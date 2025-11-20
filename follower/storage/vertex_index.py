# follower/local_storage/vector_index.py

import os
import faiss
import numpy as np
from typing import Optional, Tuple


class FollowerFaissIndex:
    """
    Local FAISS index wrapper for a follower node.
    """

    def __init__(
            self,
            index_path: str,
            embedding_dim: int,
            metric: str = "l2",  # or "ip" for inner product / cosine
    ):
        self.index_path = index_path
        self.embedding_dim = embedding_dim
        self.metric = metric
        self.index = self._load_or_create_index()
        self.next_id = self.index.ntotal  # ID: 0 to N - 1

    def _load_or_create_index(self):
        """
        Load FAISS index from disk if exists; otherwise create a new empty one.
        """
        os.makedirs(os.path.dirname(os.path.abspath(self.index_path)), exist_ok=True)
        if os.path.exists(self.index_path):
            idx = faiss.read_index(self.index_path)
            if idx.d != self.embedding_dim:
                raise ValueError(
                    f"Index dim {idx.d} != expected {self.embedding_dim}"
                )
            return idx
        if self.metric == "l2":
            idx = faiss.IndexFlatL2(self.embedding_dim)
        elif self.metric == "ip":
            idx = faiss.IndexFlatIP(self.embedding_dim)
        else:
            raise ValueError(f"Unsupported metric: {self.metric}")
        return idx

    def save(self):
        """
        Persist the current index to disk.
        """
        faiss.write_index(self.index, self.index_path)

    def add(self, vector: np.ndarray):
        """
        Add vector to FAISS index and return assigned vector_id.

        The caller is responsible for keeping any mapping from vector_id
        to higher-level identifiers such as photo_id.
        """
        vector = vector.reshape(1, -1).astype("float32")
        vector_id = self.next_id
        self.index.add(vector)
        self.next_id += 1
        return vector_id

    def search(self, query: np.ndarray, top_k: int = 10) -> Tuple[np.ndarray, np.ndarray]:
        """
        Search the index for the nearest neighbors of a query vector.

        Args:
            query: np.ndarray of shape (D,) or (1, D), dtype float32.
            top_k: Number of nearest neighbors to retrieve.

        Returns:
            distances: np.ndarray of shape (top_k,), similarity/distance scores.
            indices:   np.ndarray of shape (top_k,), corresponding vector IDs.
        """
        if query.ndim == 1:
            query = query.reshape(1, -1)
        query = query.astype("float32")
        distances, indices = self.index.search(query, top_k)
        # FAISS returns shape (1, top_k) for a single query.
        return distances[0], indices[0]

    def clear(self):
        """
        Remove all vectors from the index by recreating a fresh empty index.
        Resets next_id to 0 and overwrites the saved index file.
        """
        if self.metric == "l2":
            self.index = faiss.IndexFlatL2(self.embedding_dim)
        elif self.metric == "ip":
            self.index = faiss.IndexFlatIP(self.embedding_dim)
        else:
            raise ValueError(f"Unsupported metric: {self.metric}")
        self.next_id = 0
        self.save()

