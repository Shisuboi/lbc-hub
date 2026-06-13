"""Client REST Gemini (generateContent) — texte + vision, sortie JSON stricte.

Zéro nouvelle dépendance : aiohttp (déjà présent). Expose generate_json(...) tel
qu'attendu par engine.router.LLMRouter. La clé API passe en query param ?key=...
"""
import base64
import json

_DEFAULT_BASE = "https://generativelanguage.googleapis.com"


class GeminiClient:
    name = "gemini"

    def __init__(self, api_key: str, session, base_url: str = _DEFAULT_BASE):
        self.api_key = api_key
        self.session = session
        self.base = base_url.rstrip("/")

    async def generate_json(self, model_id: str, prompt: str, schema: dict, image_bytes=None):
        """Retourne (data: dict, token_count: int). Lève en cas d'erreur HTTP."""
        parts = [{"text": prompt}]
        if image_bytes:
            parts.append({
                "inline_data": {
                    "mime_type": "image/jpeg",
                    "data": base64.b64encode(image_bytes).decode("ascii"),
                }
            })
        body = {
            "contents": [{"parts": parts}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": schema,
            },
        }
        url = f"{self.base}/v1beta/models/{model_id}:generateContent"
        params = {"key": self.api_key}
        async with self.session.post(url, params=params, json=body) as resp:
            resp.raise_for_status()
            payload = await resp.json()
        text = payload["candidates"][0]["content"]["parts"][0]["text"]
        tokens = payload.get("usageMetadata", {}).get("totalTokenCount", 0)
        return json.loads(text), tokens

    async def generate_text(self, model_id: str, prompt: str, use_search: bool = False):
        """Génère du texte libre. Retourne (text: str, token_count: int). Lève en cas d'erreur HTTP.

        Si use_search=True, active l'outil Google Search natif de Gemini (grounding web). Dans ce
        mode, on N'IMPOSE PAS de responseSchema/JSON : la recherche groundée renvoie du texte libre
        (potentiellement en plusieurs `parts` qu'on concatène).
        """
        body: dict = {"contents": [{"parts": [{"text": prompt}]}]}
        if use_search:
            body["tools"] = [{"googleSearch": {}}]
        url = f"{self.base}/v1beta/models/{model_id}:generateContent"
        params = {"key": self.api_key}
        async with self.session.post(url, params=params, json=body) as resp:
            resp.raise_for_status()
            payload = await resp.json()
        parts = payload["candidates"][0]["content"].get("parts", [])
        text = "".join(p.get("text", "") for p in parts)
        tokens = payload.get("usageMetadata", {}).get("totalTokenCount", 0)
        return text, tokens
