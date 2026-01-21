import time
import requests
from datetime import datetime
from expt.es_config import *
from utils.prompt_metadata import extract_prompt_meta
from utils.photo_to_vector import ImageEmbeddingModel


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


def run_es_query(query):
    resp = requests.get(
        f'{ES_URL}/_search',
        auth=(ES_USERNAME, ES_PASSWORD),
        json=query,
        verify=CERT_PATH,
        timeout=10
    )
    data = resp.json()
    return {
        hit["_source"].get("photo_id"): {
            "photo_id": hit["_source"].get("photo_id"),
            "photo_name": hit["_source"].get("photo_name"),
            "score": hit.get("_score"),
            "timestamp": hit["_source"].get("timestamp"),
            "location": hit["_source"].get("location"),
            "tags": hit["_source"].get("tags")
        }
        for hit in data["hits"]["hits"]
    }


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] == '-f' and len(sys.argv) == 2:
        print('Usage: python -m expt.es_photo_search <prompt> <num_candidates>')
        print('or: python -m expt.es_photo_search -f <prompt_file> <num_candidates>')
        sys.exit(1)

    prompts, top_k, num_cand = [], 10, 100
    if sys.argv[1] == '-f':
        prompt_file_path = sys.argv[2]
        if len(sys.argv) == 4:
            num_cand = int(sys.argv[3])
        try:
            with open(prompt_file_path, 'r') as file:
                lines = file.readlines()
                for line in lines:
                    prompts.append(line.strip())
        except FileNotFoundError:
            print(f"Error: The file '{prompt_file_path}' was not found.")
    else:
        prompts.append(sys.argv[1])
        if len(sys.argv) == 3:
            num_cand = int(sys.argv[2])

    model = ImageEmbeddingModel()
    results = []
    total_time_1, total_time_2, total_time_3 = 0, 0, 0

    for prompt in prompts:
        time_check1 = time.perf_counter()
        filters = extract_prompt_meta(prompt)
        time_check2 = time.perf_counter()
        vec = model.encode_text(prompt)
        vec = vec.reshape(1, -1).squeeze().astype("float32").tolist()
        time_check3 = time.perf_counter()
        q1 = build_es_query(filters, None, VECTOR_SEARCH_TOP_K, num_cand)
        result1 = run_es_query(q1)
        time_check4 = time.perf_counter()
        q2 = build_es_query(filters, vec, max(len(result1), VECTOR_SEARCH_TOP_K),
                            num_cand)
        result2 = run_es_query(q2)
        time_check5 = time.perf_counter()

        results = []
        for k, v in result2.items():
            if k in result1:
                results.append(v)
        total_time_1 += time_check2 - time_check1
        total_time_2 += time_check3 - time_check2
        total_time_3 += time_check5 - time_check4
        time.sleep(0.5)

    print(f'{"=" * 60}')
    print('Search Mode: Elastic Search')
    print(f'Prompt/Prompt Num: "{prompts[0] if len(prompts) == 1 else len(prompts)}"')
    print(f'Time of prompt metadata extraction: {total_time_1: .4f} s')
    print(f'Time of prompt vectorization: {total_time_2: .4f} s')
    print(f'Time of query: {total_time_3: .4f} s')
    if sys.argv[1] != '-f':
        print(f'Total Results: {len(results)}')
        print(f'{"=" * 60}')
        for i, result in enumerate(results):
            print(f'{i + 1}.', result['photo_name'], result['score'])
    print(f'{"=" * 60}')
