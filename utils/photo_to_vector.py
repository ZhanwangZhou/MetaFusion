from typing import Optional

import clip
import numpy as np
import torch
from PIL import Image
from io import BytesIO


class ImageEmbeddingModel:
    """
    Wrapper around CLIP for both image and text encoding.
    """

    def __init__(
        self,
        model_name: str = "ViT-B/32",
        device: Optional[str] = None,
        normalize: bool = True,
    ):
        self.model_name = model_name
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.normalize = normalize
        self.model, self.preprocess = self._load_model()
        self.model.eval()

        # Probe embedding dimension once so that downstream components
        # (like FAISS index) can be initialized correctly.
        with torch.no_grad():
            dummy = torch.zeros(1, 3, 224, 224, device=self.device)
            emb = self.model.encode_image(dummy)
        self.embedding_dim = emb.shape[-1]

    def _load_model(self):
        model, preprocess = clip.load(self.model_name, device=self.device)
        return model, preprocess

    def encode(self, image_path: str = "", image_bytes: bytes = None) -> np.ndarray:
        """
        Convert an image file into a single embedding vector.

        Returns:
            np.ndarray of shape (D,), dtype float32
        """
        if image_path:
            with Image.open(image_path) as image:
                image_tensor = self.preprocess(image).unsqueeze(0).to(self.device)
        elif image_bytes:
            image = Image.open(BytesIO(image_bytes)).convert("RGB")
            image_tensor = self.preprocess(image).unsqueeze(0).to(self.device)
        else:
            raise ValueError
        with torch.no_grad():
            embedding = self.model.encode_image(image_tensor)
        if self.normalize:
            embedding = embedding / embedding.norm(dim=-1, keepdim=True)
        embedding = embedding.squeeze(0).cpu().numpy().astype("float32")
        return embedding

    def encode_text(self, text: str) -> np.ndarray:
        """
        Encode a natural language text query into a single embedding vector.

        The returned vector lives in the same embedding space as image
        embeddings produced by `encode`, so it can be directly compared
        with stored image vectors for text-to-image search.

        Returns:
            np.ndarray of shape (D,), dtype float32
        """
        # CLIP expects a batch of tokenized texts.
        tokens = clip.tokenize([text]).to(self.device)
        with torch.no_grad():
            embedding = self.model.encode_text(tokens)
        if self.normalize:
            embedding = embedding / embedding.norm(dim=-1, keepdim=True)
        embedding = embedding.squeeze(0).cpu().numpy().astype("float32")
        return embedding
