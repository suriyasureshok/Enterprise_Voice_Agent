/**
 * VOXOPS Voice Client — Phase 8
 * Handles: microphone capture, STT upload, TTS playback,
 *          waveform visualisation, conversation history.
 */

"use strict";

/* ── Config ────────────────────────────────────────────────── */
const BACKEND = "http://localhost:8000";
const VOICE_ENDPOINT = `${BACKEND}/voice/voice-query`;
const HEALTH_ENDPOINT = `${BACKEND}/health`;
const HEALTH_POLL_MS = 8000;

/* ── DOM references ────────────────────────────────────────── */
const micBtn            = document.getElementById("micBtn");
const micHint           = document.getElementById("micHint");
const recTimerWrap      = document.getElementById("recTimerWrap");
const recTimerEl        = document.getElementById("recTimer");
const textInput         = document.getElementById("textInput");
const sendTextBtn       = document.getElementById("sendTextBtn");
const convoFeed         = document.getElementById("convoFeed");
const convoEmpty        = document.getElementById("convoEmpty");
const clearBtn          = document.getElementById("clearBtn");
const processingOverlay = document.getElementById("processingOverlay");
const ttsAudio          = document.getElementById("ttsAudio");
const statusDot         = document.getElementById("statusDot");
const statusLabel       = document.getElementById("statusLabel");
const callMeta          = document.getElementById("callMeta");
const callIdEl          = document.getElementById("callId");
const backendUrlEl      = document.getElementById("backendUrl");
const waveCanvas        = document.getElementById("waveCanvas");
const waveCtx           = waveCanvas.getContext("2d");
const offlineBanner     = document.getElementById("offlineBanner");
const retryBtn          = document.getElementById("retryBtn");

/* ── State ─────────────────────────────────────────────────── */
let mediaRecorder    = null;
let audioChunks      = [];
let isRecording      = false;
let recTimerInterval = null;
let recSeconds       = 0;
let audioStream      = null;
let audioContext     = null;
let analyser         = null;
let animFrameId      = null;
let sessionId        = generateId();
let isBusy           = false;
let backendOnline    = false;

// Exponential-backoff health poll: 5s → 10s → 20s → 40s → 60s max
const POLL_DELAYS = [5000, 10000, 20000, 40000, 60000];
let pollDelayIdx  = 0;
let pollTimer     = null;

/* ── Init ──────────────────────────────────────────────────── */
backendUrlEl.textContent = BACKEND;
setStatus("offline", "Checking…");
pingBackend();

retryBtn.addEventListener("click", () => {
  clearTimeout(pollTimer);
  pollDelayIdx = 0;
  setStatus("offline", "Retrying…");
  pingBackend();
});

/* ── Health check with exponential backoff ─────────────────────── */
async function pingBackend() {
  try {
    const r = await fetch(HEALTH_ENDPOINT, { signal: AbortSignal.timeout(4000) });
    if (r.ok) {
      setStatus("online", "Backend online");
      offlineBanner.hidden = true;
      setInputsDisabled(false);
      backendOnline = true;
      pollDelayIdx  = 0;          // reset backoff
      // Resume steady-state polling at 10 s while online
      clearTimeout(pollTimer);
      pollTimer = setTimeout(pingBackend, 10000);
      return;
    }
    throw new Error(`HTTP ${r.status}`);
  } catch (err) {
    // Connection refused or timeout — suppress default console error by
    // catching here; we display status in the UI instead.
    const wasOnline = backendOnline;
    backendOnline   = false;
    setStatus("offline", "Backend offline");
    offlineBanner.hidden = false;
    if (wasOnline) setInputsDisabled(true);

    // Backoff: increase delay up to max
    const delay = POLL_DELAYS[Math.min(pollDelayIdx, POLL_DELAYS.length - 1)];
    pollDelayIdx  = Math.min(pollDelayIdx + 1, POLL_DELAYS.length - 1);
    clearTimeout(pollTimer);
    pollTimer = setTimeout(pingBackend, delay);
  }
}

