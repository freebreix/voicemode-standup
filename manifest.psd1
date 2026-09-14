# Pinned upstream versions. install.ps1 reads this; bump deliberately + test.
@{
    # whisper.cpp prebuilt release (github.com/ggml-org/whisper.cpp/releases)
    WhisperCppTag        = 'b4938'
    WhisperCublasAsset   = 'whisper-cublas-12.4.0-bin-x64.zip'   # GPU (CUDA 12.4)
    WhisperCpuAsset      = 'whisper-bin-x64.zip'                  # CPU fallback
    WhisperModels        = @('large-v3-turbo', 'base')           # ggml-<name>.bin from HF ggerganov/whisper.cpp

    # Piper OpenAI TTS server lives in tts/ (tracked source, Piper-only).
    # Started from ginto-sakata/local-openai-tts-server (MIT); see tts/LICENSE.

    # VoiceMode MCP - pinned in shim/pyproject.toml (voice-mode==8.12.0).
    # The shim wraps its `converse` tool; keep this note in sync with that pin.
    VoiceModePin         = 'voice-mode==8.12.0'

    PythonVersion        = '3.12'

    # NSSM (nssm.cc) wraps tts/whisper as real Windows Services (Session 0,
    # no console window ever) instead of hidden-window Scheduled Tasks.
    # register-services.ps1 needs admin; register-tasks.ps1 stays as the
    # non-admin fallback install.ps1 uses when it can't elevate.
    NssmVersion           = '2.24'
    NssmZipUrl            = 'https://nssm.cc/release/nssm-2.24.zip'
}
