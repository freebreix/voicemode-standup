"""Minimal OpenAI-compatible TTS server (Piper only) for voicemode-standup.

Endpoints: POST /v1/audio/speech, GET /v1/audio/voices, /v1/models, /v1/health
(all also without the /v1 prefix).

The synthetic "auto" voice detects each utterance's language (lingua, built
lazily from TTS_LANGUAGES) and hands each caller session a stable, distinct
speaker from that language's pool. See detect_lang / resolve_auto_voice.

With STRICT_LANGUAGE on (default), an "auto" request in a language lingua
identifies as one NOT in TTS_LANGUAGES is rejected (HTTP 400) so the caller can
tell the user it isn't supported, rather than mis-voiced. See
unsupported_language.

Derived from ginto-sakata/local-openai-tts-server (MIT, inactive since 2025-04):
the OpenAI route shapes and the HuggingFace voice-download idea. Rewritten
Piper-only (no Silero, no torch) with per-session / per-language voice
selection, lazy model loading, and PCM output resampled for VoiceMode's
streaming path. See LICENSE.
"""
from __future__ import annotations

import hashlib
import io
import logging
import os
import re
import threading
import time
import wave

import numpy as np
import yaml
from dotenv import dotenv_values
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from huggingface_hub import hf_hub_download
from piper.voice import PiperVoice

try:
    import soxr
    SOXR_AVAILABLE = True
except ImportError:  # pragma: no cover
    SOXR_AVAILABLE = False

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("tts")

CONFIG_ENV_PATH = os.environ.get("TTS_CONFIG", "config.env")
VOICES_DEF_PATH = os.environ.get("TTS_VOICES_DEF", "voices_definitions.yaml")

# VoiceMode's streaming PCM path plays raw 16-bit mono at a hard-coded 24 kHz
# (voice_mode/streaming.py: SAMPLE_RATE=24000). Piper medium voices are
# 22.05 kHz, so everything the server emits is resampled to this rate.
OUTPUT_SAMPLE_RATE = int(os.environ.get("OUTPUT_SAMPLE_RATE", "24000"))

app = FastAPI()


# --------------------------------------------------------------------------- #
#  audio helpers
# --------------------------------------------------------------------------- #
def _resample_int16(pcm: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    """Resample a mono int16 array. soxr (VHQ) when available, else linear."""
    if src_rate == dst_rate:
        return pcm
    if SOXR_AVAILABLE:
        return soxr.resample(pcm, src_rate, dst_rate, quality="VHQ").astype(np.int16)
    duration = pcm.shape[0] / float(src_rate)
    n_out = int(round(duration * dst_rate))
    x_old = np.linspace(0.0, duration, num=pcm.shape[0], endpoint=False)
    x_new = np.linspace(0.0, duration, num=n_out, endpoint=False)
    return np.interp(x_new, x_old, pcm.astype(np.float32)).astype(np.int16)


def _piper_pcm(voice: PiperVoice, text: str) -> np.ndarray:
    """Run Piper and return mono int16 PCM resampled to OUTPUT_SAMPLE_RATE."""
    chunks, src_rate = [], None
    for chunk in voice.synthesize(text):
        src_rate = getattr(chunk, "sample_rate", None) or src_rate
        raw = getattr(chunk, "audio_int16_bytes", None)
        if raw is None:
            fa = np.asarray(chunk.audio_float_array, dtype=np.float32)
            raw = np.clip(fa * 32767.0, -32768, 32767).astype(np.int16).tobytes()
        chunks.append(np.frombuffer(raw, dtype=np.int16))
    pcm = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.int16)
    if src_rate is None:
        src_rate = getattr(getattr(voice, "config", None), "sample_rate", OUTPUT_SAMPLE_RATE)
    return _resample_int16(pcm, src_rate, OUTPUT_SAMPLE_RATE)


