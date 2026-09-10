"""Multi-session wrapper around VoiceMode.

Two behaviours are injected into the `converse` MCP tool, both defaults-only
(an explicit argument from the caller always wins):

1. wait_for_conch=True  -> a second agent queues for the floor instead of being
   turned away. hold_conch=True on turns that expect a reply, so a Q/A pair is
   not cut into at the turn boundary.
2. voice=<stable per-session pick>  -> each Claude session is hashed onto one
   voice from VOICEMODE_STANDUP_VOICES, so parallel agents are distinguishable
   and a given session always sounds the same.

The session key is the harness session id (CLAUDE_CODE_SESSION_ID etc.); with a
per-session stdio server that env var is present, and the process pid is the
fallback. See __main__.py.
"""
