import os
import sys

os.environ["HF_HUB_OFFLINE"] = "1"

from django.apps import AppConfig


class AIConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.ai"
    verbose_name = "AI / RAG"

    embedding_model = None
    reranker_model = None

    def ready(self):
        if len(sys.argv) > 1 and sys.argv[1] in ("migrate", "makemigrations", "collectstatic", "test", "flush", "loaddata"):
            return

        from django.conf import settings

        if not getattr(settings, "RAG_EMBEDDINGS_ENABLED", False):
            return

        try:
            from sentence_transformers import CrossEncoder, SentenceTransformer
        except ImportError:
            return

        try:
            AIConfig.embedding_model = SentenceTransformer(
                "sentence-transformers/all-MiniLM-L6-v2",
                local_files_only=True,
            )
            AIConfig.reranker_model = CrossEncoder(
                getattr(settings, "RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L6-v2"),
                local_files_only=True,
            )
        except Exception:
            AIConfig.embedding_model = None
            AIConfig.reranker_model = None
