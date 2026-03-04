"""voxops.voice.tts package — Text-to-Speech."""

from src.voxops.voice.tts.coqui_tts import (
    CoquiTTSEngine,
    load_model,
    save_audio,
    speak,
    to_wav_bytes,
)

__all__ = ["CoquiTTSEngine", "load_model", "speak", "save_audio", "to_wav_bytes"]
