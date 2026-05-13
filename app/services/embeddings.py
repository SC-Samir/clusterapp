from sentence_transformers import SentenceTransformer

from app.config import get_settings

settings = get_settings()


class EmbeddingService:
    def __init__(self) -> None:
        self.model = SentenceTransformer(settings.embedding_model)

    def embed(self, text: str) -> list[float]:
        vec = self.model.encode(text or "", normalize_embeddings=True)
        return vec.tolist()
