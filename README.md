# Ednex AI Presenter

Upload a deck, point it at your knowledge base; get a tireless presenter that pitches and handles Q&A — on screen now, on a robot later.

## Prerequisites

- Python 3.10+
- Node.js 20+

## Setup

### 1. Environment variables

```bash
cp .env.example .env
# Fill in OPENAI_API_KEY and ELEVENLABS_API_KEY
```

### Text-to-speech provider

OpenAI TTS is the default for human-like narration previews and packaged Show File audio:

```bash
TTS_PROVIDER=openai
OPENAI_TTS_MODEL=gpt-4o-mini-tts
OPENAI_TTS_VOICE=marin
OPENAI_TTS_TIMEOUT_SECONDS=12
OPENAI_TTS_MAX_RETRIES=0
```

Good built-in voices to try: `marin`, `cedar`, `coral`, `nova`, `shimmer`.

For offline/dev fallback, use free local TTS:

```bash
TTS_PROVIDER=free-local
sudo apt install espeak-ng
```

Packaging renders audio for every approved script segment, so OpenAI TTS can take a little time on larger decks. If OpenAI TTS times out or fails once during packaging, the app falls back to local TTS for the remaining segments so the Show File still completes. For fastest local testing, set `TTS_PROVIDER=free-local`.

### 2. Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Frontend

```bash
cd frontend
npm install
```

## Run

### Backend (API server)

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload
```

API available at `http://localhost:8000` — health check: `GET /health`

### Frontend (dev server)

```bash
cd frontend
npm run dev
```

UI available at `http://localhost:5173`

## Kill Busy Ports And Rerun

If the backend or frontend says the port is already in use, kill the process on that port and start it again.

### Backend port `8000`

```bash
sudo lsof -ti:8000 | xargs -r kill -9
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload
```

### Frontend port `5173`

```bash
sudo lsof -ti:5173 | xargs -r kill -9
cd frontend
npm run dev
```

### One-liner for both

```bash
sudo lsof -ti:8000,5173 | xargs -r kill -9
npm run dev # from Root
```

## Test

### Backend

```bash
cd backend
source .venv/bin/activate
pytest tests/ -v
```

### Frontend

```bash
cd frontend
npm test
```
