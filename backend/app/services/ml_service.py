import logging
import numpy as np
from typing import Optional

logger = logging.getLogger(__name__)


class MLService:
    def __init__(self):
        self.model = None

    def load_model(self, model_name: str):
        """Load the embedding model. Called once at app startup."""
        try:
            from fastembed import TextEmbedding
            logger.info(f"Loading ML model: {model_name}")
            self.model = TextEmbedding(model_name=model_name)
            # Warm up with a test embedding
            list(self.model.embed(["test"]))
            logger.info("ML model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load ML model: {e}")
            self.model = None

    def auto_sort(
        self,
        items: list[dict],
        categories: list[dict],
        threshold: float = 0.25,
    ) -> list[dict]:
        """
        Match items to categories using semantic similarity.

        items: [{"id": "...", "name": "Milch"}, ...]
        categories: [{"id": "...", "name": "Milchprodukte"}, ...]

        Returns: [{"item_id": "...", "item_name": "...", "category_id": "...",
                   "category_name": "...", "confidence": 0.87}, ...]
        """
        if not self.model or not items or not categories:
            return []

        item_names = [i["name"] for i in items]
        cat_names = [c["name"] for c in categories]

        # Batch embed all texts
        item_embeddings = np.array(list(self.model.embed(item_names)))
        cat_embeddings = np.array(list(self.model.embed(cat_names)))

        # Normalize for cosine similarity
        item_norm = item_embeddings / np.linalg.norm(item_embeddings, axis=1, keepdims=True)
        cat_norm = cat_embeddings / np.linalg.norm(cat_embeddings, axis=1, keepdims=True)

        # Cosine similarity matrix: (num_items x num_categories)
        similarity = item_norm @ cat_norm.T

        assignments = []
        for i, item in enumerate(items):
            best_idx = int(np.argmax(similarity[i]))
            confidence = float(similarity[i][best_idx])

            if confidence >= threshold:
                assignments.append({
                    "item_id": item["id"],
                    "item_name": item["name"],
                    "category_id": categories[best_idx]["id"],
                    "category_name": categories[best_idx]["name"],
                    "confidence": round(confidence, 3),
                })

        return assignments


ml_service = MLService()
