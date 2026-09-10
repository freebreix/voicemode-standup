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
}
