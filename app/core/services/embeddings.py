from pathlib import Path

from sentence_transformers import SentenceTransformer

from app.core.config import get_settings

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

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Encode a batch of texts in a single forward pass.

        Returns one vector per input text, preserving order. Empty/whitespace
        inputs are still encoded (the model handles them) so the output length
        always matches the input length.
        """
        if not texts:
            return []
        vectors = self.model.encode(
            [text or "" for text in texts],
            batch_size=max(1, len(texts)),
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return [vec.tolist() for vec in vectors]