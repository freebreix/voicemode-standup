"""Multi-session wrapper around VoiceMode.

Two behaviours are injected into the `converse` MCP tool, both defaults-only
(an explicit argument from the caller always wins):

1. wait_for_conch=True  -> a second agent queues for the floor instead of being
   turned away. hold_conch=True on turns that expect a reply, so a Q/A pair is
   not cut into at the turn boundary.
2. voice="auto:<session-id>"  -> the TTS server detects the utterance language
   and hands out a stable speaker per (session, language). Parallel agents stay
   distinguishable; a given session sounds the same each time. The session id
   rides in the voice string because voice-mode does not forward custom params.
   Disable with VOICEMODE_STANDUP_AUTOVOICE=false.

The session key is the harness session id (CLAUDE_CODE_SESSION_ID etc.); with a
per-session stdio server that env var is present, and the process pid is the
fallback. See __main__.py.
"""
