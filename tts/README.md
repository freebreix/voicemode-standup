# tts/ — Piper TTS server

Minimal OpenAI-compatible text-to-speech for [voicemode-standup](../README.md).
Piper only, no torch. Started from
[`ginto-sakata/local-openai-tts-server`](https://github.com/ginto-sakata/local-openai-tts-server)
(MIT); now a rewrite — see [`LICENSE`](LICENSE).

`install.ps1` in the repo root sets this up (venv + `config.env` from
`config/tts.config.env.template`) and runs it as a Scheduled Task on
`127.0.0.1:8880`. To run it by hand:

```powershell
uv venv --python 3.12 .venv
uv pip install --python .venv\Scripts\python.exe -r requirements.txt
copy ..\config\tts.config.env.template config.env
.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8880
```

## Endpoints

`POST /v1/audio/speech` · `GET /v1/audio/voices` · `GET /v1/models` ·
`GET /v1/health` (all also without `/v1`).

`/v1/audio/speech` body: `{"input": "...", "voice": "...", "response_format": "pcm"|"wav", "session_id": "..."}`.
`pcm` is raw mono int16 at 24 kHz (resampled from Piper's 22.05 kHz for VoiceMode's
streaming path).

## The `auto` voice

`voice: "auto"` (or omitted with `DEFAULT_VOICE=auto`) detects the utterance
language with [`lingua`](https://github.com/pemistahl/lingua-py) — a detector
built lazily from `TTS_LANGUAGES`, biased toward the first-listed "primary"
language so a short or weak signal never flips the voice — and picks a speaker
from that language's pool.

Pass `session_id` (or `voice: "auto:<id>"`) and each session keeps a stable,
distinct speaker until the pool is exhausted, after which sessions share one (no
error).

## Config (`config.env`)

| var | default | meaning |
|---|---|---|
| `TTS_LANGUAGES` | `en` | ordered; `[0]` is the primary/fallback language. One language skips detection. A language `lingua` has no model for can only be used alone. (`LANGUAGES` is an alias.) |
| `PREFERRED_QUALITY` | `medium` | first-pick Piper quality (`x_low`/`low`/`medium`/`high`); nearest available otherwise |
| `DEFAULT_VOICE` | — | voice used when a request omits one (`auto`, or a voice id) |
| `ENABLED_PIPER_VOICES_<LANG>` | all defined | per-language speaker allow-list: bare names (resolved via `PREFERRED_QUALITY`) or full `<name>-<quality>` ids. This is the pool `auto` assigns from |
| `DEVICE` | `cpu` | `cuda` loads voices with `use_cuda=True` (needs `onnxruntime-gpu`) |
| `TTS_CPU_THREADS` | `0` | >0 sets `OMP_NUM_THREADS` |

Misconfiguration (unknown language, no voice, no lingua model, bad
`PREFERRED_QUALITY`) is reported at `GET /v1/health`
(`{"status": "error", "errors": [...]}`) and logged `CRITICAL`; the server still
serves whatever is usable.

`voices_definitions.yaml` is the Piper voice catalogue
([`rhasspy/piper-voices`](https://github.com/rhasspy/piper-voices)) — data, edited
only to track new upstream voices. Models download from HuggingFace on first use
into `piper_models/`.