function setInputsDisabled(disabled) {
  sendTextBtn.disabled = disabled;
  micBtn.style.opacity = disabled ? "0.4" : "";
  micBtn.style.pointerEvents = disabled ? "none" : "";
  textInput.placeholder = disabled
    ? "Backend offline — start the server first"
    : "e.g. Where is order ORD-001?";
}

function setStatus(state, label) {
  statusDot.className = "status-dot" + (state === "online" ? " status-dot--online" : " status-dot--offline");
  statusLabel.textContent = label;
}

/* ── Mic button — click-to-toggle ─────────────────────────── */
micBtn.addEventListener("click", () => {
  if (isBusy) return;
  if (isRecording) stopRecording();
  else              startRecording();
});

/* ── Keyboard shortcut: Space to toggle ──────────────────── */
document.addEventListener("keydown", e => {
  if (e.code === "Space" && document.activeElement !== textInput && !isBusy) {
    e.preventDefault();
    if (isRecording) stopRecording();
    else              startRecording();
  }
});

/* ── Text input ────────────────────────────────────────────── */
sendTextBtn.addEventListener("click", () => sendText());
textInput.addEventListener("keydown", e => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendText(); }
});

async function sendText() {
  const q = textInput.value.trim();
  if (!q || isBusy) return;
  textInput.value = "";
  addUserBubble(q);
  await submitToBackend(null, q);
}

/* ── Clear conversation ─────────────────────────────────────── */
clearBtn.addEventListener("click", () => {
  convoFeed.innerHTML = "";
  convoFeed.appendChild(convoEmpty);
  convoEmpty.hidden = false;
  sessionId = generateId();
  callMeta.hidden = true;
});

/* ── Recording ──────────────────────────────────────────────── */
async function startRecording() {
  try {
    audioStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
  } catch (err) {
    alert("Microphone access denied. Please allow microphone access and reload.");
    return;
  }

  audioChunks = [];
  mediaRecorder = new MediaRecorder(audioStream, getBestMimeType());
  mediaRecorder.ondataavailable = e => { if (e.data.size > 0) audioChunks.push(e.data); };
  mediaRecorder.onstop = () => finaliseRecording();
  mediaRecorder.start(200); // collect in 200 ms chunks

  isRecording = true;
  micBtn.classList.add("mic-btn--recording");
  micHint.textContent = "Recording… click to stop";
  recTimerWrap.hidden = false;
  recSeconds = 0;
  updateTimerDisplay();
  recTimerInterval = setInterval(() => { recSeconds++; updateTimerDisplay(); }, 1000);

  startWaveform(audioStream);
}

function stopRecording() {
  if (!mediaRecorder || mediaRecorder.state === "inactive") return;
  mediaRecorder.stop();
  audioStream?.getTracks().forEach(t => t.stop());
  isRecording = false;
  micBtn.classList.remove("mic-btn--recording");
  micHint.textContent = "Hold to record · click once to toggle";
  recTimerWrap.hidden = true;
  clearInterval(recTimerInterval);
  stopWaveform();
}

async function finaliseRecording() {
  if (audioChunks.length === 0) return;
  const mime = mediaRecorder.mimeType || "audio/webm";
  const blob = new Blob(audioChunks, { type: mime });
  const transcript = "(voice recording)";
  addUserBubble(transcript, true);
  await submitToBackend(blob, null);
}

