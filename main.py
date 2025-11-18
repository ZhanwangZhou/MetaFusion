import typer
from leader.leader import Leader
from leader.storage.store import prefilter_candidate_silos, search_metadata
from follower.follower import Follower
from utils.geocode import geocode_bbox
from utils.prompt_metadata import PromptMetadataExtractor

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
    extractor = PromptMetadataExtractor()

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
                    leader_node.upload(arg)
                case 'clear':
                    leader_node.clear()
                case 'search':
                    if not arg:
                        print("Usage: search <natural language prompt>")
                        continue

                    prompt = arg
                    meta = extractor.extract(prompt)
                    print("Parsed metadata:", meta.to_dict())

                    # default: no geographic bounds
                    min_lat = max_lat = min_lon = max_lon = None

                    # If a location was extracted (e.g., ["Yosemite"]), geocode the first place
                    if meta.locations:
                        bbox = geocode_bbox(meta.locations[0], radius_km=50.0)
                        if bbox is not None:
                            min_lat, max_lat, min_lon, max_lon = bbox
                            print(
                                f"Geocoded location '{meta.locations[0]}' "
                                f"-> bbox: lat[{min_lat:.4f}, {max_lat:.4f}], "
                                f"lon[{min_lon:.4f}, {max_lon:.4f}]"
                            )
                        else:
                            print(f"Warning: could not geocode location: {meta.locations[0]}")

                    # 1) Prefilter silos by metadata
                    cand_silos = prefilter_candidate_silos(
                        start_ts=meta.start_ts,
                        end_ts=meta.end_ts,
                        min_lat=min_lat,
                        max_lat=max_lat,
                        min_lon=min_lon,
                        max_lon=max_lon,
                        any_tags=meta.tags or None,
                    )
                    print("Candidate silos (silo_id, count):", cand_silos)

                    # 2) Then query specific photo_ids (for follower subset search)
                    silo_ids = [s for (s, _) in cand_silos]
                    candidates = search_metadata(
                        start_ts=meta.start_ts,
                        end_ts=meta.end_ts,
                        min_lat=min_lat,
                        max_lat=max_lat,
                        min_lon=min_lon,
                        max_lon=max_lon,
                        any_tags=meta.tags or None,
                        silo_ids=silo_ids,
                        limit=1000,
                    )
                    print(f"Found {len(candidates)} candidate photos, sample:", candidates[:5])

                    # 3) Ask candidate followers to run vector search with the same prompt
                    if not cand_silos:
                        print("No candidate silos from metadata; skip vector search.")
                    else:
                        silo_ids = [s for (s, _) in cand_silos]
                        # For now, keep it simple: request top_k results per follower.
                        leader_node.search_text(prompt, candidate_silo_ids=silo_ids, top_k=5)

                case 'exit' | 'quit':
                    print("Bye.")
                    break

                case _:
                    print(f"Unknown command: {cmd}")

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

