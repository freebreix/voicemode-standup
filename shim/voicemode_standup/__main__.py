"""Entry point: patch VoiceMode's `converse`, then run its stdio MCP server.

Run by each Claude session (MCP `type: stdio`, command = `voicemode-standup`).
"""
from __future__ import annotations

import functools
import hashlib
import os
import sys

_DEFAULT_POOL = "amy-medium,ryan-medium,lessac-medium,hfc_female-medium,kristin-medium"


def _log(msg: str) -> None:
    # stderr shows up in the MCP server log; never touch stdout (JSON-RPC).
    print(f"[voicemode-standup] {msg}", file=sys.stderr, flush=True)


def _truthy(v, default: bool) -> bool:
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def _falsey(v) -> bool:
    return str(v).strip().lower() in ("0", "false", "no", "off", "none", "")


def _session_key() -> str:
    for var in ("CLAUDE_CODE_SESSION_ID", "CLAUDE_SESSION_ID", "VOICEMODE_SESSION_ID"):
        val = os.environ.get(var)
        if val:
            return val
    return f"pid-{os.getpid()}"


def _pick_voice(pool: list[str], key: str) -> str:
    h = int(hashlib.sha1(key.encode("utf-8")).hexdigest(), 16)
    return pool[h % len(pool)]


class _Injector:
    """Fills converse defaults. Applied to a kwargs dict (wrapping .fn) or to the
    raw arguments dict (wrapping Tool.run) - same logic, both are plain dicts."""

    def __init__(self):
        self.pool = [v.strip() for v in os.environ.get("VOICEMODE_STANDUP_VOICES", _DEFAULT_POOL).split(",") if v.strip()]
        self.auto_wait = _truthy(os.environ.get("VOICEMODE_STANDUP_AUTOWAIT"), True)
        self.auto_hold = _truthy(os.environ.get("VOICEMODE_STANDUP_AUTOHOLD"), True)
        self.key = _session_key()
        self.voice = _pick_voice(self.pool, self.key) if self.pool else None
        _log(f"session={self.key!r} voice={self.voice!r} autowait={self.auto_wait} autohold={self.auto_hold}")

    def apply(self, d: dict) -> dict:
        if d is None:
            d = {}
        if self.auto_wait and "wait_for_conch" not in d:
            d["wait_for_conch"] = True
        if (
            self.auto_hold
            and "hold_conch" not in d
            and not _falsey(d.get("wait_for_response", True))
            and not _truthy(d.get("skip_conch"), False)
        ):
            d["hold_conch"] = True
        if self.voice and not d.get("voice"):
            d["voice"] = self.voice
        if not d.get("session_id"):
            d["session_id"] = self.key
        return d


_INJ: "_Injector | None" = None


def _apply_patch() -> None:
    global _INJ

    # Fold ~/.voicemode/voicemode.env into os.environ first (pool / autowait
    # overrides can live there), matching voicemode's own launcher.
    try:
        from voice_mode.config import load_voicemode_env

        load_voicemode_env()
    except Exception as e:  # noqa: BLE001
        _log(f"load_voicemode_env skipped: {e}")

    # Import voice_mode.server so the tools register, and grab the FunctionTool
    # class to wrap its run() at the class level (guarded by tool name). This is
    # the fastmcp-version-stable seam: FunctionTool.run(self, arguments: dict)
    # receives the raw argument dict from the MCP layer *before* validation, so
    # keys we inject are validated normally (they are all real converse params).
    try:
        import voice_mode.server  # noqa: F401  (registers tools)
        from fastmcp.tools.function_tool import FunctionTool
    except Exception as e:  # noqa: BLE001
        _log(f"FATAL: cannot import voice_mode / fastmcp: {e}")
        raise

    _INJ = _Injector()

    run = FunctionTool.run
    if getattr(run, "_standup_wrapped", False):
        return

    @functools.wraps(run)
    async def _run(self, arguments, *a, **k):
        if getattr(self, "name", None) == "converse" and _INJ is not None:
            arguments = _INJ.apply(dict(arguments or {}))
        return await run(self, arguments, *a, **k)

    _run._standup_wrapped = True  # type: ignore[attr-defined]
    FunctionTool.run = _run  # type: ignore[assignment]
    _log("patched FunctionTool.run (converse injection active)")


def main() -> None:
    _apply_patch()
    from voice_mode.server import main as server_main

    server_main()


if __name__ == "__main__":
    main()