/* ── Submit to backend ──────────────────────────────────────── */
async function submitToBackend(audioBlob, textQuery) {
  if (isBusy) return;
  isBusy = true;
  setBusy(true);

  try {
    const formData = new FormData();
    if (audioBlob) {
      const ext  = audioBlob.type.includes("ogg") ? ".ogg" : ".webm";
      formData.append("audio", audioBlob, `voice${ext}`);
    } else {
      formData.append("text", textQuery);
    }

    const res = await fetch(VOICE_ENDPOINT, {
      method: "POST",
      body: formData,
      signal: AbortSignal.timeout(30000),
    });

    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      throw new Error(detail.detail || `HTTP ${res.status}`);
    }

    const data = await res.json();
    handleResponse(data);

  } catch (err) {
    addSystemBubble(`⚠ Error: ${err.message}`, null, null, null);
  } finally {
    isBusy = false;
    setBusy(false);
  }
}

/* ── Handle API response ────────────────────────────────────── */
function handleResponse(data) {
  // If audio came in, update user bubble to show real transcript
  if (data.transcript && data.transcript !== "(voice recording)") {
    updateLastUserBubble(data.transcript);
  }

  addSystemBubble(
    data.response_text,
    data.intent,
    data.needs_escalation,
    data.ticket_id
  );

  // Update session meta
  if (data.ticket_id) {
    callMeta.hidden = false;
    callIdEl.textContent = data.ticket_id;
  }

  // TTS playback — prefer audio_url, fall back to Web Speech API
  if (data.audio_url) {
    ttsAudio.src = data.audio_url.startsWith("http") ? data.audio_url : BACKEND + data.audio_url;
    ttsAudio.play().catch(() => {});
  } else {
    speakText(data.response_text);
  }
}

/* ── Web Speech API TTS fallback ────────────────────────────── */
function speakText(text) {
  if (!("speechSynthesis" in window)) return;
  window.speechSynthesis.cancel();
  const utter = new SpeechSynthesisUtterance(text);
  utter.rate  = 0.97;
  utter.pitch = 1.0;
  // Choose a natural voice if available
  const voices = window.speechSynthesis.getVoices();
  const preferred = voices.find(v =>
    /en[-_](US|GB|AU)/i.test(v.lang) && !v.name.toLowerCase().includes("zira")
  );
  if (preferred) utter.voice = preferred;
  window.speechSynthesis.speak(utter);
}
// voices load async in some browsers
window.speechSynthesis?.addEventListener("voiceschanged", () => {});

/* ── Conversation bubbles ───────────────────────────────────── */
function addUserBubble(text, isVoice = false) {
  convoEmpty.hidden = true;
  const wrap = createBubble("user", isVoice ? `🎙 ${text}` : text);
  wrap.dataset.voice = isVoice ? "1" : "0";
  convoFeed.appendChild(wrap);
  scrollBottom();
  return wrap;
}

function updateLastUserBubble(realTranscript) {
  const msgs = convoFeed.querySelectorAll(".msg--user");
  if (!msgs.length) return;
  const last = msgs[msgs.length - 1];
  if (last.dataset.voice === "1") {
    const bubble = last.querySelector(".msg__bubble");
    if (bubble) bubble.textContent = `🎙 ${realTranscript}`;
  }
}

function addSystemBubble(text, intent, needsEscalation, ticketId) {
  const wrap = createBubble("system", text);

  // Badges row
  const badges = document.createElement("div");
  badges.className = "msg__badges";

  if (intent) {
    const b = document.createElement("span");
    b.className = "badge badge--intent";
    b.textContent = `intent: ${intent}`;
    badges.appendChild(b);
  }
  if (needsEscalation) {
    const b = document.createElement("span");
    b.className = "badge badge--escalation";
    b.textContent = "Escalated";
    badges.appendChild(b);
  }
  if (ticketId) {
    const b = document.createElement("span");
    b.className = "badge badge--ticket";
    b.textContent = `Ticket: ${ticketId}`;
    badges.appendChild(b);
  }
  if (badges.children.length) wrap.insertBefore(badges, wrap.querySelector(".msg__meta"));

  // Play button to replay TTS
  const playBtn = document.createElement("button");
  playBtn.className = "play-btn";
  playBtn.innerHTML = "▶ Replay";
  playBtn.onclick = () => speakText(text);
  wrap.appendChild(playBtn);

  convoFeed.appendChild(wrap);
  scrollBottom();
}

