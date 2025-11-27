import time
import requests
from datetime import datetime
from expt.es_config import *
from utils.prompt_metadata import extract_prompt_meta
from follower.storage.photo_to_vector import ImageEmbeddingModel


def build_es_query(metadata, vector=None, k=10, num_candidates=100):
    must_filters = []

    # --- Time Range ---
    start_ts = metadata.get("start_ts")
    end_ts = metadata.get("end_ts")
    if isinstance(start_ts, datetime):
        start_ts = start_ts.isoformat()
    if isinstance(end_ts, datetime):
        end_ts = end_ts.isoformat()
    if start_ts or end_ts:
        must_filters.append({
            "range": {
                "timestamp": {
                    "gte": start_ts,
                    "lte": end_ts
                }
            }
        })

    # --- Geo Bounding Box ---
    min_lat = metadata.get("min_lat")
    max_lat = metadata.get("max_lat")
    min_lon = metadata.get("min_lon")
    max_lon = metadata.get("max_lon")
    if None not in (min_lat, max_lat, min_lon, max_lon):
        must_filters.append({
            "geo_bounding_box": {
                "location": {
                    "top_left": {
                        "lat": max_lat,
                        "lon": min_lon
                    },
                    "bottom_right": {
                        "lat": min_lat,
                        "lon": max_lon
                    }
                }
            }
        })

    # --- Assemble final query ---
    body = {
        "size": k
    }
    if vector is not None:
        body["knn"] = {
            "field": "embedding",
            "query_vector": vector,
            "k": k,
            "num_candidates": num_candidates
        }
        if must_filters:
            body["query"] = {
                "bool": {
                    "filter": must_filters
                }
            }
    else:
        # Metadata-only search
        if must_filters:
            body["query"] = {
                "bool": {
                    "filter": must_filters
                }
            }
        else:
            body["query"] = {"match_all": {}}

    return body


def run_es_query(metadata, vector=None, k=10, num_candidates=100):
    query = build_es_query(metadata, vector, k, num_candidates)
    resp = requests.get(
        f'{ES_URL}/_search',
        auth=(ES_USERNAME, ES_PASSWORD),
        json=query,
        verify=False,
        timeout=10
    )
    data = resp.json()
    return [
        {
            "photo_id": hit["_source"].get("photo_id"),
            "photo_name": hit["_source"].get("photo_name"),
            "score": hit.get("_score"),
            "timestamp": hit["_source"].get("timestamp"),
            "location": hit["_source"].get("location"),
            "tags": hit["_source"].get("tags")
        }
        for hit in data["hits"]["hits"]
    ]


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('Usage: python -m expt.es_photo_search <prompt> <top_k> <num_candidates>')
        sys.exit(1)
    prompt, top_k, num_cand = sys.argv[1], 10, 100
    if len(sys.argv) > 2:
        top_k = int(sys.argv[2])
    if len(sys.argv) == 4:
        num_cand = int(sys.argv[3])
    model = ImageEmbeddingModel()
    vec = model.encode_text(prompt)
    vec = vec.reshape(1, -1).squeeze().astype("float32").tolist()
    filters = extract_prompt_meta(prompt)
    start_time = time.time()
    results = run_es_query(filters, vec, top_k, num_cand)
    for result in results:
        print(result['photo_name'], result['score'])
    end_time = time.time()
    print(end_time - start_time)