def _pcm_to_wav_bytes(pcm: np.ndarray, rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(pcm.tobytes())
    return buf.getvalue()


# --------------------------------------------------------------------------- #
#  language detection + per-session voice selection
# --------------------------------------------------------------------------- #
config_errors: list[str] = []           # surfaced at /v1/health and logged CRITICAL
_LANGS_ORDERED: list[str] = ["en"]      # from TTS_LANGUAGES; [0] is primary/fallback
_PRIMARY_LANG = "en"
preferred_quality = "medium"
use_cuda = False
piper_models_dir = os.path.abspath("piper_models")
piper_hf_repo_id = "rhasspy/piper-voices"
default_voice_id = ""

voice_meta: dict[str, dict] = {}        # voice id -> {name, lang, subpath}
loaded_voices: dict[str, PiperVoice] = {}
api_voice_list: list[dict] = []
_lang_pool: dict[str, list[str]] = {}   # lang -> ordered speaker pool
_assignments: dict[tuple, str] = {}     # (session, lang) -> voice id
_in_use: dict[str, set] = {}            # lang -> {voice id handed out}
_voice_lock = threading.Lock()
_load_lock = threading.Lock()

_QUALITY_ORDER = ("x_low", "low", "medium", "high")

# ISO-639-1 -> lingua.Language attribute name. None => lingua has no model, so the
# language can only be used on its own (never auto-selected against others).
_ISO_TO_LINGUA = {
    "ar": "ARABIC", "ca": "CATALAN", "cs": "CZECH", "cy": "WELSH", "da": "DANISH",
    "de": "GERMAN", "el": "GREEK", "en": "ENGLISH", "es": "SPANISH", "fa": "PERSIAN",
    "fi": "FINNISH", "fr": "FRENCH", "hu": "HUNGARIAN", "is": "ICELANDIC",
    "it": "ITALIAN", "ka": "GEORGIAN", "kk": "KAZAKH", "lb": None, "ne": None,
    "nl": "DUTCH", "no": "BOKMAL", "pl": "POLISH", "pt": "PORTUGUESE",
    "ro": "ROMANIAN", "ru": "RUSSIAN", "sk": "SLOVAK", "sl": "SLOVENE",
    "sr": "SERBIAN", "sv": "SWEDISH", "sw": "SWAHILI", "tr": "TURKISH",
    "uk": "UKRAINIAN", "vi": "VIETNAMESE", "zh": "CHINESE",
}
_DETECT_FLOOR = float(os.environ.get("TTS_DETECT_FLOOR", "0.65"))
_DETECT_MARGIN = float(os.environ.get("TTS_DETECT_MARGIN", "0.15"))
_detector = None
_detector_built = False

# STRICT_LANGUAGE: reject an utterance whose language isn't in TTS_LANGUAGES
# instead of voicing it with the wrong speaker. Uses its own all-language
# lingua detector (lazy).
strict_language = True
_all_detector = None
_all_detector_built = False


def _split_quality(voice_id: str):
    """'thorsten_emotional-medium' -> ('thorsten_emotional', 'medium').
    An id with no known quality suffix -> (voice_id, None)."""
    base, _, q = voice_id.rpartition("-")
    if base and q in _QUALITY_ORDER:
        return base, q
    return voice_id, None


def _quality_sort_key(q, preferred):
    """Rank a quality vs the preferred one: exact first, then nearest, ties
    toward the higher quality."""
    order = _QUALITY_ORDER
    pi = order.index(preferred) if preferred in order else order.index("medium")
    qi = order.index(q) if q in order else -1
    return (abs(qi - pi), -qi)


def _get_detector():
    """Build the lingua detector on first use (lazy) from the configured
    languages. Returns None when detection is unneeded or unavailable."""
    global _detector, _detector_built
    if _detector_built:
        return _detector
    _detector_built = True
    codes = [c for c in _LANGS_ORDERED if _ISO_TO_LINGUA.get(c)]
    if len(codes) < 2:
        return None
    try:
        from lingua import Language, LanguageDetectorBuilder
        langs = [getattr(Language, _ISO_TO_LINGUA[c]) for c in codes]
        _detector = LanguageDetectorBuilder.from_languages(*langs).build()
        logger.info(f"lingua detector built (lazy) for: {codes}")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"lingua unavailable ({e}); auto-voice pins to primary '{_PRIMARY_LANG}'")
        _detector = None
    return _detector


def detect_lang(text: str) -> str:
    """Guess the language of `text` among the configured ones, biased toward the
    primary (first-listed) language so a weak or short signal never flips the
    voice. Falls back to primary whenever detection is off or uncertain."""
    text = (text or "").strip()
    if not text or len(_LANGS_ORDERED) < 2:
        return _PRIMARY_LANG
    det = _get_detector()
    if det is None:
        return _PRIMARY_LANG
    try:
        from lingua import Language
        conf = {c.language: c.value for c in det.compute_language_confidence_values(text)}
    except Exception:  # noqa: BLE001
        return _PRIMARY_LANG
    if not conf:
        return _PRIMARY_LANG
    primary_lg = getattr(Language, _ISO_TO_LINGUA[_PRIMARY_LANG], None)
    best_lg, best_v = max(conf.items(), key=lambda kv: kv[1])
    if best_lg == primary_lg:
        return _PRIMARY_LANG
    n_words = len(re.findall(r"\w+", text, flags=re.UNICODE))
    floor = 0.90 if n_words < 2 else _DETECT_FLOOR
    if best_v >= floor and (best_v - conf.get(primary_lg, 0.0)) >= _DETECT_MARGIN:
        for iso, name in _ISO_TO_LINGUA.items():
            if name and getattr(Language, name, None) == best_lg:
                return iso
    return _PRIMARY_LANG


