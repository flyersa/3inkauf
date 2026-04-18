import base64
import json
import re
import logging
import numpy as np
import requests
from typing import Optional

logger = logging.getLogger(__name__)

# Per the gemma4 model card, the authors recommend these sampling parameters
# across all use cases. We apply them to every Ollama call so the same tuning
# is used for auto-sort and for paper-list scans.
OLLAMA_SAMPLING = {
    "temperature": 1.0,
    "top_p": 0.95,
    "top_k": 64,
    # 8K context is plenty for our prompts and leaves VRAM headroom for KV cache
    # on small GPUs (e.g. RTX A2000 12GB running a 9.6GB model).
    "num_ctx": 8192,
}

# Keep the model resident in VRAM between requests. We're the only model on
# the Ollama host so we can afford a long keep-alive and avoid cold reloads.
OLLAMA_KEEP_ALIVE = "1h"


class MLService:
    def __init__(self):
        self.model = None

    def load_model(self, model_name: str):
        """Load the fastembed model. Called once at app startup."""
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
        """Check saved sorting hints for a direct match."""
        item_lower = item_name.lower().strip()
        hint_cat_name = hints.get(item_lower)
        if hint_cat_name:
            for cat in categories:
                if cat["name"].lower().strip() == hint_cat_name.lower().strip():
                    return {"category": cat, "confidence": 0.98}
        return None

    def _text_prematch(self, item_name: str, categories: list[dict]) -> Optional[dict]:
        """Try simple text matching (substring)."""
        item_lower = item_name.lower().strip()
        for cat in categories:
            cat_lower = cat["name"].lower().strip()
            if item_lower in cat_lower or cat_lower in item_lower:
                return {"category": cat, "confidence": 0.95}
        return None

    def auto_sort_simple(
        self,
        items: list[dict],
        categories: list[dict],
        hints: Optional[dict] = None,
        threshold: float = 0.25,
    ) -> list[dict]:
        """Simple mode: hints -> substring -> fastembed embeddings."""
        if not self.model or not items or not categories:
            return []
        if hints is None:
            hints = {}

        assignments = []
        embedding_items = []

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

        if embedding_items:
            item_names = [i["name"] for i in embedding_items]
            cat_names = [c["name"] for c in categories]

            item_embeddings = np.array(list(self.model.embed(item_names)))
            cat_embeddings = np.array(list(self.model.embed(cat_names)))

            item_norm = item_embeddings / np.linalg.norm(item_embeddings, axis=1, keepdims=True)
            cat_norm = cat_embeddings / np.linalg.norm(cat_embeddings, axis=1, keepdims=True)
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

    def auto_sort_advanced(
        self,
        items: list[dict],
        categories: list[dict],
        hints: Optional[dict] = None,
        ollama_url: str = "",
        ollama_model: str = "gemma3:4b",
    ) -> list[dict]:
        """Advanced mode: hints -> substring -> Ollama LLM for remaining items."""
        if not items or not categories:
            return []
        if hints is None:
            hints = {}

        assignments = []
        llm_items = []

        # Step 1: hints + prematch first (instant, free)
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
                llm_items.append(item)

        # Step 2: send remaining items to Ollama (chat API)
        if llm_items and ollama_url:
            cat_names = [c["name"] for c in categories]
            cat_map = {}
            for c in categories:
                cat_map[c["name"].lower().strip()] = c

            item_names = [i["name"] for i in llm_items]
            cat_list = "\n".join(f"- {c}" for c in cat_names)

            try:
                resp = requests.post(
                    f"{ollama_url}/api/chat",
                    json={
                        "model": ollama_model,
                        "messages": [
                            {
                                "role": "system",
                                "content": "You sort shopping list items into categories. Reply ONLY with a JSON array. No other text.",
                            },
                            {
                                "role": "user",
                                "content": f"Sort these items into the categories below. Each item must be assigned to exactly one category. Use ONLY the exact category names provided.\n\nCATEGORIES:\n{cat_list}\n\nITEMS:\n{json.dumps(item_names)}\n\nReply: [{{\"item\": \"...\", \"category\": \"...\"}}]",
                            },
                        ],
                        "stream": False,
                        "think": False,
                        "keep_alive": OLLAMA_KEEP_ALIVE,
                        "options": OLLAMA_SAMPLING,
                    },
                    timeout=30,
                )
                resp.raise_for_status()
                raw = resp.json().get("message", {}).get("content", "")

                # Parse JSON array from response
                match = re.search(r'\[.*\]', raw, re.DOTALL)
                if match:
                    result = json.loads(match.group())
                    item_lookup = {i["name"].lower().strip(): i for i in llm_items}

                    for r in result:
                        r_item = r.get("item", "").strip()
                        r_cat = r.get("category", "").strip()
                        item = item_lookup.get(r_item.lower().strip())
                        cat = cat_map.get(r_cat.lower().strip())
                        if item and cat:
                            assignments.append({
                                "item_id": item["id"],
                                "item_name": item["name"],
                                "category_id": cat["id"],
                                "category_name": cat["name"],
                                "confidence": 0.90,
                            })
                else:
                    logger.warning(f"Could not parse Ollama response: {raw[:200]}")
            except Exception as e:
                logger.error(f"Ollama request failed: {e}")

        item_id_order = {item["id"]: idx for idx, item in enumerate(items)}
        assignments.sort(key=lambda a: item_id_order.get(a["item_id"], 999))
        return assignments

    # Backward compat
    def auto_sort(self, items, categories, hints=None, threshold=0.25):
        return self.auto_sort_simple(items, categories, hints, threshold)

    def scan_list_from_image(
        self,
        image_bytes: bytes,
        language: str = "English",
        ollama_url: str = "",
        ollama_model: str = "gemma4:e4b",
    ) -> dict:
        """Single-pass scan: gemma4:e4b transcribes the photo AND assigns
        categories in one call. Much faster than two calls and accurate enough
        with a model this strong."""
        if not ollama_url:
            raise RuntimeError("Ollama URL not configured")

        b64 = base64.b64encode(image_bytes).decode("ascii")
        prompt = (
            "You are reading a shopping list from a photograph (handwritten or printed).\n\n"
            "For every item literally visible on the list, output one JSON entry with:\n"
            "- `name`: the item as written, keeping its original language.\n"
            "- `quantity`: any quantity written next to the item (e.g. \"2x\", \"500g\", "
            "\"1 Liter\"); use null if none.\n"
            f"- `category`: a supermarket category written in {language} — reuse the same "
            "category across similar items; aim for 4-8 categories total.\n\n"
            "Rules:\n"
            "- Do NOT add items that are not written in the photo.\n"
            "- Do NOT autocomplete, expand, or guess unclear words — skip them.\n"
            "- If the photo is not a shopping list or has no items, return empty arrays.\n\n"
            "Respond with JSON ONLY matching:\n"
            '{"categories": ["<cat>", ...], '
            '"items": [{"name": "<item>", "quantity": "<qty-or-null>", "category": "<cat>"}]}'
        )
        resp = requests.post(
            f"{ollama_url}/api/chat",
            json={
                "model": ollama_model,
                "messages": [{"role": "user", "content": prompt, "images": [b64]}],
                "stream": False,
                "think": False,
                "format": "json",
                "keep_alive": OLLAMA_KEEP_ALIVE,
                "options": OLLAMA_SAMPLING,
            },
            timeout=180,
        )
        resp.raise_for_status()
        raw = resp.json().get("message", {}).get("content", "")
        logger.info(f"Scan raw output ({len(raw)} chars): {raw[:400]!r}")

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if not m:
                raise RuntimeError(f"Model returned non-JSON: {raw[:200]}")
            data = json.loads(m.group())

        categories = [
            c.strip() for c in (data.get("categories") or [])
            if isinstance(c, str) and c.strip()
        ]
        cleaned_items = []
        seen_cats = set(c.lower() for c in categories)
        for it in data.get("items") or []:
            if not isinstance(it, dict):
                continue
            name = str(it.get("name") or "").strip()
            if not name:
                continue
            qty = it.get("quantity")
            if qty is not None:
                qty_str = str(qty).strip()
                qty = qty_str if qty_str and qty_str.lower() != "null" else None
            cat = str(it.get("category") or "").strip() or None
            if cat and cat.lower() not in seen_cats:
                categories.append(cat)
                seen_cats.add(cat.lower())
            cleaned_items.append({"name": name, "quantity": qty, "category": cat})
        return {"categories": categories, "items": cleaned_items}


ml_service = MLService()
