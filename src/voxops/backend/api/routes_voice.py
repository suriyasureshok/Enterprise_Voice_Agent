"""
VOXOPS AI Gateway — Voice Query Endpoint

POST /voice-query
  Accepts audio (file upload) or text, runs STT if needed,
  and returns a JSON response with transcript + system reply.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from configs.logging_config import get_logger
from src.voxops.database.db import get_db

log = get_logger(__name__)

router = APIRouter(prefix="/voice", tags=["voice"])


# ---------------------------------------------------------------------------
# ffmpeg discovery — ensure it is on PATH even after a post-startup install
# ---------------------------------------------------------------------------

def _ensure_ffmpeg_on_path() -> None:
    """Find ffmpeg and add its directory to *os.environ["PATH"]* if needed."""
    if shutil.which("ffmpeg"):
        return  # already reachable

    search_roots: list[Path] = [
        # WinGet default package location
        Path.home() / "AppData" / "Local" / "Microsoft" / "WinGet" / "Packages",
        Path("C:/ffmpeg/bin"),
        Path("C:/tools/ffmpeg/bin"),
        Path("C:/ProgramData/chocolatey/bin"),
    ]
    for root in search_roots:
        if not root.exists():
            continue
        # WinGet puts it under Gyan.FFmpeg*/…/bin/ffmpeg.exe
        for exe in root.glob("**/ffmpeg.exe"):
            bin_dir = str(exe.parent)
            os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
            log.info("Added ffmpeg to PATH: {}", bin_dir)
            return

    log.warning("ffmpeg not found in any known location — audio conversion will be skipped")


_ensure_ffmpeg_on_path()          # run once at import time


# ---------------------------------------------------------------------------
# Audio conversion helper
# ---------------------------------------------------------------------------

def _get_wav_rms(wav_path: str) -> float:
    """Return the RMS energy of a WAV file (0 = silence)."""
    import math
    import struct
    import wave
    try:
        with wave.open(wav_path, "rb") as wf:
            raw = wf.readframes(wf.getnframes())
            if len(raw) < 2:
                return 0.0
            samples = struct.unpack(f"<{len(raw) // 2}h", raw)
            return math.sqrt(sum(s * s for s in samples) / max(len(samples), 1))
    except Exception:
        return 0.0


def _convert_to_wav(input_path: str) -> str:
    """Convert audio to 16 kHz mono WAV for Whisper.

    Strategy:
      1. Try ffmpeg conversion + aggressive volume normalization
      2. If the result is silent (RMS near 0), return the ORIGINAL file
         and let Whisper/faster-whisper decode it natively (it has built-in
         ffmpeg support for webm/ogg/mp4/etc.)
      3. If ffmpeg isn't installed, return the original file as-is.
    """
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        log.warning("ffmpeg not found — passing original file to Whisper")
        return input_path

    wav_path = input_path.rsplit(".", 1)[0] + "_converted.wav"
    try:
        # Single-pass: convert + extreme volume boost + noise filter
        result = subprocess.run(
            [
                ffmpeg_bin, "-y", "-i", input_path,
                "-af", (
                    "highpass=f=80,"
                    "lowpass=f=8000,"
                    "dynaudnorm=p=0.95:m=10:g=3,"
                    "volume=20,"
                    "alimiter=limit=0.95"
                ),
                "-ar", "16000",
                "-ac", "1",
                "-c:a", "pcm_s16le",
                wav_path,
            ],
            capture_output=True,
            timeout=30,
        )

        if result.returncode == 0 and Path(wav_path).exists():
            rms = _get_wav_rms(wav_path)
            log.info("Converted audio: {} ({} bytes, RMS={:.0f})",
                     wav_path, Path(wav_path).stat().st_size, rms)

            if rms > 50:
                return wav_path

            # Conversion produced silence — the original file likely has
            # audio in a codec that ffmpeg couldn't amplify from near-zero.
            # Let Whisper try the original directly (it has built-in decoders).
            log.warning("Converted WAV is silent (RMS={:.0f}), using original file for Whisper", rms)
            Path(wav_path).unlink(missing_ok=True)
            return input_path

        stderr_msg = result.stderr[:300] if result.stderr else b"(no stderr)"
        log.warning("ffmpeg failed (rc={}): {}, using original", result.returncode, stderr_msg)
        return input_path

    except Exception as exc:
        log.warning("Audio conversion error: {}, using original", exc)
        return input_path


# ---------------------------------------------------------------------------
# WAV diagnostics helper
# ---------------------------------------------------------------------------

def _log_wav_info(wav_path: str) -> None:
    """Log WAV file properties and audio level for debugging."""
    import math
    import struct
    import wave

    try:
        with wave.open(wav_path, "rb") as wf:
            ch = wf.getnchannels()
            rate = wf.getframerate()
            frames = wf.getnframes()
            dur = frames / rate if rate > 0 else 0
            raw_bytes = wf.readframes(frames)
            if len(raw_bytes) >= 2:
                samples = struct.unpack(f"<{len(raw_bytes) // 2}h", raw_bytes)
                rms = math.sqrt(sum(s * s for s in samples) / max(len(samples), 1))
                peak = max(abs(s) for s in samples)
            else:
                rms = peak = 0
        log.info(
            "WAV info: ch={}, rate={}, frames={}, dur={:.1f}s, RMS={:.0f}, peak={}",
            ch, rate, frames, dur, rms, peak,
        )
    except Exception as exc:
        log.warning("WAV info check failed (not a WAV?): {}", exc)


# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------

class VoiceQueryResponse(BaseModel):
    transcript: str
    intent: str | None = None
    confidence: float | None = None
    entities: dict | None = None
    response_text: str
    audio_url: str | None = None
    needs_escalation: bool = False
    ticket_id: str | None = None


# ---------------------------------------------------------------------------
# Transcript normalization — fix common voice misrecognitions
# ---------------------------------------------------------------------------

import re as _re

def _normalize_transcript(text: str) -> str:
    """Fix common voice-to-text errors for logistics domain IDs."""
    t = text.strip()
    # "order dash 001" / "ord dash 001" / "order 1" → "ORD-001"
    t = _re.sub(r'\b(?:order|ord)\s*[-–]?\s*(\d{1,3})\b', lambda m: f'ORD-{m.group(1).zfill(3)}', t, flags=_re.IGNORECASE)
    # "customer 101" / "cust 101" → "CUST-101"
    t = _re.sub(r'\b(?:customer|cust)\s*[-–]?\s*(\d{2,4})\b', lambda m: f'CUST-{m.group(1)}', t, flags=_re.IGNORECASE)
    # "vehicle 01" / "veh 01" → "VEH-01"
    t = _re.sub(r'\b(?:vehicle|veh)\s*[-–]?\s*(\d{1,2})\b', lambda m: f'VEH-{m.group(1).zfill(2)}', t, flags=_re.IGNORECASE)
    # "warehouse 001" → "WH-001"
    t = _re.sub(r'\b(?:warehouse)\s*[-–]?\s*(\d{1,3})\b', lambda m: f'WH-{m.group(1).zfill(3)}', t, flags=_re.IGNORECASE)
    # Number words → digits
    _NW = {'zero':'0','one':'1','two':'2','three':'3','four':'4','five':'5','six':'6','seven':'7','eight':'8','nine':'9'}
    t = _re.sub(r'\b(zero|one|two|three|four|five|six|seven|eight|nine)\b', lambda m: _NW[m.group().lower()], t, flags=_re.IGNORECASE)
    return t


# ---------------------------------------------------------------------------
# POST /voice-query
# ---------------------------------------------------------------------------

@router.post("/voice-query", response_model=VoiceQueryResponse)
async def voice_query(
    audio: Optional[UploadFile] = File(None, description="Audio file (WAV/MP3)"),
    text: Optional[str] = Form(None, description="Text query (alternative to audio)"),
    db: Session = Depends(get_db),
):
    """
    Accept a voice query (audio file **or** text) and return a response.

    Pipeline:
      1. STT transcription (if audio provided)
      2. Orchestrator: Intent detection → Data retrieval → Simulation → Response
      3. Agent handoff (if escalation needed)
    """
    if audio is None and text is None:
        raise HTTPException(status_code=400, detail="Provide either 'audio' file or 'text' form field.")

    transcript = _normalize_transcript(text) if text else ""

    # --- STT (if audio file provided) ---
    if audio is not None:
        try:
            from src.voxops.voice.stt.whisper_engine import transcribe_audio

            # Write uploaded bytes to a temporary file for Whisper
            suffix = Path(audio.filename).suffix if audio.filename else ".wav"
            raw = await audio.read()
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(raw)
                tmp_path = tmp.name

            log.info("Received audio: {} bytes, suffix={}, filename={}",
                     len(raw), suffix, audio.filename)

            # Convert webm/ogg/opus → WAV for reliable Whisper decoding
            wav_path = _convert_to_wav(tmp_path)

            # Quick audio level check (WAV only)
            _log_wav_info(wav_path)

            log.info("Transcribing uploaded audio ({} bytes, format={})", len(raw), suffix)
            result = transcribe_audio(wav_path)
            transcript = _normalize_transcript(result.get("text", ""))
            log.info("Transcript (normalized): {}", transcript[:120])

            # Cleanup temp files
            Path(tmp_path).unlink(missing_ok=True)
            if wav_path != tmp_path:
                Path(wav_path).unlink(missing_ok=True)
        except ImportError:
            log.warning("Whisper not available — falling back to empty transcript.")
        except Exception as exc:
            log.error("STT failed: {}", exc)
            raise HTTPException(status_code=500, detail=f"Speech-to-text failed: {exc}")

    if not transcript.strip():
        # Instead of an error, return a friendly response so the UI can show it
        return VoiceQueryResponse(
            transcript="(no speech detected)",
            intent="unknown",
            confidence=0.0,
            entities={},
            response_text="I didn't catch that. Could you please speak again or type your question?",
            audio_url=None,
            needs_escalation=False,
            ticket_id=None,
        )

    # --- Orchestrator: intent → data → simulation → response → handoff ---
    from src.voxops.backend.services.orchestrator import process_query

    result = process_query(query=transcript, db=db)

    # --- TTS: generate audio file (best-effort) ---
    audio_url: str | None = None
    try:
        from src.voxops.voice.tts.coqui_tts import save_audio as tts_save
        audio_path = tts_save(result.response_text)
        # Return a URL relative to the backend root — served at /audio/
        audio_url = f"/audio/{audio_path.name}"
        log.info("TTS audio: {}", audio_url)
    except ImportError:
        log.debug("Coqui TTS not installed — skipping audio generation.")
    except Exception as exc:
        log.warning("TTS generation failed (non-fatal): {}", exc)

    return VoiceQueryResponse(
        transcript=result.transcript,
        intent=result.intent,
        confidence=result.confidence,
        entities=result.entities,
        response_text=result.response_text,
        audio_url=audio_url,
        needs_escalation=result.needs_escalation,
        ticket_id=result.handoff.ticket_id if result.handoff else None,
    )
