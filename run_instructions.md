# Run Instructions — Ednex AI Presenter

## Prerequisites

| Tool | Version |
|---|---|
| Python | 3.10+ |
| Node.js | 20+ |
| npm | 9+ |
| ffmpeg | any (required by pydub for audio resampling) |

Install ffmpeg if not already present:
```bash
sudo apt install ffmpeg
```

---

## First-Time Setup (do once)

### 1. Environment file

```bash
cp .env.example backend/.env
```

Open `backend/.env` and fill in the required values:

```
OPENAI_API_KEY=sk-...         # required — used for LLM, TTS, embeddings
ELEVENLABS_API_KEY=...        # optional — only if using ElevenLabs TTS
```

### 2. Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Frontend

```bash
cd frontend
npm install
```

### 4. Root dev tooling

```bash
npm install        # from project root — installs concurrently
```

---

## Modes

### Mode A — PC mode (default, no robot)

Audio plays through your browser. No Unitree SDK calls are made.

**`.env` settings (nothing extra needed):**
```
ROBOT_ENABLED=false    # or just leave it out
```

**Start:**
```bash
# From project root — starts both backend + frontend together
npm run dev
```

Backend: `http://localhost:8000`
Frontend: `http://localhost:5173`

---

### Mode B — Robot mode (Unitree G1)

Audio streams to the G1's built-in speaker via `PlayStream`. The browser stays open as the control panel but is silent. LED strip reflects presenter state (green = speaking, blue = Q&A, red = error).

#### Before starting

**Step 1 — Find your NIC name**
```bash
ip link show
```
Look for the interface connected to the robot (e.g. `enp3s0`, `eth0`, `eno1`).

**Step 2 — Set a static IP on that interface**
```bash
sudo ip addr add 192.168.123.100/24 dev enp3s0
```
The G1 expects your PC to be in the `192.168.123.x` subnet.

**Step 3 — Power on the G1 and connect Ethernet**
Connect the Ethernet cable between your PC and the robot's LAN port.

**Step 4 — Update `.env`**
```
ROBOT_ENABLED=true
ROBOT_NETWORK_INTERFACE=enp3s0   # your actual NIC name from Step 1
ROBOT_VOLUME=100                 # 0–100
ROBOT_PCM_GAIN=2.0               # software amplification: 1.0=none, 2.0=double, 3.0=max
```

**Start:**
```bash
npm run dev
```

Check the backend terminal for:
```
RobotBridge: initializing DDS on interface 'enp3s0'
RobotBridge: ready (volume=100, gain=2.0)
```

When a presentation session starts, you'll also see:
```
RobotBridge: attached to session bus
```

The presenter control panel shows a **🤖 Robot** badge in the header when robot mode is active.

---

## Running — Quick Reference

### One command (recommended)

From the **project root**:
```bash
npm run dev
```
This kills any existing processes on ports 8000 and 5173, then starts backend + frontend concurrently.

### Separate terminals

**Terminal 1 — Backend:**
```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload
```

**Terminal 2 — Frontend:**
```bash
cd frontend
npm run dev
```

### Activate venv (any time you open a new terminal for backend work)
```bash
source backend/.venv/bin/activate
```

---

## Port Conflicts

If ports are already in use:

```bash
# Kill both ports and restart
sudo lsof -ti:8000,5173 | xargs -r kill -9
npm run dev
```

Individual ports:
```bash
sudo lsof -ti:8000 | xargs -r kill -9   # backend
sudo lsof -ti:5173 | xargs -r kill -9   # frontend
```

---

## Key URLs

| URL | What |
|---|---|
| `http://localhost:5173` | Presenter UI |
| `http://localhost:8000/health` | Backend health check |
| `http://localhost:8000/docs` | Auto-generated API docs (Swagger) |

---

## TTS Provider Options

Set in `backend/.env`:

**OpenAI TTS (default — best quality):**
```
TTS_PROVIDER=openai
OPENAI_TTS_MODEL=gpt-4o-mini-tts
OPENAI_TTS_VOICE=marin
```
Other good voices: `cedar`, `coral`, `nova`, `shimmer`

**Free local TTS (offline, faster for dev):**
```
TTS_PROVIDER=free-local
```
Requires: `sudo apt install espeak-ng`

> When packaging a Show File, OpenAI TTS generates audio for every script segment. On large decks this takes time. Use `free-local` for fastest iteration during development.

---

## Robot Volume Tuning

The G1 speaker is 8Ω 3W (5W peak). Two knobs:

| Setting | Effect |
|---|---|
| `ROBOT_VOLUME=100` | System volume via SDK (0–100). Always set to 100 first. |
| `ROBOT_PCM_GAIN=2.0` | Software PCM amplification before streaming. `1.0` = unchanged, `2.0` = double amplitude, `3.0` = max (may clip on loud audio). |

Start with `ROBOT_PCM_GAIN=2.0`. If still quiet, try `3.0`. If speech sounds distorted, drop back to `1.5`.

---

## Test SDK Examples (without the full presenter)

These run standalone against the G1 directly:

```bash
cd unitree_sdk2_python

# Get/set volume and brightness (Go2-style VUI — also works on G1)
python3 example/vui_client/vui_client_example.py enp3s0

# G1 audio: TTS, LED, volume, WAV playback
python3 example/g1/audio/g1_audio_client_example.py enp3s0

# G1 audio: play a WAV file
python3 example/g1/audio/g1_audio_client_play_wav.py enp3s0 path/to/file.wav

# G1 locomotion: walk, wave, etc.
python3 example/g1/high_level/g1_loco_client_example.py enp3s0
```

Replace `enp3s0` with your NIC name.

---

## Run Tests

**Backend:**
```bash
cd backend
source .venv/bin/activate
pytest tests/ -v
```

**Frontend:**
```bash
cd frontend
npm test
```