function createBubble(role, text) {
  const wrap = document.createElement("div");
  wrap.className = `msg msg--${role}`;

  const roleEl = document.createElement("div");
  roleEl.className = "msg__role";
  roleEl.textContent = role === "user" ? "You" : "VOXOPS AI";

  const bubble = document.createElement("div");
  bubble.className = "msg__bubble";
  bubble.textContent = text;

  const meta = document.createElement("div");
  meta.className = "msg__meta";
  meta.textContent = fmtTime(new Date());

  wrap.appendChild(roleEl);
  wrap.appendChild(bubble);
  wrap.appendChild(meta);
  return wrap;
}

/* ── UI helpers ─────────────────────────────────────────────── */
function setBusy(on) {
  processingOverlay.hidden = !on;
  sendTextBtn.disabled = on;
  micBtn.style.pointerEvents = on ? "none" : "";
}

function scrollBottom() {
  convoFeed.scrollTop = convoFeed.scrollHeight;
}

function updateTimerDisplay() {
  const m = String(Math.floor(recSeconds / 60)).padStart(2, "0");
  const s = String(recSeconds % 60).padStart(2, "0");
  recTimerEl.textContent = `${m}:${s}`;
}

/* ── Waveform visualiser ─────────────────────────────────────── */
function startWaveform(stream) {
  audioContext = new (window.AudioContext || window.webkitAudioContext)();
  analyser     = audioContext.createAnalyser();
  analyser.fftSize = 256;
  const source = audioContext.createMediaStreamSource(stream);
  source.connect(analyser);
  drawWave();
}

function stopWaveform() {
  cancelAnimationFrame(animFrameId);
  if (audioContext) { audioContext.close(); audioContext = null; }
  clearCanvas();
}

function drawWave() {
  animFrameId = requestAnimationFrame(drawWave);
  const data  = new Uint8Array(analyser.frequencyBinCount);
  analyser.getByteTimeDomainData(data);

  const W = waveCanvas.width;
  const H = waveCanvas.height;
  waveCtx.clearRect(0, 0, W, H);
  waveCtx.fillStyle = "#1e2636";
  waveCtx.fillRect(0, 0, W, H);

  waveCtx.lineWidth   = 2;
  waveCtx.strokeStyle = "#4f8ef7";
  waveCtx.beginPath();

  const sliceW = W / data.length;
  let x = 0;
  for (let i = 0; i < data.length; i++) {
    const v = data[i] / 128.0;
    const y = (v * H) / 2;
    i === 0 ? waveCtx.moveTo(x, y) : waveCtx.lineTo(x, y);
    x += sliceW;
  }
  waveCtx.lineTo(W, H / 2);
  waveCtx.stroke();
}

function clearCanvas() {
  const W = waveCanvas.width;
  const H = waveCanvas.height;
  waveCtx.clearRect(0, 0, W, H);
  waveCtx.fillStyle = "#1e2636";
  waveCtx.fillRect(0, 0, W, H);
  // Draw flat idle line
  waveCtx.lineWidth   = 1.5;
  waveCtx.strokeStyle = "rgba(79,142,247,0.25)";
  waveCtx.beginPath();
  waveCtx.moveTo(0,   H / 2);
  waveCtx.lineTo(W, H / 2);
  waveCtx.stroke();
}

clearCanvas(); // draw idle line on load

/* ── Mime type ───────────────────────────────────────────────── */
function getBestMimeType() {
  const types = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/ogg"];
  for (const t of types) {
    if (MediaRecorder.isTypeSupported(t)) return { mimeType: t };
  }
  return {};
}

/* ── Utilities ───────────────────────────────────────────────── */
function generateId() {
  return "sess-" + Math.random().toString(36).slice(2, 10).toUpperCase();
}

function fmtTime(d) {
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

