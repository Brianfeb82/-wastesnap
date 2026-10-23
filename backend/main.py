"""WasteSnap API — classifies waste items via vision AI and finds nearby recycling."""

import os
import base64
import httpx
from fastapi import FastAPI, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="WasteSnap API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = "qwen/qwen3.8-27b"  # free vision model on Groq

CLASSIFY_PROMPT = """You are a waste classification expert. Look at this image and respond ONLY with valid JSON, no markdown fences:
{
  "item": "<what the item is>",
  "category": "<one of: recyclable, compostable, landfill, hazardous, e-waste>",
  "material": "<primary material, e.g. PET plastic, glass, organic>",
  "instructions": "<one sentence: how to properly dispose of this item>",
  "confidence": <0.0 to 1.0>
}
If the image is unclear or not a waste item, set category to "unknown" and confidence to 0.0."""


class Classification(BaseModel):
    item: str
    category: str
    material: str
    instructions: str
    confidence: float


class ClassifyResponse(BaseModel):
    classification: Classification
    nearby: list[dict] | None = None


@app.post("/classify", response_model=ClassifyResponse)
async def classify_waste(
    image: UploadFile = File(...),
    lat: float | None = Query(None),
    lon: float | None = Query(None),
):
    img_bytes = await image.read()
    b64 = base64.b64encode(img_bytes).decode()
    mime = image.content_type or "image/jpeg"

    # Vision classification via Groq
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            json={
                "model": GROQ_MODEL,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": CLASSIFY_PROMPT},
                            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                        ],
                    }
                ],
                "temperature": 0.1,
                "max_tokens": 300,
            },
        )
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"]

    # Parse JSON from response (strip markdown fences if model adds them anyway)
    import json
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0]
    classification = Classification(**json.loads(cleaned))

    # Find nearby recycling/waste facilities via Overpass
    nearby = None
    if lat is not None and lon is not None:
        nearby = await _find_nearby(lat, lon, classification.category)

    return ClassifyResponse(classification=classification, nearby=nearby)


async def _find_nearby(lat: float, lon: float, category: str) -> list[dict]:
    """Query OpenStreetMap Overpass for recycling/waste facilities within 5km."""
    # ponytail: hardcoded radius 5km, make configurable when needed
    amenity_filter = {
        "recyclable": 'node["amenity"="recycling"](around:5000,{lat},{lon});',
        "hazardous": 'node["recycling_type"="centre"](around:5000,{lat},{lon});',
        "e-waste": 'node["recycling:small_appliances"="yes"](around:5000,{lat},{lon});node["recycling:electrical_items"="yes"](around:5000,{lat},{lon});',
        "compostable": 'node["amenity"="recycling"]["recycling:green_waste"="yes"](around:5000,{lat},{lon});node["landuse"="allotments"](around:5000,{lat},{lon});',
    }
    query_body = amenity_filter.get(category, 'node["amenity"="recycling"](around:5000,{lat},{lon});')
    query_body = query_body.format(lat=lat, lon=lon)

    overpass_query = f"[out:json][timeout:10];({query_body});out body 5;"

    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.post(
                "https://overpass-api.de/api/interpreter",
                data={"data": overpass_query},
            )
            resp.raise_for_status()
            elements = resp.json().get("elements", [])
        except Exception:
            return []

    results = []
    for el in elements[:5]:
        tags = el.get("tags", {})
        results.append({
            "name": tags.get("name", "Recycling Point"),
            "lat": el["lat"],
            "lon": el["lon"],
            "distance_m": _haversine(lat, lon, el["lat"], el["lon"]),
            "type": tags.get("amenity", tags.get("recycling_type", "unknown")),
        })
    results.sort(key=lambda x: x["distance_m"])
    return results


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> int:
    """Distance in meters between two coordinates."""
    import math
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return int(R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))


@app.get("/health")
async def health():
    return {"status": "ok"}
