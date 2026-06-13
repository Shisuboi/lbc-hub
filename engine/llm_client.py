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

