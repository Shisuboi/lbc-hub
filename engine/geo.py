"""Géocodage des villes via l'API BAN (gratuite, sans clé) + remplissage lat/lon.

Best-effort : tout échec (réseau, ville inconnue) laisse lat/lon absents — jamais bloquant.
Cache dans le Brain (table city_geo) pour ne géocoder chaque ville qu'une fois.
"""

BAN_URL = "https://api-adresse.data.gouv.fr/search/"


async def geocode_city(session, city: str):
    """Retourne (lat, lon) pour une ville via la BAN, ou None. Best-effort."""
    city = (city or "").strip()
    if not city:
        return None
    try:
        async with session.get(BAN_URL, params={"q": city, "limit": "1"}) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
        feats = data.get("features") or []
        if not feats:
            return None
        lon, lat = feats[0]["geometry"]["coordinates"]  # GeoJSON = [lon, lat]
        return (float(lat), float(lon))
    except Exception:
        return None


async def fill_latlon(brain, session, payload: dict) -> None:
    """Renseigne payload['lat']/['lon'] depuis la ville (cache Brain → BAN). In-place, best-effort."""
    city = payload.get("location_city")
    if not city:
        return
    cached = brain.get_city_geo(city)
    if cached is not None:
        lat, lon = cached
    else:
        geo = await geocode_city(session, city)
        if geo is None:
            return
        lat, lon = geo
        brain.set_city_geo(city, lat, lon)
    payload["lat"] = lat
    payload["lon"] = lon