def _get_all_detector():
    """Lingua detector over every language it has a model for (lazy). Only used
    by unsupported_language()."""
    global _all_detector, _all_detector_built
    if _all_detector_built:
        return _all_detector
    _all_detector_built = True
    try:
        from lingua import Language, LanguageDetectorBuilder
        langs = [getattr(Language, n) for n in {v for v in _ISO_TO_LINGUA.values() if v}]
        _all_detector = LanguageDetectorBuilder.from_languages(*langs).build()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"lingua unavailable ({e}); STRICT_LANGUAGE check disabled")
        _all_detector = None
    return _all_detector


def unsupported_language(text: str):
    """ISO code of `text`'s language when lingua identifies it as one NOT in
    TTS_LANGUAGES; None otherwise (including when it can't decide). lingua's own
    minimum-distance guard is the only confidence check."""
    text = (text or "").strip()
    if not text:
        return None
    det = _get_all_detector()
    if det is None:
        return None
    lg = det.detect_language_of(text)
    if lg is None:
        return None
    from lingua import Language
    configured = {getattr(Language, _ISO_TO_LINGUA[c], None)
                  for c in _LANGS_ORDERED if _ISO_TO_LINGUA.get(c)}
    if lg in configured:
        return None
    return lg.iso_code_639_1.name.lower()


def resolve_auto_voice(session, lang):
    """Pick a Piper voice for (session, detected language). Each session keeps a
    stable voice per language; distinct sessions get distinct voices until the
    pool is exhausted, then they share it (no error). Returns None only if there
    is no pool even after falling back to the primary language."""
    pool, used_lang = _lang_pool.get(lang), lang
    if not pool:
        pool, used_lang = _lang_pool.get(_PRIMARY_LANG), _PRIMARY_LANG
    if not pool:
        return None
    key = (session or "_anon", used_lang)
    with _voice_lock:
        cur = _assignments.get(key)
        if cur in pool:
            return cur
        used = _in_use.setdefault(used_lang, set())
        h = int(hashlib.sha1(session.encode("utf-8")).hexdigest(), 16) if session else 0
        free = [v for v in pool if v not in used]
        pick = free[h % len(free)] if free else pool[h % len(pool)]
        _assignments[key] = pick
        used.add(pick)
        return pick


def _ensure_voice_files(subpath: str):
    """Download <subpath>.onnx + .onnx.json from HuggingFace if missing."""
    base = os.path.join(piper_models_dir, subpath)
    onnx, cfg = base + ".onnx", base + ".onnx.json"
    for want, fname in ((onnx, f"{subpath}.onnx"), (cfg, f"{subpath}.onnx.json")):
        if not os.path.exists(want):
            os.makedirs(os.path.dirname(want), exist_ok=True)
            logger.info(f"downloading {fname} ...")
            hf_hub_download(repo_id=piper_hf_repo_id, filename=fname, local_dir=piper_models_dir)
    return onnx, cfg


def _get_voice(voice_id: str) -> PiperVoice:
    """Lazily download + load a Piper voice, cached. _load_lock serialises so two
    first-hits on the same voice don't both download."""
    v = loaded_voices.get(voice_id)
    if v is not None:
        return v
    with _load_lock:
        v = loaded_voices.get(voice_id)
        if v is None:
            onnx, cfg = _ensure_voice_files(voice_meta[voice_id]["subpath"])
            v = PiperVoice.load(onnx, config_path=cfg, use_cuda=use_cuda)
            loaded_voices[voice_id] = v
            logger.info(f"lazy-loaded Piper voice '{voice_id}'")
    return v


