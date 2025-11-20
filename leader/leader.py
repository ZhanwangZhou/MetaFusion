import os
import time
import threading
import base64
from typing import List, Dict, Optional, Any
from leader.storage.store import *
from utils.config import *
from utils.image_utils import *
from utils.prompt_metadata import extract_prompt_meta
from utils.network import tcp_server
from utils.network import tcp_client
from utils.network import udp_server


class Leader:
    def __init__(self, host, port, base_dir, model_name, device, normalize):
        self.host = host
        self.port = port
        self.signals = {'shutdown': False}
        self.followers: List[Dict[str, Optional[Any]]] = []
        self.pending_client_request: Dict[str, Dict[str, Optional[Any]]] = {}

        # Unified follower index/model parameters
        self.base_dir = base_dir
        self.model_name = model_name
        self.device = device
        self.normalize = normalize

        self.check_heartbeat_thread = threading.Thread(target=self._check_heartbeat)
        self.udp_listen_thread = threading.Thread(
            target=udp_server, args=(host, port, self.signals, self._udp_listen)
        )
        self.tcp_listen_thread = threading.Thread(
            target=tcp_server, args=(host, port, self.signals, self._tcp_listen)
        )

        self.check_heartbeat_thread.start()
        self.udp_listen_thread.start()
        self.tcp_listen_thread.start()
        self.conn = init_metadata_table()
        LOGGER.info('Leader initialized')
        # self.tcp_listen_thread.join()
        # self.udp_listen_thread.join()
        # self.check_heartbeat_thread.join()

    def list_member(self):
        print('Leader: Host = %s, Port = %d' % (self.host, self.port))
        for i, follower in enumerate(self.followers):
            print('Follower: ID = %d, Host = %s, Port = %d, Status = %s'
                  % (i, follower['host'], follower['port'], follower['status']))

    def upload(self, image_path):
        if len(self.followers) == 0:
            print('No follower nodes are assigned to the leader')
            return
        try:
            image_bytes = read_image_bytes(image_path)
        except Exception as e:
            print(f'Failed to read image from {image_path}: {e}')
            return
        image_hash = hash_image_bytes(image_bytes)
        photo_name = os.path.basename(image_path)
        photo_id = image_hash  # can be updated later with upload_time/user_id
        if query_by_photo_id(self.conn, photo_id):
            print(photo_name, 'has already been stored')
            return
        digest = hashlib.sha256(photo_id.encode("utf-8")).hexdigest()
        index = int(digest, 16) % len(self.followers)
        image_b64 = base64.b64encode(image_bytes).decode("ascii")
        message = {
            'message_type': 'upload',
            'photo_id': photo_id,
            'photo_name': photo_name,
            'photo_format': get_format_from_bytes(image_bytes),
            'image_b64': image_b64
        }
        tcp_client(self.followers[index]['host'],
                   self.followers[index]['port'],
                   message)

    def mass_upload(self, image_dir):
        photo_paths = list_photo_paths(image_dir)
        for photo_path in photo_paths:
            self.upload(photo_path)

    def search(self, prompt, output_path=None, vector_search=True, search_mode='metafusion'):
        """
        搜索图片，支持三种模式：
        - 'metafusion': 元数据过滤 + 向量搜索（默认）
        - 'vector_only': 仅在所有follower上进行向量搜索
        - 'metadata_only': 仅使用元数据搜索
        
        Args:
            prompt: 搜索提示词
            output_path: 输出路径
            vector_search: 是否启用向量搜索（向后兼容）
            search_mode: 搜索模式 ('metafusion', 'vector_only', 'metadata_only')
        """
        metadata = extract_prompt_meta(prompt)
        LOGGER.info('Extracted prompt meta data: %s', metadata)

        # 模式1: 仅元数据搜索（只在leader节点）
        if search_mode == 'metadata_only':
            LOGGER.info("=== Metadata Only Search ===")
            cand_silos = prefilter_candidate_silos(self.conn, metadata)
            LOGGER.info("Candidate silos (silo_id, count): %s", cand_silos)
            if not cand_silos:
                print("No candidate silos from metadata.")
                return []
            silo_ids = [s for (s, _) in cand_silos]
            candidates = fetch_photos_by_metadata(self.conn, metadata, silo_ids)
            LOGGER.info(f"Found {len(candidates)} candidate photos from metadata only")
            print(f"Metadata Only Search Results for prompt '{prompt}':")
            print(f"Total results: {len(candidates)}")
            for i, photo in enumerate(candidates[:10]):  # 显示前10个
                print(f"  {i+1}. photo_id={photo['photo_id']}, silo_id={photo['silo_id']}, ts={photo['ts']}")
            return candidates

        # 模式2: 仅向量搜索（在所有follower上）
        if search_mode == 'vector_only':
            LOGGER.info("=== Vector Only Search (All Silos) ===")
            if len(self.followers) == 0:
                print("No follower nodes available.")
                return []
            # 向所有follower发送向量搜索请求
            alive_followers = [(f['silo_id'], f) for f in self.followers if f.get('status') == 'alive']
            if not alive_followers:
                print("No alive follower nodes.")
                return []
            
            silo_ids = {silo_id for silo_id, _ in alive_followers}
            request_id = f"search-{int(time.time() * 10000)}"
            self.pending_client_request[request_id] = {
                'prompt': prompt,
                'recipients': silo_ids.copy(),
                'last_check': time.time(),
                'result': [],
                'search_mode': 'vector_only'
            }
            message = {
                'message_type': 'search',
                'request_id': request_id,
                'text': prompt,
                'top_k': VECTOR_SEARCH_TOP_K,
            }
            if output_path and os.path.isdir(output_path):
                message['message_type'] = 'get'
                message['output_path'] = output_path
            
            LOGGER.info(f"Sending vector search to all {len(alive_followers)} followers")
            for silo_id, follower in alive_followers:
                tcp_client(follower['host'], follower['port'], message)
            return None  # 异步返回

        # 模式3: MetaFusion（元数据过滤 + 向量搜索）
        if search_mode == 'metafusion':
            LOGGER.info("=== MetaFusion Search (Metadata + Vector) ===")
            # Filter silos by metadata
            cand_silos = prefilter_candidate_silos(self.conn, metadata)
            LOGGER.info("Candidate silos (silo_id, count): %s", cand_silos)
            if not cand_silos:
                print("No candidate silos from metadata; skip vector search.")
                return []
            
            # 如果禁用向量搜索（向后兼容）
            if not vector_search:
                silo_ids = [s for (s, _) in cand_silos]
                candidates = fetch_photos_by_metadata(self.conn, metadata, silo_ids)
                LOGGER.debug(f"Found {len(candidates)} candidate photos, sample: %s",
                             candidates[:5])
                return candidates
            
            silo_ids = {s for (s, _) in cand_silos}
            request_id = f"search-{int(time.time() * 10000)}"
            self.pending_client_request[request_id] = {
                'prompt': prompt,
                'recipients': silo_ids.copy(),
                'last_check': time.time(),
                'result': [],
                'search_mode': 'metafusion'
            }
            message = {
                'message_type': 'search',
                'request_id': request_id,
                'text': prompt,
                'top_k': VECTOR_SEARCH_TOP_K,
            }
            if output_path and os.path.isdir(output_path):
                message['message_type'] = 'get'
                message['output_path'] = output_path
            
            LOGGER.info(f"Sending vector search to {len(cand_silos)} filtered followers")
            for silo_id, num in cand_silos:
                message['top_k'] = max(num * 2, VECTOR_SEARCH_TOP_K)
                follower = self.followers[silo_id]
                if follower.get('status') != 'alive':
                    if 'pending_message' in follower:
                        follower['pending_message'][request_id] = message
                    continue
                tcp_client(follower['host'], follower['port'], message)
            return None  # 异步返回

        raise ValueError(f"Unknown search_mode: {search_mode}")

    def compare_search_methods(self, prompt, output_path=None, wait_time=5):
        """
        比较三种搜索方法的准确度和性能：
        1. MetaFusion (元数据过滤 + 向量搜索)
        2. Vector Only (仅向量搜索，所有follower)
        3. Metadata Only (仅元数据搜索，leader节点)
        
        Args:
            prompt: 搜索提示词
            output_path: 输出路径
            wait_time: 等待向量搜索完成的时间（秒）
        """
        print("\n" + "="*80)
        print("开始搜索方法对比测试")
        print(f"查询提示词: '{prompt}'")
        print("="*80 + "\n")
        
        results = {}
        
        # 测试1: 仅元数据搜索
        print("\n[测试 1/3] 仅元数据搜索 (Leader节点)...")
        start_time = time.time()
        metadata_results = self.search(prompt, search_mode='metadata_only')
        metadata_time = time.time() - start_time
        results['metadata_only'] = {
            'results': metadata_results if metadata_results else [],
            'time': metadata_time,
            'count': len(metadata_results) if metadata_results else 0
        }
        print(f"完成时间: {metadata_time:.3f}秒, 结果数量: {results['metadata_only']['count']}\n")
        
        # 测试2: 仅向量搜索（所有follower）
        print("[测试 2/3] 仅向量搜索 (所有Follower节点)...")
        start_time = time.time()
        self.search(prompt, output_path=output_path, search_mode='vector_only', vector_search=True)
        print(f"等待 {wait_time} 秒收集结果...")
        time.sleep(wait_time)
        vector_time = time.time() - start_time
        # 从pending_client_request中查找vector_only的结果
        vector_results = []
        for req_id, req in list(self.pending_client_request.items()):
            if req.get('search_mode') == 'vector_only' and req['prompt'] == prompt:
                vector_results = req.get('result', [])
                break
        results['vector_only'] = {
            'results': vector_results,
            'time': vector_time,
            'count': len(vector_results)
        }
        print(f"完成时间: {vector_time:.3f}秒, 结果数量: {results['vector_only']['count']}\n")
        
        # 测试3: MetaFusion（元数据过滤 + 向量搜索）
        print("[测试 3/3] MetaFusion搜索 (元数据过滤 + 向量搜索)...")
        start_time = time.time()
        self.search(prompt, output_path=output_path, search_mode='metafusion', vector_search=True)
        print(f"等待 {wait_time} 秒收集结果...")
        time.sleep(wait_time)
        metafusion_time = time.time() - start_time
        # 从pending_client_request中查找metafusion的结果
        metafusion_results = []
        for req_id, req in list(self.pending_client_request.items()):
            if req.get('search_mode') == 'metafusion' and req['prompt'] == prompt:
                metafusion_results = req.get('result', [])
                break
        results['metafusion'] = {
            'results': metafusion_results,
            'time': metafusion_time,
            'count': len(metafusion_results)
        }
        print(f"完成时间: {metafusion_time:.3f}秒, 结果数量: {results['metafusion']['count']}\n")
        
        # 打印比较总结
        self._print_comparison_summary(prompt, results)
        
        return results
    
    def _print_comparison_summary(self, prompt, results):
        """
        打印搜索方法比较总结
        """
        print("\n" + "="*80)
        print("搜索方法对比总结")
        print("="*80)
        print(f"查询提示词: '{prompt}'\n")
        
        # 性能对比
        print("【性能对比】")
        print(f"{'方法':<20} {'耗时(秒)':<15} {'结果数量':<15}")
        print("-" * 50)
        for method, data in results.items():
            method_name = {
                'metadata_only': '仅元数据搜索',
                'vector_only': '仅向量搜索',
                'metafusion': 'MetaFusion'
            }.get(method, method)
            print(f"{method_name:<20} {data['time']:<15.3f} {data['count']:<15}")
        
        # 结果对比
        print("\n【结果对比】")
        
        # MetaFusion vs Vector Only
        if results['metafusion']['count'] > 0 and results['vector_only']['count'] > 0:
            reduction_rate = (1 - results['metafusion']['count'] / results['vector_only']['count']) * 100
            print(f"MetaFusion vs 仅向量搜索: 搜索空间减少了 {reduction_rate:.1f}%")
        
        # 显示各方法的top结果
        print("\n【Top-5 结果预览】")
        for method, data in results.items():
            method_name = {
                'metadata_only': '仅元数据搜索',
                'vector_only': '仅向量搜索',
                'metafusion': 'MetaFusion'
            }.get(method, method)
            print(f"\n{method_name}:")
            
            if method == 'metadata_only':
                # 元数据搜索结果
                for i, photo in enumerate(data['results'][:5]):
                    print(f"  {i+1}. photo_id={photo.get('photo_id', 'N/A')}, "
                          f"silo_id={photo.get('silo_id', 'N/A')}")
            else:
                # 向量搜索结果（带score）
                sorted_results = sorted(data['results'], key=lambda x: x.get('score', 0), reverse=True)
                for i, photo in enumerate(sorted_results[:5]):
                    print(f"  {i+1}. photo_id={photo.get('photo_id', 'N/A')}, "
                          f"score={photo.get('score', 0):.4f}")
        
        print("\n" + "="*80 + "\n")

    def clear(self):
        clear_all_photos(self.conn)
        LOGGER.info('Cleared photos in metadata database')
        message = {'message_type': 'clear'}
        for follower in self.followers:
            tcp_client(follower['host'], follower['port'], message)

    def _check_heartbeat(self):
        while not self.signals['shutdown']:
            for follower in self.followers:
                if follower['status'] == 'alive' and \
                        time.time() - follower['heartbeat'] > FOLLOWER_TIMEOUT:
                    follower['status'] = 'dead'
                    LOGGER.info('Set follower %d to dead' % (follower['silo_id']))
            time.sleep(FOLLOWER_HEARTBEAT_INTERVAL)

    def _udp_listen(self, message_dict):
        match message_dict['message_type']:
            case 'heartbeat':
                self.followers[message_dict['silo_id']]['heartbeat'] = time.time()

    def _tcp_listen(self, message_dict):
        match message_dict['message_type']:
            case 'register':
                self._handle_register(message_dict)
            case 'upload_reply':
                self._handle_upload_reply(message_dict)
            case 'search_result':
                self._handle_search_result(message_dict)
            case 'get_result':
                self._handle_search_result(message_dict, get_photo=True)

    def _handle_register(self, message_dict):
        host = message_dict['host']
        port = message_dict['port']
        for i, follower in enumerate(self.followers):
            if follower['host'] == host and follower['port'] == port:
                silo_id = i
                follower['status'] = 'alive'
                follower['heartbeat'] = time.time()
                break
        else:
            silo_id = len(self.followers)
            new_follower = {
                'silo_id': silo_id,
                'host': host,
                'port': port,
                'status': 'alive',
                'heartbeat': time.time(),
                'pending_message': {}
            }
            self.followers.append(new_follower)
        message = {
            'message_type': 'register_ack',
            'silo_id': silo_id,
            'leader_host': self.host,
            'leader_port': self.port,
            'base_dir': self.base_dir,
            'model_name': self.model_name,
            'device': self.device,
            'normalize': self.normalize
        }
        try:
            tcp_client(host, port, message)
            LOGGER.info('Ack registration of follower %d (host = %s, port = %d)'
                        % (silo_id, host, port))
        except ConnectionRefusedError:
            self.followers[silo_id]['status'] = 'dead'

    def _handle_upload_reply(self, message_dict):
        silo_id = message_dict['silo_id']
        metadata = message_dict['metadata']
        insert_new_photo(self.conn, silo_id, metadata)
        LOGGER.info(f'Inserted photo {metadata["photo_name"]} into metadata database.'
                    f'Assigned to follower {silo_id}')

    def _handle_search_result(self, message_dict, get_photo=False):
        """
        Handle text-to-image search results coming back from a follower.
        """
        silo_id = message_dict.get('silo_id')
        request_id = message_dict.get('request_id')
        results = message_dict.get('results', [])
        request = self.pending_client_request.get(request_id)
        if not request:
            LOGGER.warning(f'Receiving unknown search result from follower{silo_id}')
            return
        request['recipients'].remove(silo_id)
        request['result'] += results
        if len(request['recipients']) > 0:
            return
        
        # 所有结果都收集完毕
        search_mode = request.get('search_mode', 'unknown')
        print(f'\n{"="*60}')
        print(f'Search Mode: {search_mode.upper()}')
        print(f'Prompt: "{request["prompt"]}"')
        print(f'Total Results: {len(request["result"])}')
        print(f'{"="*60}')
        
        if not request['result']:
            print("(no results)")
        else:
            # 按得分排序
            sorted_results = sorted(request['result'], key=lambda x: x.get('score', 0), reverse=True)
            for i, r in enumerate(sorted_results[:10]):  # 显示前10个结果
                score = r.get('score')
                photo_name = r.get('photo_name')
                photo_id = r.get('photo_id', 'N/A')
                print(f'{i+1}. Filename = {photo_name}, Photo_ID = {photo_id}, Score = {score:.4f}')
                if get_photo:
                    image_bytes = base64.b64decode(r['image_b64'])
                    output_path = os.path.join(message_dict['output_path'], photo_name)
                    save_image_bytes(image_bytes, output_path)
                    print(f'   Saved to {output_path}')
        print(f'{"="*60}\n')
        self.pending_client_request.pop(request_id)
