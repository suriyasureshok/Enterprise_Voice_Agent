"""VOXOPS AI Gateway — Audio Utilities

Provides:
  - convert_audio()    — convert between WAV / MP3 / OGG / FLAC
  - normalise_audio()  — peak-normalise a numpy audio array
  - resample_audio()   — change sample rate
  - audio_to_bytes()   — numpy array → WAV bytes
  - bytes_to_numpy()   — WAV bytes → numpy float32 array
  - get_audio_info()   — duration, sample rate, channels
"""

from __future__ import annotations

import io
import struct
import wave
from pathlib import Path
from typing import Any

import numpy as np

from configs.logging_config import get_logger

log = get_logger(__name__)

# Optional heavy dependency — gracefully degrade
try:
    from pydub import AudioSegment
    _PYDUB_AVAILABLE = True
except ImportError:
    AudioSegment = None  # type: ignore[assignment,misc]
    _PYDUB_AVAILABLE = False


# ---------------------------------------------------------------------------
# Format conversion
# ---------------------------------------------------------------------------

def convert_audio(
    input_path: str | Path,
    output_path: str | Path,
    output_format: str | None = None,
    sample_rate: int | None = None,
    channels: int | None = None,
) -> Path:
    """
    Convert an audio file between formats (WAV, MP3, OGG, FLAC).

    Args:
        input_path:    Source audio file.
        output_path:   Destination file.
        output_format: Target format string (e.g. ``"wav"``, ``"mp3"``).  
                       If ``None``, inferred from ``output_path`` extension.
        sample_rate:   Resample to this rate (Hz).  ``None`` = keep original.
        channels:      Number of output channels. ``None`` = keep original.

    Returns:
        :class:`Path` to the converted file.
    """
    if not _PYDUB_AVAILABLE:
        raise RuntimeError("pydub is required for audio conversion. pip install pydub")

    inp = Path(input_path)
    out = Path(output_path)
    fmt = output_format or out.suffix.lstrip(".").lower()

    log.info("Converting {} → {} (format={})", inp.name, out.name, fmt)

    audio: AudioSegment = AudioSegment.from_file(str(inp))

    if sample_rate is not None:
        audio = audio.set_frame_rate(sample_rate)
    if channels is not None:
        audio = audio.set_channels(channels)

    out.parent.mkdir(parents=True, exist_ok=True)
    audio.export(str(out), format=fmt)
    log.info("Conversion complete — {}", out)
    return out


def convert_bytes(
    audio_bytes: bytes,
    input_format: str = "wav",
    output_format: str = "wav",
    sample_rate: int | None = None,
    channels: int | None = None,
) -> bytes:
    """
    Convert raw audio bytes from one format to another.

    Returns:
        Converted audio as bytes.
    """
    if not _PYDUB_AVAILABLE:
        raise RuntimeError("pydub is required. pip install pydub")

    audio: AudioSegment = AudioSegment.from_file(
        io.BytesIO(audio_bytes), format=input_format
    )
    if sample_rate is not None:
        audio = audio.set_frame_rate(sample_rate)
    if channels is not None:
        audio = audio.set_channels(channels)

    buf = io.BytesIO()
    audio.export(buf, format=output_format)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

def normalise_audio(
    audio: np.ndarray,
    target_peak: float = 0.95,
) -> np.ndarray:
    """
    Peak-normalise a float32 audio signal.

    Args:
        audio:       1-D numpy float32 array of samples.
        target_peak: Target absolute peak value (0.0–1.0).

    Returns:
        Normalised copy of the array.
    """
    peak = np.max(np.abs(audio))
    if peak == 0:
        log.warning("Audio signal is silent — skipping normalisation.")
        return audio.copy()

    gain = target_peak / peak
    normalised = audio * gain
    log.debug("Normalised audio — peak {:.4f} → {:.4f}", peak, target_peak)
    return normalised


def trim_silence(
    audio: np.ndarray,
    threshold_db: float = -40.0,
    frame_length: int = 1024,
) -> np.ndarray:
    """
    Trim leading and trailing silence from an audio signal.

    Args:
        audio:        1-D float32 numpy array.
        threshold_db: Silence threshold in dB relative to 0 dBFS.
        frame_length: Number of samples per analysis frame.

    Returns:
        Trimmed copy of the signal.
    """
    threshold_linear = 10 ** (threshold_db / 20.0)
    abs_audio = np.abs(audio)

    # Find first frame above threshold
    start = 0
    for i in range(0, len(abs_audio), frame_length):
        frame = abs_audio[i : i + frame_length]
        if np.max(frame) > threshold_linear:
            start = max(0, i)
            break
    else:
        # Entire signal is below threshold — return empty
        log.debug("Entire signal below threshold — returning empty array.")
        return np.array([], dtype=audio.dtype)

    # Find last frame above threshold
    end = len(audio)
    for i in range(len(abs_audio) - 1, -1, -frame_length):
        frame_start = max(0, i - frame_length + 1)
        frame = abs_audio[frame_start : i + 1]
        if np.max(frame) > threshold_linear:
            end = min(len(audio), i + 1)
            break

    trimmed = audio[start:end]
    log.debug(
        "Trimmed silence — {} → {} samples ({:.1f}%)",
        len(audio),
        len(trimmed),
        len(trimmed) / max(len(audio), 1) * 100,
    )
    return trimmed


