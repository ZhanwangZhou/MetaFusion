import os
import sys
import time

import typer
from leader.leader import Leader
from follower.follower import Follower

app = typer.Typer(help='MetaFusion distributed photo system CLI')


@app.command()
def leader(
        host: str = typer.Option('localhost', help='Leader IP address'),
        port: int = typer.Option(8000, help='Leader port'),
        base_dir: str = typer.Option('state/',
                                     help='Follower vector index base directory'),
        model_name: str = typer.Option('ViT-B/32',
                                       help='Follower image embedding model name'),
        device: str = typer.Option('cpu',
                                   help='Follower image embedding model device'),
        normalize: bool = typer.Option(True,
                                       help='Follower image embedding normalization')
):
    """Start the leader node."""
    leader_node = Leader(host, port, base_dir, model_name, device, normalize)

    # If the Leader doesn't include an extractor, you can create one here in main:

    while True:
        print('Enter command')
        try:
            line = input("> ").strip()
            if not line:
                continue

            # split into command + remaining args
            parts = line.split(maxsplit=1)
            cmd = parts[0]
            arg = parts[1] if len(parts) > 1 else ""

            match cmd:
                case 'ls':
                    leader_node.list_member()
                case 'ls_num_photo':
                    leader_node.list_num_photo()
                case 'upload':
                    if not arg:
                        print('Usage: upload <image path>')
                        continue
                    leader_node.upload(arg)
                case 'mass_upload':
                    if not arg:
                        print('Usage: upload <image directory>')
                    leader_node.mass_upload(arg)
                case 'upload_from_msgpack':
                    leader_node.upload_from_msgpack(arg)
                case 'clear':
                    leader_node.clear()
                case 'search':
                    if not arg:
                        print("Usage: search <natural language prompt>")
                        continue
                    leader_node.search(arg, search_mode='meta_fusion')
                case 'mass_search':
                    if not arg:
                        print("Usage: mass_search <prompt file>")
                        continue
                    leader_node.mass_search(arg)
                case 'search_metadata':
                    if not arg:
                        print("Usage: search_metadata <natural language prompt>")
                        continue
                    leader_node.search(arg, search_mode='metadata_only')
                case 'search_vector':
                    if not arg:
                        print("Usage: search_vector <natural language prompt>")
                        continue
                    leader_node.search(arg, search_mode='vector_only')
                case 'get':
                    parts = arg.split(maxsplit=1)
                    if len(parts) <= 1:
                        print('Usage: get <output directory> <natural language prompt>')
                        continue
                    leader_node.search(parts[1], parts[0], search_mode='meta_fusion')
                case 'help':
                    print("\n可用命令:")
                    print("  ls                          - 列出所有follower节点")
                    print("  upload <path>               - 上传单张图片")
                    print("  mass_upload <dir>           - 批量上传图片目录")
                    print("  clear                       - 清空所有数据")
                    print("  search <prompt>             - MetaFusion搜索 (默认)")
                    print("  search_metadata <prompt>    - 仅元数据搜索")
                    print("  search_vector <prompt>      - 仅向量搜索")
                    print("  compare <prompt>            - 比较三种搜索方法")
                    print("  get <dir> <prompt>          - 搜索并下载图片")
                    print("  help                        - 显示帮助信息")
                    print("  exit/quit                   - 退出程序\n")
                case 'exit' | 'quit':
                    print("Bye.")
                    leader_node.quit()
                    break

                case _:
                    print(f"Unknown command: {cmd}. Type 'help' for available commands.")

        except (KeyboardInterrupt, EOFError):
            print("\nBye.")
            leader_node.quit()
            break
        time.sleep(0.5)


@app.command()
def follower(
        host: str = typer.Option('localhost', help='Follower IP address'),
        port: int = typer.Option(9000, help='Follower port'),
        leader_host: str = typer.Option('localhost', help='Leader IP address'),
        leader_port: int = typer.Option(8000, help='Leader port'),
):
    """Start a follower node."""
    follower_node = Follower(host, port)
    follower_node.register(leader_host, leader_port)


if __name__ == "__main__":
    if sys.platform == "darwin":
        os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
    app()
