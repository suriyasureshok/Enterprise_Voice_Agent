"""VOXOPS AI Gateway — Speech-to-Text Engine (faster-whisper)

Provides:
  - WhisperSTT class with lazy model loading
  - transcribe_audio()  — file or bytes → text
  - transcribe_stream()  — microphone / streaming audio → text
"""

from __future__ import annotations

import io
import tempfile
from pathlib import Path
from typing import Any, BinaryIO

import numpy as np
from faster_whisper import WhisperModel

from configs.logging_config import get_logger
from configs.settings import settings

log = get_logger(__name__)


class WhisperSTT:
    """
    Singleton-style wrapper around *faster-whisper*.

    The model is loaded lazily on first call to :meth:`transcribe_audio`
    so startup stays fast.
    """

    _instance: WhisperSTT | None = None
    _model: WhisperModel | None = None

    def __new__(cls) -> WhisperSTT:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    # ------------------------------------------------------------------ #
    # Model lifecycle                                                     #
    # ------------------------------------------------------------------ #

    def load_model(
        self,
        model_size: str | None = None,
        device: str = "auto",
        compute_type: str = "default",
    ) -> WhisperModel:
        """
        Load (or return cached) faster-whisper model.

        Args:
            model_size:   Whisper variant — ``tiny``, ``base``, ``small``,
                          ``medium``, ``large-v2``, etc.  Defaults to the
                          value in ``settings.whisper_model_size``.
            device:       ``"auto"`` | ``"cpu"`` | ``"cuda"``.
            compute_type: ``"default"`` | ``"float16"`` | ``"int8"`` etc.

        Returns:
            The loaded :class:`WhisperModel`.
        """
        if self._model is not None:
            return self._model

        size = model_size or settings.whisper_model_size
        log.info("Loading Whisper model '{}' on {} ({})", size, device, compute_type)

        self._model = WhisperModel(
            size,
            device=device,
            compute_type=compute_type,
        )
        log.info("Whisper model loaded successfully.")
        return self._model

    @property
    def model(self) -> WhisperModel:
        """Access the model, loading it if needed."""
        if self._model is None:
            self.load_model()
        return self._model

    # ------------------------------------------------------------------ #
    # Transcription                                                       #
    # ------------------------------------------------------------------ #

    def transcribe_audio(
        self,
        audio_input: str | Path | bytes | BinaryIO | np.ndarray,
        language: str | None = None,
        beam_size: int = 5,
        **kwargs: Any,
    ) -> dict:
        """
        Transcribe audio to text.

        Args:
            audio_input: Can be:
                - a file path (str / Path)
                - raw bytes (WAV/MP3/OGG/FLAC)
                - a file-like object
                - a numpy float32 array (16 kHz mono)
            language:  ISO 639-1 code (``"en"``).  ``None`` = auto-detect.
            beam_size: Beam width for decoding.
            **kwargs:  Forwarded to ``WhisperModel.transcribe()``.

        Returns:
            ``{"text": str, "language": str, "segments": list[dict]}``
        """
        audio = self._resolve_input(audio_input)
        log.debug("Starting transcription (lang={}, beam={})", language, beam_size)

        segments_iter, info = self.model.transcribe(
            audio,
            language=language,
            beam_size=beam_size,
            **kwargs,
        )

        segments: list[dict] = []
        full_text_parts: list[str] = []
        for seg in segments_iter:
            segments.append({
                "start": round(seg.start, 2),
                "end":   round(seg.end, 2),
                "text":  seg.text.strip(),
            })
            full_text_parts.append(seg.text.strip())

        full_text = " ".join(full_text_parts)
        detected_lang = info.language if info else language or "unknown"

        log.info(
            "Transcription complete — {} chars, lang={}",
            len(full_text),
            detected_lang,
        )

        return {
            "text":     full_text,
            "language": detected_lang,
            "segments": segments,
        }

    # ------------------------------------------------------------------ #
    # Helpers                                                             #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _resolve_input(
        audio_input: str | Path | bytes | BinaryIO | np.ndarray,
    ) -> str | np.ndarray:
        """
        Normalise diverse input types into something faster-whisper accepts
        (file path string or numpy array).
        """
        # numpy array  → pass through
        if isinstance(audio_input, np.ndarray):
            return audio_input

        # str / Path → file path
        if isinstance(audio_input, (str, Path)):
            path = Path(audio_input)
            if not path.exists():
                raise FileNotFoundError(f"Audio file not found: {path}")
            return str(path)

        # bytes → write to temp file
        if isinstance(audio_input, bytes):
            audio_input = io.BytesIO(audio_input)

        # file-like → write to temp file and return path
        if hasattr(audio_input, "read"):
            suffix = ".wav"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(audio_input.read())
                return tmp.name

        raise TypeError(f"Unsupported audio_input type: {type(audio_input)}")


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------

_engine = WhisperSTT()

load_model = _engine.load_model
transcribe_audio = _engine.transcribe_audio

