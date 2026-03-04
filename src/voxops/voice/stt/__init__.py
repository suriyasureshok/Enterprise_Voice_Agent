"""voxops.voice.stt package — Speech-to-Text."""

from src.voxops.voice.stt.whisper_engine import (
    WhisperSTT,
    load_model,
    transcribe_audio,
)

__all__ = ["WhisperSTT", "load_model", "transcribe_audio"]
