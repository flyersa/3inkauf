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
            list(self.model.embed(["test"]))
            logger.info("ML model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load ML model: {e}")
            self.model = None

    def _hint_match(self, item_name: str, categories: list[dict], hints: dict) -> Optional[dict]:
        """
        Check saved sorting hints for a direct match.
        hints: {item_name_lower: category_name}
        """
        item_lower = item_name.lower().strip()
        hint_cat_name = hints.get(item_lower)
        if hint_cat_name:
            # Find the category by name (case-insensitive)
            for cat in categories:
                if cat["name"].lower().strip() == hint_cat_name.lower().strip():
                    return {"category": cat, "confidence": 0.98}
        return None

    def _text_prematch(self, item_name: str, categories: list[dict]) -> Optional[dict]:
        """
        Try simple text matching before falling back to embeddings.
        """
        item_lower = item_name.lower().strip()
        for cat in categories:
            cat_lower = cat["name"].lower().strip()
            if item_lower in cat_lower or cat_lower in item_lower:
                return {"category": cat, "confidence": 0.95}
        return None

    def auto_sort(
        self,
        items: list[dict],
        categories: list[dict],
        hints: Optional[dict] = None,
        threshold: float = 0.25,
    ) -> list[dict]:
        """
        Match items to categories using:
        1. Saved user hints (highest priority)
        2. Text pre-matching (substring)
        3. Semantic similarity (fallback)

        hints: {item_name_lower: category_name} from SortingHint table
        """
        if not self.model or not items or not categories:
            return []

        if hints is None:
            hints = {}

        assignments = []
        embedding_items = []

        # Step 1: Check saved hints, then text prematch
        for item in items:
            match = self._hint_match(item["name"], categories, hints)
            if not match:
                match = self._text_prematch(item["name"], categories)
            if match:
                assignments.append({
                    "item_id": item["id"],
                    "item_name": item["name"],
                    "category_id": match["category"]["id"],
                    "category_name": match["category"]["name"],
                    "confidence": match["confidence"],
                })
            else:
                embedding_items.append(item)

        # Step 2: Semantic matching for remaining items
        if embedding_items:
            item_names = [i["name"] for i in embedding_items]
            cat_names = [c["name"] for c in categories]

            item_embeddings = np.array(list(self.model.embed(item_names)))
            cat_embeddings = np.array(list(self.model.embed(cat_names)))

            item_norm = item_embeddings / np.linalg.norm(
                item_embeddings, axis=1, keepdims=True
            )
            cat_norm = cat_embeddings / np.linalg.norm(
                cat_embeddings, axis=1, keepdims=True
            )

            similarity = item_norm @ cat_norm.T

            for i, item in enumerate(embedding_items):
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

        item_id_order = {item["id"]: idx for idx, item in enumerate(items)}
        assignments.sort(key=lambda a: item_id_order.get(a["item_id"], 999))

        return assignments


ml_service = MLService()