# --------------------------------------------------------------------------- #
#  startup
# --------------------------------------------------------------------------- #
@app.on_event("startup")
def load_config():
    global _LANGS_ORDERED, _PRIMARY_LANG, preferred_quality, use_cuda
    global piper_models_dir, piper_hf_repo_id, default_voice_id
    global api_voice_list, _detector, _detector_built
    global strict_language, _all_detector, _all_detector_built

    _detector, _detector_built = None, False
    _all_detector, _all_detector_built = None, False
    for d in (config_errors,):
        d.clear()
    for d in (voice_meta, loaded_voices, _lang_pool, _assignments, _in_use):
        d.clear()

    cfg = dotenv_values(CONFIG_ENV_PATH) if os.path.exists(CONFIG_ENV_PATH) else {}
    logger.info(f"config: {CONFIG_ENV_PATH} ({'loaded' if cfg else 'defaults'})")

    raw_langs = cfg.get("TTS_LANGUAGES") or cfg.get("LANGUAGES") or "en"
    _LANGS_ORDERED = [x.strip().lower() for x in raw_langs.split(",") if x.strip()] or ["en"]
    _PRIMARY_LANG = _LANGS_ORDERED[0]
    strict_language = (cfg.get("STRICT_LANGUAGE", "true") or "true").strip().lower() not in (
        "0", "false", "no", "off")
    preferred_quality = (cfg.get("PREFERRED_QUALITY", "medium") or "medium").strip().lower()
    if preferred_quality not in _QUALITY_ORDER:
        config_errors.append(
            f"PREFERRED_QUALITY '{preferred_quality}' is not one of {list(_QUALITY_ORDER)}; using 'medium'.")
        preferred_quality = "medium"
    use_cuda = (cfg.get("DEVICE", "cpu") or "cpu").strip().lower() == "cuda"
    default_voice_id = (cfg.get("DEFAULT_VOICE", "") or "").strip()
    threads = (cfg.get("TTS_CPU_THREADS") or cfg.get("TORCH_CPU_THREADS") or "0").strip()
    if threads.isdigit() and int(threads) > 0:
        os.environ.setdefault("OMP_NUM_THREADS", threads)

    if len(_LANGS_ORDERED) > 1:
        for c in _LANGS_ORDERED:
            if not _ISO_TO_LINGUA.get(c):
                config_errors.append(
                    f"TTS_LANGUAGES lists '{c}' but language auto-detection has no model for it; "
                    f"it will never be auto-selected. Use it as the only language, or remove it.")

    with open(VOICES_DEF_PATH, "r", encoding="utf-8") as f:
        definitions = yaml.safe_load(f) or {}
    piper_def = definitions.get("piper", {})
    piper_models_dir = os.path.abspath(piper_def.get("models_dir", "piper_models"))
    piper_hf_repo_id = piper_def.get("hf_repo_id") or "rhasspy/piper-voices"
    lang_defs = piper_def.get("languages", {})

    for lang_code in _LANGS_ORDERED:
        lang_def = lang_defs.get(lang_code)
        if not lang_def or not lang_def.get("voices"):
            config_errors.append(f"No Piper voice is defined for configured language '{lang_code}'.")
            continue
        defined = lang_def["voices"]                # id -> {subpath_no_ext, name}
        by_base: dict[str, list] = {}
        for vid in defined:
            b, q = _split_quality(vid)
            by_base.setdefault(b, []).append((q or "medium", vid))

        env_key = f"ENABLED_PIPER_VOICES_{lang_code.upper()}"
        if env_key in cfg:
            wanted = []
            for item in (x.strip() for x in (cfg.get(env_key) or "").split(",") if x.strip()):
                ib, _ = _split_quality(item)
                if item in defined:
                    wanted.append(item)
                elif ib in by_base:
                    wanted.append(("base", ib))
                else:
                    config_errors.append(f"{env_key}: '{item}' is not a defined {lang_code} voice.")
            if not wanted:
                config_errors.append(
                    f"{env_key} is set but matched no defined voice; '{lang_code}' has no usable voice.")
                continue
        else:
            wanted = [("base", b) for b in by_base]

        pool = []
        for w in wanted:
            if isinstance(w, tuple):
                variants = sorted(by_base[w[1]], key=lambda qv: _quality_sort_key(qv[0], preferred_quality))
                chosen = variants[0][1]
            else:
                chosen = w
            vdef = defined[chosen]
            subpath = vdef.get("subpath_no_ext")
            if not subpath:
                config_errors.append(f"Piper voice '{chosen}' ({lang_code}) has no subpath_no_ext; skipped.")
                continue
            voice_meta[chosen] = {"name": vdef.get("name", chosen), "lang": lang_code, "subpath": subpath}
            if chosen not in pool:
                pool.append(chosen)
        if pool:
            _lang_pool[lang_code] = pool
            logger.info(f"Piper '{lang_code}': speaker pool {pool} (quality~{preferred_quality}, lazy-load)")

    for c in _LANGS_ORDERED:
        if c not in _lang_pool:
            config_errors.append(f"Configured language '{c}' has no usable voice.")

    api_voice_list = sorted(
        ({"id": vid, "name": m["name"]} for vid, m in voice_meta.items()), key=lambda x: x["name"])
    if _lang_pool:
        api_voice_list = [{"id": "auto", "name": "Auto (per-session, language-aware)"}] + api_voice_list

    for err in config_errors:
        logger.critical(f"CONFIG ERROR: {err}")
    if config_errors:
        logger.critical(f"{len(config_errors)} config error(s) — see GET /v1/health.")
    logger.info(f"ready: languages={_LANGS_ORDERED} primary={_PRIMARY_LANG} "
                f"quality={preferred_quality} voices={len(voice_meta)} cuda={use_cuda}")


