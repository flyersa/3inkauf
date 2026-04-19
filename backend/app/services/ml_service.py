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

    def parse_voice_intent(
        self,
        transcript: str,
        context: dict,
        ollama_url: str,
        ollama_model: str,
    ) -> dict:
        """Convert a spoken transcript into a structured app command via gemma4."""
        if not ollama_url:
            raise RuntimeError("Ollama URL not configured")

        route = context.get("route") or "unknown"
        list_name = context.get("list_name") or ""
        list_id = context.get("list_id") or ""
        items_on_list = context.get("items") or []
        locale = context.get("locale") or "en"
        language_name = "German" if locale.startswith("de") else "English"

        items_ctx = (
            ", ".join(items_on_list[:50]) if items_on_list else "(no items)"
        )
        list_ctx = list_name if list_name else "(none)"

        schema = (
            '{"action": "create_list|add_items|check_item|uncheck_item|'
            'delete_item|clear_list|unknown", '
            '"list_name": "<for create_list>", '
            '"items": [{"name": "<item>", "quantity": "<qty or null>"}], '
            '"item_name": "<for check/uncheck/delete>", '
            '"message": "<short confirmation in the user\'s language>"}'
        )

        prompt = (
            f"You convert a voice transcript from a shopping-list app into a structured "
            f"command. Respond with JSON ONLY.\n\n"
            f"Allowed actions:\n"
            f"- create_list: user wants a new list. Use `list_name`.\n"
            f"- add_items: user wants to add one OR MORE items to the current list. "
            f"ALWAYS split a comma/and-separated sequence into multiple entries in "
            f"`items` (e.g. 'Pizza, Milch und zwei Eier' -> 3 entries). Each entry has "
            f"`name` and optional `quantity`.\n"
            f"- check_item: mark an existing item done. Use `item_name`; match "
            f"case-insensitively against the current items.\n"
            f"- uncheck_item: mark an existing item NOT done. Use `item_name`.\n"
            f"- delete_item: remove an existing item. Use `item_name`.\n"
            f"- clear_list: remove all items on the current list.\n"
            f"- unknown: anything else, including commands that can't be fulfilled in "
            f"the current context. Set `message` to a short explanation "
            f"in {language_name}.\n\n"
            f"Rules:\n"
            f"- Preserve the original language of item names; do not translate.\n"
            f"- Extract explicit quantities (e.g. '2 Milch' -> name=Milch, quantity='2'; "
            f"'500g Mehl' -> quantity='500g'). If no quantity, set quantity=null.\n"
            f"- `message` MUST be in {language_name}, one short sentence confirming what "
            f"you understood.\n"
            f"- If the user is on list_overview and tries to add/check/delete/clear "
            f"without first creating or opening a list, return action=unknown with a "
            f"message explaining they need to open a list first.\n"
            f"- For check/uncheck/delete, `item_name` should match an entry from the "
            f"current items list as closely as possible (handle German articles and "
            f"inflections).\n\n"
            f"Examples:\n"
            f'Transcript: "Füge Pizza, Toilettenpapier und Eiscreme hinzu"\n'
            f'-> {{"action":"add_items","items":[{{"name":"Pizza","quantity":null}},{{"name":"Toilettenpapier","quantity":null}},{{"name":"Eiscreme","quantity":null}}],"message":"3 Artikel hinzugefügt"}}\n'
            f'Transcript: "add pizza, toilet paper, ice cream"\n'
            f'-> {{"action":"add_items","items":[{{"name":"pizza","quantity":null}},{{"name":"toilet paper","quantity":null}},{{"name":"ice cream","quantity":null}}],"message":"Added 3 items"}}\n'
            f'Transcript: "zwei Liter Milch und drei Eier hinzufügen"\n'
            f'-> {{"action":"add_items","items":[{{"name":"Milch","quantity":"2 Liter"}},{{"name":"Eier","quantity":"3"}}],"message":"2 Artikel hinzugefügt"}}\n'
            f'Transcript: "Erstelle eine Liste namens Wochenende"\n'
            f'-> {{"action":"create_list","list_name":"Wochenende","message":"Liste \\"Wochenende\\" erstellt"}}\n'
            f'Transcript: "Milch ist erledigt"  (with Milch on the list)\n'
            f'-> {{"action":"check_item","item_name":"Milch","message":"Milch abgehakt"}}\n\n'
            f"Context:\n"
            f"- Current screen: {route}\n"
            f"- Current list: {list_ctx}\n"
            f"- Items on current list: {items_ctx}\n"
            f"- User's language: {language_name}\n\n"
            f"Transcript: \"{transcript}\"\n\n"
            f"Respond with JSON matching exactly this schema (omit fields that don't "
            f"apply to the chosen action):\n{schema}"
        )

        # Voice intent needs deterministic structured output; the OLLAMA_SAMPLING
        # defaults (temperature=1.0) are tuned for scan creativity and
        # occasionally make small models emit just <eos> on short commands.
        voice_sampling = {
            "temperature": 0.2,
            "top_p": 0.9,
            "top_k": 40,
            "num_ctx": 8192,
            "num_predict": 300,
        }
        resp = requests.post(
            f"{ollama_url}/api/chat",
            json={
                "model": ollama_model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                # Without think:false, reasoning-mode models (e.g. gemma4:e2b)
                # exhaust num_predict on hidden thinking and return empty content.
                "think": False,
                "format": "json",
                "keep_alive": OLLAMA_KEEP_ALIVE,
                "options": voice_sampling,
            },
            timeout=30,
        )
        resp.raise_for_status()
        raw = resp.json().get("message", {}).get("content", "")
        logger.info(f"Voice intent raw: {raw[:300]!r}")

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if not m:
                return {"action": "unknown", "message": "Sorry, I didn't get that."}
            data = json.loads(m.group())

        allowed = {"create_list", "add_items", "check_item", "uncheck_item",
                   "delete_item", "clear_list", "unknown"}
        action = str(data.get("action") or "unknown").strip()
        if action not in allowed:
            action = "unknown"

        result: dict = {
            "action": action,
            "message": str(data.get("message") or "").strip() or None,
        }
        if action == "create_list":
            result["list_name"] = str(data.get("list_name") or "").strip() or None
        elif action == "add_items":
            items = []
            for it in data.get("items") or []:
                if not isinstance(it, dict):
                    continue
                name = str(it.get("name") or "").strip()
                if not name:
                    continue
                qty = it.get("quantity")
                if qty is not None:
                    qstr = str(qty).strip()
                    qty = qstr if qstr and qstr.lower() != "null" else None
                items.append({"name": name, "quantity": qty})
            result["items"] = items
        elif action in ("check_item", "uncheck_item", "delete_item"):
            result["item_name"] = str(data.get("item_name") or "").strip() or None
        # clear_list / unknown need no extra fields
        return result

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

        # Give gemma an explicit target vocabulary in the user's language so it
        # doesn't default to English category names.
        is_german = language.lower().startswith("german") or language.lower().startswith("de")
        if is_german:
            cat_examples = (
                "Obst & Gemüse, Milchprodukte, Backwaren, Fleisch & Wurst, "
                "Getränke, Tiefkühl, Süßwaren, Haushalt, Sonstiges"
            )
        else:
            cat_examples = (
                "Produce, Dairy, Bakery, Meat, Beverages, Frozen, Sweets, "
                "Household, Other"
            )

        prompt = (
            "You are reading a shopping list from a photograph (handwritten or printed).\n\n"
            f"OUTPUT LANGUAGE FOR CATEGORIES: {language}. "
            f"Use category names like: {cat_examples}. "
            f"Do NOT translate the category names into English if the language is German.\n\n"
            "For every item literally visible on the list, output one JSON entry with:\n"
            "- `name`: the item as written, keeping its original language.\n"
            "- `quantity`: any quantity written next to the item (e.g. \"2x\", \"500g\", "
            "\"1 Liter\"); use null if none.\n"
            f"- `category`: a supermarket category written in {language}. Reuse the same "
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
                # num_predict bump: cloud-served models (e.g. gemma4:31b-cloud)
                # default to ~256 output tokens which truncates long lists.
                "options": {**OLLAMA_SAMPLING, "num_predict": 2048},
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

    def identify_item_from_image(
        self,
        image_bytes: bytes,
        language: str = "German",
        ollama_url: str = "",
        ollama_model: str = "qwen3.5:397b-cloud",
    ) -> dict:
        """Look at a photo of a single grocery item and return its name
        (supermarket-style) plus any obvious quantity. Returns
        ``{"name": str|None, "quantity": str|None}`` — ``name`` is None when
        no confident identification is possible so the caller can surface a
        friendly error."""
        if not ollama_url:
            raise RuntimeError("Ollama URL not configured")

        b64 = base64.b64encode(image_bytes).decode("ascii")
        is_german = language.lower().startswith("german") or language.lower().startswith("de")
        language_name = "German" if is_german else "English"

        prompt = (
            "You are looking at a photograph a user took of ONE grocery item they want to "
            "add to their shopping list. Identify the single most prominent product.\n\n"
            f"OUTPUT LANGUAGE: {language_name}. Use supermarket-style naming.\n\n"
            "Rules:\n"
            "- `name` is ONE short product name (max 3 words), e.g. \"Milch\", \"Joghurt Vanille\", "
            "\"Bananen\". No brand names unless nothing else identifies the product.\n"
            "- `quantity` is the package size or count if printed on the packaging (e.g. \"1L\", "
            "\"500g\", \"6 Stück\"); null if nothing obvious is visible.\n"
            "- If you can't identify a single grocery item with confidence, set name to null.\n"
            "- Never invent. Return null name rather than guessing.\n\n"
            "Respond with JSON ONLY in this exact shape:\n"
            '{"name": "<name-or-null>", "quantity": "<qty-or-null>"}'
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
                "options": {
                    "temperature": 0.1,
                    "top_p": 0.9,
                    "top_k": 40,
                    "num_ctx": 4096,
                    "num_predict": 200,
                },
            },
            timeout=60,
        )
        resp.raise_for_status()
        raw = resp.json().get("message", {}).get("content", "")
        logger.info(f"Item-photo raw output ({len(raw)} chars): {raw[:200]!r}")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if not m:
                return {"name": None, "quantity": None}
            data = json.loads(m.group())

        name = data.get("name")
        if name is not None:
            n = str(name).strip()
            name = n if n and n.lower() != "null" else None
        qty = data.get("quantity")
        if qty is not None:
            q = str(qty).strip()
            qty = q if q and q.lower() != "null" else None
        return {"name": name, "quantity": qty}

    def scan_fridge_from_image(
        self,
        image_bytes: bytes,
        language: str = "German",
        ollama_url: str = "",
        ollama_model: str = "qwen3.5:397b-cloud",
    ) -> dict:
        """Identify food items visible in a photograph of a refrigerator's
        contents. Returns the same shape as paper-list scan so the frontend
        preview modal can be reused, plus a `confidence` field per item."""
        if not ollama_url:
            raise RuntimeError("Ollama URL not configured")

        b64 = base64.b64encode(image_bytes).decode("ascii")

        is_german = language.lower().startswith("german") or language.lower().startswith("de")
        if is_german:
            cat_examples = (
                "Obst & Gemüse, Milchprodukte, Fleisch & Wurst, "
                "Getränke, Tiefkühl, Süßwaren, Sonstiges"
            )
        else:
            cat_examples = (
                "Produce, Dairy, Meat, Beverages, Frozen, Sweets, Other"
            )

        prompt = (
            "You are looking at a photograph of the inside of a refrigerator. "
            "List every food item you can identify, even partial ones.\n\n"
            f"OUTPUT LANGUAGE: {language}. Use {language} names for items and categories.\n\n"
            "For each item include:\n"
            "- `name`: supermarket-style name (e.g. \"Joghurt\", \"Salami\").\n"
            "- `quantity`: optional (e.g. \"1 pack\", \"6 eggs\"), use null if unclear.\n"
            "- `category`: one of the supermarket categories listed below.\n"
            "- `confidence`: one of \"high\", \"medium\", \"low\".\n\n"
            f"Suggested categories (pick the best fit, reuse across similar items): {cat_examples}.\n\n"
            "Rules:\n"
            "- Do NOT invent items. If unsure, use confidence=low, never omit the flag.\n"
            "- Focus on edible groceries. Skip empty containers and unidentifiable wrapped packages.\n"
            "- If the photo is not a fridge or the fridge is empty, return empty arrays.\n\n"
            "Respond with JSON ONLY in this exact shape:\n"
            '{"categories": ["<cat>", ...], '
            '"items": [{"name": "<item>", "quantity": "<qty-or-null>", '
            '"category": "<cat>", "confidence": "high|medium|low"}]}'
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
                "options": {
                    "temperature": 0.2,
                    "top_p": 0.9,
                    "top_k": 40,
                    "num_ctx": 8192,
                    "num_predict": 2000,
                },
            },
            timeout=180,
        )
        resp.raise_for_status()
        raw = resp.json().get("message", {}).get("content", "")
        logger.info(f"Fridge scan raw output ({len(raw)} chars): {raw[:400]!r}")

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
        seen_cats = {c.lower() for c in categories}
        cleaned_items = []
        for it in data.get("items") or []:
            if not isinstance(it, dict):
                continue
            name = str(it.get("name") or "").strip()
            if not name:
                continue
            qty = it.get("quantity")
            if qty is not None:
                qs = str(qty).strip()
                qty = qs if qs and qs.lower() != "null" else None
            cat = str(it.get("category") or "").strip() or None
            if cat and cat.lower() not in seen_cats:
                categories.append(cat)
                seen_cats.add(cat.lower())
            conf = str(it.get("confidence") or "medium").strip().lower()
            if conf not in ("high", "medium", "low"):
                conf = "medium"
            cleaned_items.append({"name": name, "quantity": qty, "category": cat, "confidence": conf})
        return {"categories": categories, "items": cleaned_items}

    # ------------------------------------------------------------------
    # Recipes
    # ------------------------------------------------------------------
    def _recipe_chat(
        self,
        ollama_url: str,
        ollama_model: str,
        prompt: str,
        timeout: int = 60,
        num_predict: int = 1500,
    ) -> dict:
        """Call Ollama chat API for recipe JSON. Uses deterministic sampling
        to keep structured output stable for small local models."""
        resp = requests.post(
            f"{ollama_url}/api/chat",
            json={
                "model": ollama_model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "think": False,
                "format": "json",
                "keep_alive": OLLAMA_KEEP_ALIVE,
                "options": {
                    "temperature": 0.4,
                    "top_p": 0.9,
                    "top_k": 40,
                    "num_ctx": 8192,
                    "num_predict": num_predict,
                },
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        raw = resp.json().get("message", {}).get("content", "")
        logger.info(f"Recipe raw ({len(raw)} chars): {raw[:300]!r}")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if not m:
                raise RuntimeError(f"Model returned non-JSON: {raw[:200]}")
            return json.loads(m.group())

    @staticmethod
    def _is_german(locale: str) -> bool:
        return (locale or "").lower().startswith("de")

    def generate_recipes_from_items(
        self,
        items_on_list: list[str],
        locale: str = "de",
        ollama_url: str = "",
        ollama_model: str = "gemma3:4b",
    ) -> dict:
        """Suggest 3-5 recipes that can be made primarily from items already on
        the list, listing missing items the user would still need to buy."""
        if not ollama_url:
            raise RuntimeError("Ollama URL not configured")
        if not items_on_list:
            return {"recipes": []}

        language = "German" if self._is_german(locale) else "English"
        items_str = ", ".join(items_on_list[:80])

        prompt = (
            "You are a home cook. Based on the ingredients ALREADY on the user's shopping list, "
            "suggest 3 concrete, named dishes they could cook. For each, return the complete "
            "recipe (ingredients + numbered preparation steps) in ONE response.\n\n"
            f"OUTPUT LANGUAGE: {language}. Use {language} names for recipes, ingredients, and steps.\n\n"
            "Rules:\n"
            "- Each recipe MUST use at least 2 items from the shopping list as main ingredients.\n"
            "- Include additional typical ingredients the recipe needs (oil, onion, garlic, "
            "spices, etc.) — those are what the user will add.\n"
            "- 5 to 10 ingredients per recipe.\n"
            "- 4 to 8 numbered preparation steps per recipe. Keep each step ONE short sentence.\n"
            "- Propose variety (don't return 3 pasta dishes).\n"
            "- Set `already_have` true if the ingredient is clearly on the list (case-insensitive, "
            "simple plural/singular). The server will re-verify.\n"
            "- Keep `description` to ONE short sentence.\n\n"
            f"CURRENT SHOPPING LIST:\n{items_str}\n\n"
            "Respond with JSON ONLY in this exact shape:\n"
            '{"recipes": [{"title": "...", "description": "...", "servings": <int>, '
            '"prep_time_minutes": <int-or-null>, "cook_time_minutes": <int-or-null>, '
            '"ingredients": [{"name": "...", "quantity": "<qty-or-null>", "already_have": true}], '
            '"steps": ["Step 1...", "Step 2...", "..."], "tips": "<short tip or empty>"}]}'
        )

        # Larger num_predict because each recipe now includes full steps.
        data = self._recipe_chat(ollama_url, ollama_model, prompt, timeout=120, num_predict=4000)
        already_on_list = {s.strip().lower() for s in items_on_list}

        def norm(n: str) -> str:
            return (n or "").strip().lower()

        recipes = []
        for r in data.get("recipes") or []:
            if not isinstance(r, dict):
                continue
            title = str(r.get("title") or "").strip()
            if not title:
                continue
            desc = str(r.get("description") or "").strip()
            try:
                servings = int(r.get("servings")) if r.get("servings") is not None else None
            except (TypeError, ValueError):
                servings = None
            try:
                prep = int(r.get("prep_time_minutes")) if r.get("prep_time_minutes") is not None else None
            except (TypeError, ValueError):
                prep = None
            try:
                cook = int(r.get("cook_time_minutes")) if r.get("cook_time_minutes") is not None else None
            except (TypeError, ValueError):
                cook = None
            tips = str(r.get("tips") or "").strip() or None

            ing_out = []
            for ing in r.get("ingredients") or []:
                if not isinstance(ing, dict):
                    continue
                name = str(ing.get("name") or "").strip()
                if not name:
                    continue
                qty = ing.get("quantity")
                if qty is not None:
                    qs = str(qty).strip()
                    qty = qs if qs and qs.lower() != "null" else None
                # Re-verify already_have server-side so we don't trust the model blindly
                have = norm(name) in already_on_list or any(
                    norm(name) in it or it in norm(name) for it in already_on_list
                )
                ing_out.append({"name": name, "quantity": qty, "already_have": bool(have)})

            steps_out = []
            for s in r.get("steps") or []:
                if isinstance(s, str):
                    ss = s.strip()
                    if ss:
                        steps_out.append(ss)

            recipes.append({
                "title": title,
                "description": desc,
                "servings": servings,
                "prep_time_minutes": prep,
                "cook_time_minutes": cook,
                "ingredients": ing_out,
                "steps": steps_out,
                "tips": tips,
            })
        return {"recipes": recipes}

    def generate_recipe_from_query(
        self,
        query: str,
        locale: str = "de",
        ollama_url: str = "",
        ollama_model: str = "gemma3:4b",
    ) -> dict:
        """Expand a free-text recipe request like 'Spaghetti bolognese für 4
        Personen' into a structured ingredient list."""
        if not ollama_url:
            raise RuntimeError("Ollama URL not configured")
        q = (query or "").strip()
        if not q:
            raise ValueError("Recipe query is empty")

        language = "German" if self._is_german(locale) else "English"

        prompt = (
            "You are a home cook. Given a free-text recipe request, return the complete recipe: "
            "ingredients the user needs to buy AND numbered preparation steps — all in ONE response.\n\n"
            f"OUTPUT LANGUAGE: {language}. Use {language} names for the recipe, ingredients, and steps.\n\n"
            "Rules:\n"
            "- If the user mentions a servings/persons count, reflect it in `servings` and scale "
            "quantities accordingly. Default to 2 servings if unspecified.\n"
            "- Ingredients: supermarket-level only (don't list salt/pepper/water unless genuinely needed).\n"
            "- Steps: 4 to 8 numbered preparation steps, each ONE short clear sentence.\n\n"
            f"USER REQUEST: \"{q}\"\n\n"
            "Respond with JSON ONLY in this shape:\n"
            '{"title": "...", "servings": <int>, "prep_time_minutes": <int-or-null>, '
            '"cook_time_minutes": <int-or-null>, '
            '"ingredients": [{"name": "...", "quantity": "<qty-or-null>"}], '
            '"steps": ["Step 1...", "Step 2...", "..."], '
            '"tips": "<short tip or empty>"}'
        )

        data = self._recipe_chat(ollama_url, ollama_model, prompt, timeout=90, num_predict=2500)
        title = str(data.get("title") or "").strip() or q
        servings = data.get("servings")
        try:
            servings = int(servings) if servings is not None else None
        except (TypeError, ValueError):
            servings = None
        try:
            prep = int(data.get("prep_time_minutes")) if data.get("prep_time_minutes") is not None else None
        except (TypeError, ValueError):
            prep = None
        try:
            cook = int(data.get("cook_time_minutes")) if data.get("cook_time_minutes") is not None else None
        except (TypeError, ValueError):
            cook = None
        tips = str(data.get("tips") or "").strip() or None

        ing_out = []
        for ing in data.get("ingredients") or []:
            if not isinstance(ing, dict):
                continue
            name = str(ing.get("name") or "").strip()
            if not name:
                continue
            qty = ing.get("quantity")
            if qty is not None:
                qs = str(qty).strip()
                qty = qs if qs and qs.lower() != "null" else None
            ing_out.append({"name": name, "quantity": qty})

        steps_out = []
        for s in data.get("steps") or []:
            if isinstance(s, str):
                ss = s.strip()
                if ss:
                    steps_out.append(ss)

        return {
            "title": title,
            "servings": servings,
            "prep_time_minutes": prep,
            "cook_time_minutes": cook,
            "ingredients": ing_out,
            "steps": steps_out,
            "tips": tips,
        }

    def generate_full_recipe(
        self,
        title: str,
        locale: str = "de",
        servings: Optional[int] = None,
        existing_ingredients: Optional[list[dict]] = None,
        ollama_url: str = "",
        ollama_model: str = "gemma3:4b",
    ) -> dict:
        """Expand a recipe title into a full recipe: ingredients (with qty),
        numbered preparation steps, and timing info."""
        if not ollama_url:
            raise RuntimeError("Ollama URL not configured")
        t = (title or "").strip()
        if not t:
            raise ValueError("Recipe title is empty")

        language = "German" if self._is_german(locale) else "English"
        context_block = ""
        if existing_ingredients:
            names = [i.get("name") for i in existing_ingredients if isinstance(i, dict) and i.get("name")]
            if names:
                context_block = (
                    "\nThe user already plans these ingredients for the dish: "
                    + ", ".join(names[:30]) + ". Reconcile with them when possible.\n"
                )
        servings_hint = f"Target servings: {servings}." if servings else "If unspecified, plan for 2 servings."

        prompt = (
            "You are an experienced home cook. Expand the recipe title into a complete recipe.\n\n"
            f"OUTPUT LANGUAGE: {language}. Use {language} names for ingredients and steps.\n\n"
            f"RECIPE TITLE: {t}\n{context_block}\n"
            f"{servings_hint}\n\n"
            "Return JSON ONLY in this exact shape:\n"
            '{"title": "...", "servings": <int>, "prep_time_minutes": <int-or-null>, '
            '"cook_time_minutes": <int-or-null>, '
            '"ingredients": [{"name": "...", "quantity": "<qty-or-null>"}], '
            '"steps": ["Step 1...", "Step 2...", "..."], '
            '"tips": "<short tip or empty>"}\n\n'
            "Rules:\n"
            "- Steps must be a numbered sequence of clear, short instructions (aim 4-10 steps).\n"
            "- Keep ingredient quantities scaled to the target servings.\n"
            "- Don't include salt/pepper/water as steps unless genuinely important.\n"
            "- No markdown, no explanations outside the JSON."
        )

        data = self._recipe_chat(ollama_url, ollama_model, prompt, timeout=90)

        out_title = str(data.get("title") or "").strip() or t
        try:
            out_servings = int(data.get("servings")) if data.get("servings") is not None else servings
        except (TypeError, ValueError):
            out_servings = servings
        try:
            prep = int(data.get("prep_time_minutes")) if data.get("prep_time_minutes") is not None else None
        except (TypeError, ValueError):
            prep = None
        try:
            cook = int(data.get("cook_time_minutes")) if data.get("cook_time_minutes") is not None else None
        except (TypeError, ValueError):
            cook = None
        tips = str(data.get("tips") or "").strip() or None

        ing_out = []
        for ing in data.get("ingredients") or []:
            if not isinstance(ing, dict):
                continue
            name = str(ing.get("name") or "").strip()
            if not name:
                continue
            qty = ing.get("quantity")
            if qty is not None:
                qs = str(qty).strip()
                qty = qs if qs and qs.lower() != "null" else None
            ing_out.append({"name": name, "quantity": qty})

        steps_out = []
        for s in data.get("steps") or []:
            if isinstance(s, str):
                ss = s.strip()
                if ss:
                    steps_out.append(ss)

        return {
            "title": out_title,
            "servings": out_servings,
            "prep_time_minutes": prep,
            "cook_time_minutes": cook,
            "ingredients": ing_out,
            "steps": steps_out,
            "tips": tips,
        }


ml_service = MLService()
