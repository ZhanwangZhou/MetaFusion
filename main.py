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
                    # assume leader_node has list_member() to show the follower list
                    leader_node.list_member()
                case 'upload':
                    if not arg:
                        print('Usage: upload <image path>')
                        continue
                    leader_node.upload(arg)
                case 'mass_upload':
                    if not arg:
                        print('Usage: upload <image directory>')
                    leader_node.mass_upload(arg)
                case 'clear':
                    leader_node.clear()
                case 'search':
                    if not arg:
                        print("Usage: search <natural language prompt>")
                        continue
                    leader_node.search(arg)
                case 'get':
                    parts = arg.split(maxsplit=1)
                    if len(parts) <= 1:
                        print('Usage: get <output directory> <natural language prompt>')
                        continue
                    leader_node.search(parts[1], parts[0])
                case 'exit' | 'quit':
                    print("Bye.")
                    break

                case _:
                    print(f"Unknown command: {cmd}")

        except (KeyboardInterrupt, EOFError):
            print("\nBye.")
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