# --------------------------------------------------------------------------- #
#  endpoints
# --------------------------------------------------------------------------- #
@app.get("/health")
@app.get("/v1/health")
def health():
    return {
        "status": "error" if config_errors else "ok",
        "voices_loaded": len(api_voice_list),
        "languages": _LANGS_ORDERED,
        "primary_language": _PRIMARY_LANG,
        "preferred_quality": preferred_quality,
        "strict_language": strict_language,
        "errors": config_errors,
    }


@app.get("/models")
@app.get("/v1/models")
def models():
    ids = ["tts-1"] + [v["id"] for v in api_voice_list]
    return {"object": "list", "data": [{"id": i, "object": "model", "owned_by": "local"} for i in ids]}


@app.get("/audio/voices")
@app.get("/v1/audio/voices")
def voices():
    return {"voices": api_voice_list}


@app.post("/audio/speech")
@app.post("/v1/audio/speech")
async def speech(request: Request):
    rid = os.urandom(4).hex()
    try:
        body = await request.json()
        text = body.get("input")
        if not text:
            raise HTTPException(status_code=400, detail={"error": "Input text cannot be empty"})

        voice_id = body.get("voice", default_voice_id)
        session_id = body.get("session_id")
        # The shim smuggles the session id through the voice field ("auto:<id>")
        # because voice-mode does not forward custom params.
        if isinstance(voice_id, str) and voice_id.startswith("auto:"):
            _, _, sid = voice_id.partition(":")
            session_id, voice_id = sid or session_id, "auto"
        if not voice_id:
            raise HTTPException(status_code=400,
                                detail={"error": "Voice ID must be specified (or set DEFAULT_VOICE)"})

        if voice_id == "auto" or voice_id not in voice_meta:
            if strict_language:
                bad = unsupported_language(text)
                if bad:
                    logger.warning(f"[{rid}] rejected: language '{bad}' not in {_LANGS_ORDERED}")
                    raise HTTPException(status_code=400, detail={"error": (
                        f"Language '{bad}' is not enabled for speech "
                        f"(TTS_LANGUAGES={','.join(_LANGS_ORDERED)}). Do not retry; "
                        f"tell the user, in {_PRIMARY_LANG}, that '{bad}' isn't supported.")})
            lang = detect_lang(text)
            resolved = resolve_auto_voice(session_id, lang)
            if not resolved and default_voice_id and default_voice_id != "auto":
                resolved = default_voice_id
            if not resolved or resolved not in voice_meta:
                raise HTTPException(status_code=503, detail={
                    "error": f"No voice available for language '{lang}'. See GET /v1/health."})
            logger.info(f"[{rid}] auto voice: session={session_id!r} lang={lang} -> {resolved}")
            voice_id = resolved

        fmt = str(body.get("response_format") or "wav").lower()
        want_pcm = fmt in ("pcm", "raw", "l16")

        voice = _get_voice(voice_id)
        t0 = time.time()
        pcm = _piper_pcm(voice, text)
        audio = pcm.tobytes() if want_pcm else _pcm_to_wav_bytes(pcm, OUTPUT_SAMPLE_RATE)
        logger.info(f"[{rid}] voice={voice_id} {time.time() - t0:.2f}s "
                    f"{'pcm' if want_pcm else 'wav'}@{OUTPUT_SAMPLE_RATE} {len(audio)}B")
        return Response(content=audio, media_type="audio/pcm" if want_pcm else "audio/wav")

    except HTTPException as e:
        logger.warning(f"[{rid}] HTTP {e.status_code}: {e.detail}")
        raise
    except Exception as e:  # noqa: BLE001
        logger.exception(f"[{rid}] synthesis failed: {e}")
        raise HTTPException(status_code=500, detail={"error": "Internal server error during synthesis."})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8880, reload=True)
