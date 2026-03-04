"""VOXOPS AI Gateway — Text-to-Speech Engine (Coqui TTS)

Provides:
  - CoquiTTSEngine class with lazy model loading
  - speak(text)     → numpy audio array
  - save_audio()    → writes WAV/MP3 to disk
"""

from __future__ import annotations

import io
import uuid
import wave
from pathlib import Path
from typing import Any

import numpy as np

from configs.logging_config import get_logger
from configs.settings import settings

log = get_logger(__name__)

# Try importing TTS — it's a heavy dependency so we handle import errors
try:
    from TTS.api import TTS as CoquiTTS
    _TTS_AVAILABLE = True
except ImportError:
    CoquiTTS = None  # type: ignore[assignment,misc]
    _TTS_AVAILABLE = False
    log.warning("coqui-tts not installed — TTS features will be unavailable.")


class CoquiTTSEngine:
    """
    Singleton wrapper around Coqui TTS.

    The model is loaded lazily on first call to :meth:`speak`.
    """

    _instance: CoquiTTSEngine | None = None
    _model: Any | None = None
    _sample_rate: int = 22050  # Coqui default

    def __new__(cls) -> CoquiTTSEngine:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    # ------------------------------------------------------------------ #
    # Model lifecycle                                                     #
    # ------------------------------------------------------------------ #

    def load_model(self, model_name: str | None = None) -> Any:
        """
        Load (or return cached) Coqui TTS model.

        Args:
            model_name: e.g. ``"tts_models/en/ljspeech/tacotron2-DDC"``.
                        Defaults to ``settings.tts_model_name``.
        Returns:
            The loaded TTS model instance.
        """
        if self._model is not None:
            return self._model

        if not _TTS_AVAILABLE:
            raise RuntimeError(
                "coqui-tts is not installed. Run: pip install coqui-tts"
            )

        name = model_name or settings.tts_model_name
        log.info("Loading Coqui TTS model: {}", name)

        self._model = CoquiTTS(model_name=name)

        # Detect sample rate from the synthesiser config
        try:
            self._sample_rate = self._model.synthesizer.output_sample_rate
        except AttributeError:
            self._sample_rate = 22050

        log.info("TTS model loaded — sample_rate={}", self._sample_rate)
        return self._model

    @property
    def model(self) -> Any:
        """Access the model, loading it if needed."""
        if self._model is None:
            self.load_model()
        return self._model

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    # ------------------------------------------------------------------ #
    # Synthesis                                                           #
    # ------------------------------------------------------------------ #

    def speak(
        self,
        text: str,
        speaker: str | None = None,
        language: str | None = None,
        speed: float = 1.0,
    ) -> dict:
        """
        Synthesise speech from text.

        Args:
            text:     The string to speak.
            speaker:  Speaker ID for multi-speaker models (or ``None``).
            language: Language code for multi-lingual models (or ``None``).
            speed:    Playback speed multiplier.

        Returns:
            ``{"audio": np.ndarray, "sample_rate": int}``
        """
        if not text or not text.strip():
            raise ValueError("Cannot synthesise empty text.")

        log.info("Synthesising {} characters of speech", len(text))

        wav: list[float] = self.model.tts(
            text=text,
            speaker=speaker,
            language=language,
            speed=speed,
        )

        audio_array = np.array(wav, dtype=np.float32)
        log.debug(
            "Audio generated — {} samples, {:.1f}s @ {} Hz",
            len(audio_array),
            len(audio_array) / self._sample_rate,
            self._sample_rate,
        )

        return {
            "audio":       audio_array,
            "sample_rate": self._sample_rate,
        }

    def save_audio(
        self,
        text: str,
        output_path: str | Path | None = None,
        speaker: str | None = None,
        language: str | None = None,
        speed: float = 1.0,
    ) -> Path:
        """
        Synthesise text and write the result to a WAV file.

        Args:
            text:        The string to speak.
            output_path: Destination file. If ``None`` a unique file is
                         created under ``settings.tts_output_path``.
            speaker:     Speaker ID for multi-speaker models.
            language:    Language code for multi-lingual models.
            speed:       Playback speed multiplier.

        Returns:
            :class:`Path` to the saved WAV file.
        """
        result = self.speak(text, speaker=speaker, language=language, speed=speed)
        audio_array: np.ndarray = result["audio"]
        sr: int = result["sample_rate"]

        if output_path is None:
            out_dir = Path(settings.tts_output_path)
            out_dir.mkdir(parents=True, exist_ok=True)
            output_path = out_dir / f"tts_{uuid.uuid4().hex[:12]}.wav"
        else:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)

        self._write_wav(output_path, audio_array, sr)
        log.info("Audio saved to {}", output_path)
        return output_path

    def to_wav_bytes(self, text: str, **kwargs: Any) -> bytes:
        """
        Synthesise text and return raw WAV bytes (useful for HTTP responses).
        """
        result = self.speak(text, **kwargs)
        buf = io.BytesIO()
        self._write_wav_to_buffer(buf, result["audio"], result["sample_rate"])
        return buf.getvalue()

    # ------------------------------------------------------------------ #
    # Internal helpers                                                    #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _write_wav(path: Path, audio: np.ndarray, sample_rate: int) -> None:
        """Write float32 numpy array to a 16-bit PCM WAV file."""
        pcm = (audio * 32767).astype(np.int16)
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm.tobytes())

    @staticmethod
    def _write_wav_to_buffer(
        buf: io.BytesIO, audio: np.ndarray, sample_rate: int
    ) -> None:
        """Write float32 numpy audio to a BytesIO as 16-bit PCM WAV."""
        pcm = (audio * 32767).astype(np.int16)
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm.tobytes())
        buf.seek(0)


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------

_engine = CoquiTTSEngine()

load_model = _engine.load_model
speak       = _engine.speak
save_audio  = _engine.save_audio
to_wav_bytes = _engine.to_wav_bytes

