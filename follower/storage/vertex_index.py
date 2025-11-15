# follower/local_storage/vector_index.py

import os
from typing import Optional, Tuple

import faiss
import numpy as np


class FollowerFaissIndex:
    """
    Local FAISS index wrapper for a follower node.
    """

    def __init__(
        self,
        index_path: str,
        embedding_dim: int,
        metric: str = "l2",   # or "ip" for inner product / cosine
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
        """
        vector = vector.reshape(1, -1).astype("float32")
        vector_id = self.next_id
        self.index.add(vector)
        self.next_id += 1
        return vector_id
