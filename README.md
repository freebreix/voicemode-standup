# voicemode-standup

Native-Windows [VoiceMode](https://github.com/mbailey/voicemode) stack tuned for
**many Claude Code sessions at once** — parallel agents take turns on the mic and
each one gets its own voice, with zero per-project config.

Built on:
- **[mbailey/voicemode](https://github.com/mbailey/voicemode)** — the MCP voice server (pinned `voice-mode==8.12.0`, wrapped, not forked).
- **[Piper](https://github.com/OHF-Voice/piper1-gpl)** — the TTS voices. [`tts/`](tts/) is a small OpenAI-compatible server around them (started from [`ginto-sakata/local-openai-tts-server`](https://github.com/ginto-sakata/local-openai-tts-server), MIT; now a rewrite — tracked source, no fork).
- **[ggml-org/whisper.cpp](https://github.com/ggml-org/whisper.cpp)** — CUDA `whisper-server` for STT (prebuilt release, unmodified).

## What it adds over stock VoiceMode

Stock VoiceMode already has the "conch" (a lock so only one agent speaks at a
time) and can record the speaking voice — but you have to opt in per call, and it
never picks distinct voices. `voicemode-standup` makes it automatic:

| | stock voicemode | voicemode-standup |
|---|---|---|
| 2nd agent speaks while 1st holds the floor | bounced ("try again") unless the agent passed `wait_for_conch=true` | **queues automatically**, speaks when it's their turn |
| Q/A pair cut into at the turn boundary | possible | `hold_conch` set automatically when a reply is expected |
| voice per session | same default for everyone | **stable distinct speaker per session**, chosen by the TTS server (per detected language) |
| Windows | WSL / Linux installers | native: Piper + whisper.cpp CUDA, one `install.ps1` |
| language | one | any set you list (`TTS_LANGUAGES`); detected per utterance (lingua), each with its own speaker pool; voices lazy-download |

## Architecture

```
 Claude session A ─┐                        ┌─ shim/.venv python -m voicemode_standup  (stdio MCP, per session)
 Claude session B ─┼─ each spawns its own ──┤     └ patches converse: wait_for_conch, hold_conch,
 Claude session C ─┘                        │        voice = "auto:<session id>"
                                            │
   shared file lock  ~/.voicemode/conch  ◄──┘   (turn-taking across the separate processes)
                                            │
              ┌─────────────────────────────┴───────────────┐
        TTS :8880  (tts/, Piper, scheduled task)     STT :2022  (whisper.cpp CUDA, scheduled task)
        └ detects utterance language, then hands each session a stable speaker
          from that language's pool (shares once the pool is exhausted)
```

Only **two** background services (TTS, STT). The MCP server is **not** a daemon —
each Claude session launches its own via stdio, which is what makes
`CLAUDE_CODE_SESSION_ID` available so voices stay stable per session. The
`~/.voicemode/conch` lock file coordinates turn-taking across those separate
processes.

## Install

```powershell
git clone https://github.com/freebreix/voicemode-standup C:\RyzeCode\voicemode-standup
cd C:\RyzeCode\voicemode-standup
pwsh -File install.ps1          # -CpuOnly if no NVIDIA GPU
```

It fetches the pinned upstreams (`manifest.psd1`), creates the TTS venv, writes a
managed block into `~/.voicemode/voicemode.env`, registers the MCP server
(user scope) and the two Scheduled Tasks, and starts the services.

Then open a **fresh** Claude session — it picks up the `voicemode` MCP server and
the `converse` tool. Run several sessions side by side; they'll wait for each
other and sound different.

## Config

**Turn-taking + session voice** — managed block of `~/.voicemode/voicemode.env`:

| var | default | meaning |
|---|---|---|
| `VOICEMODE_STANDUP_AUTOVOICE` | `true` | default `voice="auto:<session id>"` on every `converse` |
| `VOICEMODE_STANDUP_AUTOWAIT` | `true` | default `wait_for_conch=true` on every `converse` |
| `VOICEMODE_STANDUP_AUTOHOLD` | `true` | default `hold_conch=true` when a reply is expected |
| `VOICEMODE_CONCH_TIMEOUT` | `600` | how long a queued session waits for the floor |

An explicit `voice=` / `wait_for_conch=` / `hold_conch=` argument from the agent
always overrides the shim.

**Languages + voices** — `tts/config.env` (from `config/tts.config.env.template`):

| var | default | meaning |
|---|---|---|
| `TTS_LANGUAGES` | `en,hu` | ordered; `[0]` is the primary/fallback language. Detection (lingua) is built lazily from this list; a single language skips detection |
| `PREFERRED_QUALITY` | `medium` | first-pick Piper voice quality (`x_low`/`low`/`medium`/`high`); nearest available is used otherwise |
| `ENABLED_PIPER_VOICES_<LANG>` | all defined | per-language speaker allow-list (bare names or `<name>-<quality>`). This is the pool sessions are assigned from |

Voices download from HuggingFace on first use. A language with no voice, or one
lingua can't distinguish from the others, is reported at
`GET http://127.0.0.1:8880/v1/health` (`status: "error"`) and logged `CRITICAL`;
the server still serves whatever is usable.

## Layout

```
install.ps1          idempotent installer / repair
update.ps1           refresh deps + re-merge env block after a manifest bump
manifest.psd1        pinned versions (whisper.cpp tag, voice-mode pin, python)
scripts/             _paths, _guard, start-tts, start-whisper, start-all, stop-all, register-tasks
shim/                voicemode_standup - the converse wrapper + pinned voice-mode
config/              tts config template, voicemode.env managed block
tts/                 the Piper TTS server (tracked); .venv/ + piper_models/ + config.env gitignored
whisper/    (gitignored)  bin-cuda/, bin/, models/
```

## License

MIT. Upstreams keep their own licenses (voicemode MIT, whisper.cpp MIT, Piper
MIT; Piper/whisper model weights have their own terms).
