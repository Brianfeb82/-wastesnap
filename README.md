# WasteSnap

**AI-powered waste classification with nearby recycling locations.**

Point your phone camera at any item → get instant classification (recyclable, compostable, landfill, hazardous, e-waste) → find the nearest drop-off point.

Built for [Arbiter Hacks V1](https://arbiter-hacks-v1.devpost.com/) — **Rethinking Waste** track.

## The Problem

Contamination from mis-sorted recyclables causes ~25% of collected recycling to end up in landfill. Most people want to recycle correctly but don't know their local rules or which bin an item belongs in.

**WasteSnap reduces contamination at the source** by giving instant, location-aware sorting guidance at the moment of disposal.

## How It Works

1. **Snap** — Take a photo of the item (camera or upload)
2. **Classify** — AI vision model identifies the item, material, and correct disposal category
3. **Locate** — OpenStreetMap finds nearby recycling centers and drop-off points
4. **Dispose** — Follow the instructions and map link

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Single-file HTML/JS PWA, TailwindCSS |
| Backend | Python FastAPI |
| AI Vision | Groq API (Llama 4 Scout — free tier) |
| Geolocation | Browser Geolocation API |
| Nearby Search | OpenStreetMap Overpass API (free) |
| Deployment | Vercel (frontend) + Render (backend) |

## Run Locally

```bash
# Backend
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
export GROQ_API_KEY="your-key-here"
uvicorn main:app --reload

# Frontend — just open index.html or serve it
cd frontend
python -m http.server 3000
```

Then open `http://localhost:3000` and set `localStorage.setItem('wastesnap_api', 'http://localhost:8000')` in the browser console.

## Deployment

### Backend (Render)
1. Push to GitHub
2. Connect repo to [Render](https://render.com)
3. Set environment variable `GROQ_API_KEY`
4. Deploy as Web Service using the Dockerfile

### Frontend (Vercel)
1. Set root directory to `frontend/`
2. Deploy — it's static HTML

After deploying, update `API_URL` in `index.html` to point to your Render backend URL.

## Waste Problem Statement

> Contamination from mis-sorted recyclables causes approximately 25% of collected recycling to be rejected and sent to landfill. The root cause is that correct disposal rules vary by municipality and material, and people lack accessible guidance at the point of disposal. WasteSnap addresses this by providing instant, AI-powered waste classification via smartphone camera, paired with location-aware routing to the nearest appropriate facility. Success would be measured by tracking classification accuracy (target: >85% on common household items) and user retention (repeat scans indicating habitual use).

## What's Next

- [ ] Offline mode with on-device TensorFlow.js model for common items
- [ ] Municipality-specific rules database (what's recyclable varies by city)
- [ ] Gamification — streak tracking, community impact stats
- [ ] Barcode scanning for packaged goods (UPC → material lookup)

## License

MIT
