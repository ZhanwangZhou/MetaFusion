import typer
from leader.leader import Leader
from follower.follower import Follower

app = typer.Typer(help='MetaFusion distributed photo system CLI')


@app.command()
def leader(
        host: str = typer.Option('localhost', help='Leader IP address'),
        port: int = typer.Option(8000, help='Leader port'),
        index_path: str = typer.Option('state/follower/faiss.index',
                                       help='Follower vector index path'),
        model_name: str = typer.Option('ViT-B/32',
                                       help='Follower image embedding model name'),
        device: str = typer.Option('cpu',
                                   help='Follower image embedding model device'),
        normalize: bool = typer.Option(True,
                                       help='Follower image embedding normalization')
):
    """Start the leader node."""
    leader_node = Leader(host, port, index_path, model_name, device, normalize)
    while True:
        print('Enter command')
        try:
            cmd = input("> ").strip().split()
            if len(cmd) == 0:
                continue
            match cmd[0]:
                case 'ls':
                    leader_node.list_member()
                case 'upload':
                    if len(cmd) != 2:
                        print('Please specify command as:\nupload <image_path>')
                    else:
                        leader_node.upload(cmd[1])
        except (KeyboardInterrupt, EOFError):
            print("\nBye.")
            break


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
    app()

