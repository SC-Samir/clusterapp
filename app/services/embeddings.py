from pathlib import Path

from sentence_transformers import SentenceTransformer

from app.config import get_settings

settings = get_settings()


class EmbeddingService:
    def __init__(self) -> None:
        model_path = Path(settings.embedding_model)
        sentence_transformer_kwargs = {
            "device": "cpu",
            "local_files_only": True,
        }

        if not (model_path / "model.safetensors").exists() and (model_path / "pytorch_model.bin").exists():
            sentence_transformer_kwargs["model_kwargs"] = {"use_safetensors": False}

        self.model = SentenceTransformer(
            settings.embedding_model,
            **sentence_transformer_kwargs,
        )

    def embed(self, text: str) -> list[float]:
        vec = self.model.encode(text or "", normalize_embeddings=True)
        return vec.tolist()
