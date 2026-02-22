import time
import datetime
from datetime import timedelta, timezone
from leader.leader import Leader
from leader.storage.store import *
from utils.config import *
from utils.formulas import *
from utils.network import tcp_client
from utils.extract_prompt_location import extract_locations
from utils.extract_prompt_time import extract_time_range, w_timestamp


class LeaderAdaptive(Leader):
    def __init__(self, host, port, base_dir, model_name, device, normalize):
        super().__init__(host, port, base_dir, model_name, device, normalize)

    def search(self, prompt, output_path=None, search_mode='meta_fusion'):
        if len(self.followers) == 0:
            print("No follower nodes available.")
            return

        # Extract location and time range with weights
        locs = extract_locations(prompt)
        w_loc = 0
        for loc in locs:
            w_loc = max(w_loc, loc.score)
        t_start, t_end = extract_time_range(prompt, datetime.now())
        w_time = w_timestamp(prompt=prompt, t_start=t_start, t_end=t_end, half_life_days=WEIGHT_TIME_HALF_LIFE)

        # Convert time to offset-aware and normalize weights
        t_start = t_start.replace(tzinfo=timezone.utc)
        t_end = t_end.replace(tzinfo=timezone.utc)
        w_loc_nml = w_loc / (w_loc + w_time)
        w_time_nml = w_time / (w_loc + w_time)

        # Fetch photos by location and compute location similarity
        sim_scores = {}
        for loc in locs:
            lambda_km = 0.5 * bbox_radius_km(loc.min_lat, loc.max_lat, loc.min_lon, loc.max_lon)
            delta_lat, delta_lon = max_query_distance(lambda_km=lambda_km, ref_lat=loc.lat)
            rows = fetch_photos_by_bounding_box(
                self.conn,
                loc.min_lat - delta_lat,
                loc.max_lat + delta_lat,
                loc.min_lon - delta_lon,
                loc.max_lon + delta_lon
            )
            for photo_id, lat, lon in rows:
                distance_km = distance_point_to_bbox_km(lat, lon, loc.min_lat, loc.max_lat, loc.min_lon, loc.max_lon)
                sim_l = location_similarity(distance_km, lambda_km)
                sim_score = sim_l * loc.score / w_loc * w_loc_nml
                if photo_id not in sim_scores or sim_scores[photo_id] < sim_score:
                    sim_scores[photo_id] = sim_score

        # Fetch photos by time range and compute time similarity
        lambda_days = 0.5 * round((t_end - t_start).total_seconds() / 86400, 3)
        delta_days = max_query_time_difference(lambda_days=lambda_days)
        rows = fetch_photos_by_time_range(self.conn,
                                          t_start - timedelta(days=delta_days),
                                          t_end + timedelta(days=delta_days))
        for photo_id, ts in rows:
            sim_t = time_similarity(ts, t_start, t_end, lambda_days)
            sim_score = sim_t * w_time_nml
            if photo_id not in sim_scores:
                sim_scores[photo_id] = 0
            sim_scores[photo_id] += sim_score

        # Send search request to followers
        query_vec = self.model.encode_text(prompt)
        request_id = f"search-{int(time.time() * 10000)}"
        self.pending_client_request[request_id] = {
            'prompt': prompt,
            'recipients':  {f['silo_id'] for f in self.followers},
            'w_loc': w_loc_nml,
            'w_time': w_time_nml,
            'metadata_sim_scores': sim_scores,
            'vector_sim_scores': {},
        }
        message = {
            'message_type': 'search',
            'request_id': request_id,
            'text': prompt,
            'query_vec': query_vec.tolist(),
            'top_k': TOP_K_ADAPTIVE
        }
        for follower in self.followers:
            if follower.get('status') != 'alive':
                if 'pending_message' in follower:
                    follower['pending_message'][request_id] = message
                continue
            tcp_client(follower['host'], follower['port'], message)

    def _handle_search_result(self, message_dict, get_photo=False):
        silo_id = message_dict.get('silo_id')
        request_id = message_dict.get('request_id')
        request = self.pending_client_request.get(request_id)
        if not request:
            LOGGER.warning(f'Receiving unknown search result from follower{silo_id}')
            return
        request['recipients'].remove(silo_id)

        # Aggregate vector similarity scores from followers
        results = message_dict.get('results', [])
        results = sorted(results, key=lambda x: x['score'])
        d_min = results[0]['score']
        r = vector_constant_target_ranking(len(request['metadata_sim_scores']))
        tau = vector_sim_constant_tau(d_1=d_min, d_r=results[r]['score'])
        for result in results:
            sim_score = vector_similarity(tau, d_1=d_min, d_r=result['score'])
            request['vector_sim_scores'][result['photo_id']] = sim_score
        if len(request['recipients']) > 0:
            return

        # Compute metadata and vector score weight
        a_loc, a_time = query_meta_availability(self.conn)
        w_loc = request['w_loc']
        w_time = request['w_time']
        availability = a_loc * w_loc + a_time * w_time
        vec_sim_sorted = sorted(request['vector_sim_scores'].values(), reverse=True)
        vector_conf = vector_confidence(vec_sim_sorted[0], vec_sim_sorted[min(100, len(vec_sim_sorted) - 1)])
        w_m, w_v = metadata_and_vector_weight(A=availability, R_v=vector_conf)

        # Compute final scores by combining metadata and vector similarity scores
        final_scores = {key: val * w_m for key, val in request['metadata_sim_scores'].items()}
        for key, val in request['vector_sim_scores'].items():
            if key not in final_scores:
                final_scores[key] = 0
            final_scores[key] += val * w_v
        self.pending_client_request.pop(request_id)

        sorted_photo_ids = sorted(final_scores.keys(), key=lambda x: final_scores[x], reverse=True)
        print(f'\n{"=" * 60}')
        print(f'Prompt: "{request["prompt"]}"')
        print(f'{"=" * 60}')
        print('w_m:', w_m, '\tw_v:', w_v)
        print(f'{"=" * 60}')
        for photo_id in sorted_photo_ids:
            if final_scores[photo_id] < 0.5:
                break
            print(photo_id, final_scores[photo_id])
        print(f'{"=" * 60}\n')
