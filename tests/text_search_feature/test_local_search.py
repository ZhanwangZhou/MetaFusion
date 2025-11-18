from pathlib import Path
import argparse

from follower.storage.photo_to_vector import ImageEmbeddingModel
from follower.storage.vertex_index import FollowerFaissIndex


def parse_args():
    parser = argparse.ArgumentParser(description="Local text-to-image search feature test")
    parser.add_argument(
        "--text",
        required=True,
        help="User input text query, e.g. 'a photo of a cat'",
    )
    parser.add_argument(
        "--top_k",
        type=int,
        default=5,
        help="Number of most similar images to return",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # 1. initialize model and test local index
    model = ImageEmbeddingModel(model_name="ViT-B/32", device="cpu", normalize=True)
    index = FollowerFaissIndex(
        index_path="state/test/faiss_text_search_test.index",
        embedding_dim=model.embedding_dim,
    )

    # 2. batch read all images under tests/text_search_feature/images and vectorize them and add to index
    project_root = Path(__file__).resolve().parents[2]
    images_dir = project_root / "tests" / "text_search_feature" / "images"

    exts = (".jpg", ".jpeg", ".png", ".webp")
    image_paths = [p for p in images_dir.iterdir() if p.suffix.lower() in exts]

    if not image_paths:
        print(f"[WARN] no images found under: {images_dir}")
        return

    print(f"[INFO] found {len(image_paths)} images under {images_dir}")

    id_to_path = {}
    for p in image_paths:
        emb = model.encode(str(p))
        vid = index.add(emb)
        id_to_path[vid] = str(p)
        print(f"[ADD] vector_id={vid} for {p}")

    index.save()

    # 3. query with the text input from command line
    query = args.text
    top_k = max(1, int(args.top_k))

    print(f"\n[QUERY] {query}  (top_k={top_k})")
    q_vec = model.encode_text(query)

    dists, ids = index.search(q_vec, top_k=top_k)

    print("\n[RESULTS]")
    for vid, dist in zip(ids, dists):
        if vid == -1:
            continue
        path = id_to_path.get(vid, "<unknown>")
        print(f"  vector_id={vid}, dist={dist:.4f}, path={path}")


if __name__ == "__main__":
    main()