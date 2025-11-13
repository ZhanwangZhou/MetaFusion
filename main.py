import typer
from leader.leader import Leader
from follower.follower import Follower

app = typer.Typer(help='MetaFusion distributed photo system CLI')


@app.command()
def leader(
        host: str = typer.Option('localhost', help='Leader IP address'),
        port: int = typer.Option(8000, help='Leader port'),
):
    """Start the leader node."""
    leader_node = Leader(host, port)
    while True:
        print('Enter command')
        try:
            cmd = input("> ").strip().split()
            if len(cmd) == 0:
                continue
            match cmd[0]:
                case 'ls':
                    leader_node.list_member()
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

