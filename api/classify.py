"""Vercel serverless function: POST /api/classify — waste classification via Groq vision."""

import os
import base64
import json
import math
from http.client import HTTPSConnection
from urllib.parse import urlencode

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = "qwen/qwen3.8-27b"

CLASSIFY_PROMPT = """You are a waste classification expert. Look at this image and respond ONLY with valid JSON, no markdown fences:
{
  "item": "<what the item is>",
  "category": "<one of: recyclable, compostable, landfill, hazardous, e-waste>",
  "material": "<primary material, e.g. PET plastic, glass, organic>",
  "instructions": "<one sentence: how to properly dispose of this item>",
  "confidence": <0.0 to 1.0>
}
If the image is unclear or not a waste item, set category to "unknown" and confidence to 0.0."""


def _groq_classify(b64: str, mime: str) -> dict:
    """Call Groq vision API using stdlib only (no httpx/requests on Vercel python runtime)."""
    body = json.dumps({
        "model": GROQ_MODEL,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": CLASSIFY_PROMPT},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
            ],
        }],
        "temperature": 0.1,
        "max_tokens": 300,
    })
    conn = HTTPSConnection("api.groq.com", timeout=30)
    conn.request("POST", "/openai/v1/chat/completions", body=body, headers={
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    })
    resp = conn.getresponse()
    data = json.loads(resp.read())
    conn.close()
    if resp.status != 200:
        raise Exception(f"Groq API error {resp.status}: {data}")
    raw = data["choices"][0]["message"]["content"]
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(cleaned)


def _find_nearby(lat: float, lon: float, category: str) -> list:
    """Query Overpass API for nearby recycling facilities."""
    filters = {
        "recyclable": f'node["amenity"="recycling"](around:5000,{lat},{lon});',
        "hazardous": f'node["recycling_type"="centre"](around:5000,{lat},{lon});',
        "e-waste": f'node["recycling:small_appliances"="yes"](around:5000,{lat},{lon});node["recycling:electrical_items"="yes"](around:5000,{lat},{lon});',
        "compostable": f'node["amenity"="recycling"]["recycling:green_waste"="yes"](around:5000,{lat},{lon});',
    }
    query_body = filters.get(category, f'node["amenity"="recycling"](around:5000,{lat},{lon});')
    overpass_query = f"[out:json][timeout:10];({query_body});out body 5;"

    conn = HTTPSConnection("overpass-api.de", timeout=15)
    encoded = urlencode({"data": overpass_query})
    conn.request("POST", "/api/interpreter", body=encoded, headers={
        "Content-Type": "application/x-www-form-urlencoded",
    })
    resp = conn.getresponse()
    if resp.status != 200:
        return []
    elements = json.loads(resp.read()).get("elements", [])
    conn.close()

    results = []
    for el in elements[:5]:
        tags = el.get("tags", {})
        results.append({
            "name": tags.get("name", "Recycling Point"),
            "lat": el["lat"],
            "lon": el["lon"],
            "distance_m": _haversine(lat, lon, el["lat"], el["lon"]),
            "type": tags.get("amenity", "unknown"),
        })
    results.sort(key=lambda x: x["distance_m"])
    return results


def _haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return int(R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))


def _parse_multipart(body: bytes, content_type: str):
    """Minimal multipart/form-data parser — extract first file field."""
    boundary = content_type.split("boundary=")[1].strip()
    if boundary.startswith('"'):
        boundary = boundary.strip('"')
    parts = body.split(f"--{boundary}".encode())
    for part in parts:
        if b"filename=" not in part:
            continue
        # Extract content type
        mime = "image/jpeg"
        if b"Content-Type:" in part:
            ct_line = part.split(b"Content-Type:")[1].split(b"\r\n")[0].strip()
            mime = ct_line.decode()
        # File data starts after double CRLF
        file_data = part.split(b"\r\n\r\n", 1)[1]
        if file_data.endswith(b"\r\n"):
            file_data = file_data[:-2]
        return file_data, mime
    return None, None


def handler(request):
    """Vercel serverless handler."""
    from http.server import BaseHTTPRequestHandler
    import io

    # CORS preflight
    if request.method == "OPTIONS":
        return _response(200, "", {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "*",
        })

    if request.method != "POST":
        return _response(405, json.dumps({"error": "POST only"}))

    try:
        content_type = request.headers.get("content-type", "")
        body = request.body

        if "multipart/form-data" not in content_type:
            return _response(400, json.dumps({"error": "Send multipart/form-data with image field"}))

        file_data, mime = _parse_multipart(body, content_type)
        if file_data is None:
            return _response(400, json.dumps({"error": "No image file found in request"}))

        b64 = base64.b64encode(file_data).decode()

        # Classify
        classification = _groq_classify(b64, mime)

        # Nearby facilities
        nearby = None
        query = dict(request.query) if hasattr(request, 'query') else {}
        # Parse query params from URL
        if hasattr(request, 'url'):
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(request.url)
            query = parse_qs(parsed.query)

        lat = query.get("lat", [None])[0] if isinstance(query.get("lat"), list) else query.get("lat")
        lon = query.get("lon", [None])[0] if isinstance(query.get("lon"), list) else query.get("lon")

        if lat and lon:
            nearby = _find_nearby(float(lat), float(lon), classification.get("category", ""))

        result = {"classification": classification, "nearby": nearby}
        return _response(200, json.dumps(result))

    except Exception as e:
        return _response(500, json.dumps({"error": str(e)}))


def _response(status, body, extra_headers=None):
    headers = {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
    }
    if extra_headers:
        headers.update(extra_headers)

    class Response:
        def __init__(self, s, b, h):
            self.status_code = s
            self.body = b
            self.headers = h

    return Response(status, body, headers)
