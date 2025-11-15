from typing import Optional
import torch
import clip
import numpy as np
from PIL import Image


class ImageEmbeddingModel:
    """
    Wrapper for image encoder
    """

    def __init__(
            self,
            model_name: str = 'ViT-B/32',
            device: Optional[str] = None,
            normalize: bool = True):
        self.model_name = model_name
        self.device = device or ('cuda' if torch.cuda.is_available() else 'cpu')
        self.normalize = normalize
        self.model, self.preprocess = self._load_model()
        self.model.eval()

        with torch.no_grad():
            dummy = torch.zeros(1, 3, 224, 224, device=self.device)
            emb = self.model.encode_image(dummy)
        self.embedding_dim = emb.shape[-1]

    def _load_model(self):
        model, preprocess = clip.load(self.model_name, device=self.device)
        return model, preprocess

    def encode(self, image_path: str) -> np.ndarray:
        """
        Convert an image file into a single embedding vector.

        Returns:
            np.ndarray of shape (D,), dtype float32
        """
        with Image.open(image_path) as image:
            image_tensor = self.preprocess(image).unsqueeze(0).to(self.device)
        with torch.no_grad():
            embedding = self.model.encode_image(image_tensor)
        if self.normalize:
            embedding = embedding / embedding.norm(dim=-1, keepdim=True)
        embedding = embedding.squeeze(0).cpu().numpy().astype("float32")
        return embedding