# ---------------------------------------------------------------------------
# Re-sampling
# ---------------------------------------------------------------------------

def resample_audio(
    audio: np.ndarray,
    orig_sr: int,
    target_sr: int,
) -> np.ndarray:
    """
    Resample a float32 mono audio signal using linear interpolation.

    For production quality, consider using ``librosa.resample()`` or
    ``scipy.signal.resample`` instead.

    Args:
        audio:     1-D float32 array.
        orig_sr:   Original sample rate.
        target_sr: Desired sample rate.

    Returns:
        Resampled audio as float32 numpy array.
    """
    if orig_sr == target_sr:
        return audio.copy()

    ratio = target_sr / orig_sr
    new_length = int(len(audio) * ratio)
    indices = np.linspace(0, len(audio) - 1, new_length)
    resampled = np.interp(indices, np.arange(len(audio)), audio).astype(np.float32)

    log.debug(
        "Resampled {} Hz → {} Hz  ({} → {} samples)",
        orig_sr,
        target_sr,
        len(audio),
        len(resampled),
    )
    return resampled


# ---------------------------------------------------------------------------
# Conversion helpers (numpy ↔ bytes)
# ---------------------------------------------------------------------------

def audio_to_wav_bytes(
    audio: np.ndarray,
    sample_rate: int = 16000,
    channels: int = 1,
) -> bytes:
    """
    Convert a float32 numpy array to in-memory WAV bytes (16-bit PCM).
    """
    pcm = (audio * 32767).clip(-32768, 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())
    return buf.getvalue()


def wav_bytes_to_numpy(wav_bytes: bytes) -> tuple[np.ndarray, int]:
    """
    Decode WAV bytes to a float32 numpy array.

    Returns:
        ``(audio_array, sample_rate)``
    """
    buf = io.BytesIO(wav_bytes)
    with wave.open(buf, "rb") as wf:
        n_channels = wf.getnchannels()
        sample_width = wf.getsampwidth()
        sample_rate = wf.getframerate()
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)

    if sample_width == 2:
        dtype = np.int16
    elif sample_width == 4:
        dtype = np.int32
    else:
        raise ValueError(f"Unsupported sample width: {sample_width}")

    samples = np.frombuffer(raw, dtype=dtype).astype(np.float32)

    # Normalise to [-1.0, 1.0]
    samples /= 2 ** (8 * sample_width - 1)

    # Downmix to mono if stereo
    if n_channels == 2:
        samples = samples.reshape(-1, 2).mean(axis=1)
    elif n_channels > 2:
        samples = samples.reshape(-1, n_channels).mean(axis=1)

    return samples, sample_rate


# ---------------------------------------------------------------------------
# Info
# ---------------------------------------------------------------------------

def get_audio_info(audio_source: str | Path | bytes) -> dict[str, Any]:
    """
    Return metadata for a WAV audio file or WAV bytes.

    Args:
        audio_source: File path (str/Path) **or** raw WAV bytes.

    Returns:
        ``{"duration_sec": float, "sample_rate": int, "channels": int,
           "sample_width": int, "n_frames": int}``
    """
    if isinstance(audio_source, bytes):
        buf = io.BytesIO(audio_source)
        with wave.open(buf, "rb") as wf:
            info = {
                "duration_sec":  round(wf.getnframes() / wf.getframerate(), 3),
                "sample_rate":   wf.getframerate(),
                "channels":      wf.getnchannels(),
                "sample_width":  wf.getsampwidth(),
                "n_frames":      wf.getnframes(),
            }
        log.debug("Audio info from bytes: {}", info)
        return info

    path = Path(audio_source)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    with wave.open(str(path), "rb") as wf:
        info = {
            "duration_sec":  round(wf.getnframes() / wf.getframerate(), 3),
            "sample_rate":   wf.getframerate(),
            "channels":      wf.getnchannels(),
            "sample_width":  wf.getsampwidth(),
            "n_frames":      wf.getnframes(),
        }
    log.debug("Audio info for {}: {}", path.name, info)
    return info

