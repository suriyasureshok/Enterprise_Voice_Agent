/* ═══════════════════════════════════════════════════════════
   VoiceOps AI Gateway — Dashboard JavaScript
   Handles: mic recording, waveform, pipeline animation,
            voice controls, logs toggle, backend API calls
   ═══════════════════════════════════════════════════════════ */

(() => {
  "use strict";

  // ── Backend URL ──
  const API_BASE = "http://localhost:8000";

  // ── DOM References ──
  const micBtn        = document.getElementById("micBtn");
  const micLabel      = document.getElementById("micLabel");
  const waveContainer = document.getElementById("waveformContainer");
  const waveCanvas    = document.getElementById("waveCanvas");
  const btnRecord     = document.getElementById("btnRecord");
  const btnPlayRec    = document.getElementById("btnPlayRec");
  const btnPlayAI     = document.getElementById("btnPlayAI");
  const audioDetails  = document.getElementById("audioDetails");
  const audioDuration = document.getElementById("audioDuration");
  const audioTimestamp = document.getElementById("audioTimestamp");
  const audioSession  = document.getElementById("audioSession");
  const pipelineBadge = document.getElementById("pipelineBadge");
  const logsToggle    = document.getElementById("logsToggle");
  const logsBody      = document.getElementById("logsBody");

  // Data panel elements
  const intentType    = document.getElementById("intentType");
  const confidenceBar = document.getElementById("confidenceBar");
  const confidenceVal = document.getElementById("confidenceVal");
  const apiOrderId    = document.getElementById("apiOrderId");
  const apiWarehouse  = document.getElementById("apiWarehouse");
  const apiStatus     = document.getElementById("apiStatus");
  const apiEta        = document.getElementById("apiEta");
  const summaryList   = document.getElementById("summaryList");
  const footerLatency = document.getElementById("footerLatency");
  const footerUpdated = document.getElementById("footerUpdated");

  // ── Recording State ──
  let isRecording     = false;
  let mediaRecorder   = null;
  let audioChunks     = [];
  let recordedBlob    = null;
  let recordedUrl     = null;
  let aiAudioUrl      = null;
  let audioContext     = null;
  let analyser        = null;
  let animFrameId     = null;
  let recordStartTime = null;
  let sessionId       = generateSessionId();

  // ── Utility ──
  function generateSessionId() {
    return "sess-" + Math.random().toString(36).substring(2, 10);
  }

  function formatTime(date) {
    return date.toLocaleTimeString("en-US", { hour12: true, hour: "2-digit", minute: "2-digit", second: "2-digit" });
  }

  // ═══════════════════════════════════════
  //  MICROPHONE RECORDING
  // ═══════════════════════════════════════

  async function startRecording() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

      // Set up audio context + analyser for waveform
      audioContext = new (window.AudioContext || window.webkitAudioContext)();
      const source = audioContext.createMediaStreamSource(stream);
      analyser = audioContext.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);

      // Start MediaRecorder
      mediaRecorder = new MediaRecorder(stream);
      audioChunks = [];

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunks.push(e.data);
      };

      mediaRecorder.onstop = () => {
        recordedBlob = new Blob(audioChunks, { type: "audio/wav" });
        recordedUrl = URL.createObjectURL(recordedBlob);
        const durationSec = ((Date.now() - recordStartTime) / 1000).toFixed(1);

        // Update audio details
        audioDetails.style.display = "block";
        audioDuration.textContent = durationSec + " s";
        audioTimestamp.textContent = formatTime(new Date());
        audioSession.textContent = sessionId;

        // Enable playback button
        btnPlayRec.disabled = false;

        // Stop waveform
        cancelAnimationFrame(animFrameId);
        waveContainer.classList.remove("active");

        // Close audio context
        if (audioContext) { audioContext.close(); audioContext = null; }

        // Stop all tracks
        stream.getTracks().forEach(t => t.stop());

        // Send to backend
        sendToBackend(recordedBlob, durationSec);
      };

      recordStartTime = Date.now();
      mediaRecorder.start();
      isRecording = true;

      // Update UI
      micBtn.classList.add("mic-btn--recording");
      micLabel.textContent = "Recording… Tap to Stop";
      btnRecord.innerHTML = '<i class="fas fa-stop"></i> Stop Recording';
      waveContainer.classList.add("active");

      // Start waveform animation
      drawWaveform();

      // Animate pipeline stage 1
      setStageState(1, "processing", "Capturing audio…");

    } catch (err) {
      console.error("Mic access denied:", err);
      micLabel.textContent = "Mic access denied. Please allow microphone.";
    }
  }

  function stopRecording() {
    if (mediaRecorder && mediaRecorder.state !== "inactive") {
      mediaRecorder.stop();
    }
    isRecording = false;
    micBtn.classList.remove("mic-btn--recording");
    micLabel.textContent = "Tap to Record";
    btnRecord.innerHTML = '<i class="fas fa-circle"></i> Record Voice';
  }

  function toggleRecording() {
    if (isRecording) {
      stopRecording();
    } else {
      // Reset previous state
      resetPipeline();
      btnPlayRec.disabled = true;
      btnPlayAI.disabled = true;
      aiAudioUrl = null;
      audioDetails.style.display = "none";
      sessionId = generateSessionId();
      startRecording();
    }
  }

  // Both mic button and Record Voice button trigger recording
  micBtn.addEventListener("click", toggleRecording);
  btnRecord.addEventListener("click", toggleRecording);

  // ═══════════════════════════════════════
  //  WAVEFORM DRAWING
  // ═══════════════════════════════════════

  function drawWaveform() {
    if (!analyser) return;
    const ctx = waveCanvas.getContext("2d");
    const bufLen = analyser.frequencyBinCount;
    const data = new Uint8Array(bufLen);

    function draw() {
      animFrameId = requestAnimationFrame(draw);
      analyser.getByteTimeDomainData(data);

      ctx.fillStyle = "rgba(0, 0, 0, 0.2)";
      ctx.fillRect(0, 0, waveCanvas.width, waveCanvas.height);

      ctx.lineWidth = 2;
      ctx.strokeStyle = "#6366f1";
      ctx.beginPath();

      const sliceWidth = waveCanvas.width / bufLen;
      let x = 0;
      for (let i = 0; i < bufLen; i++) {
        const v = data[i] / 128.0;
        const y = (v * waveCanvas.height) / 2;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
        x += sliceWidth;
      }
      ctx.lineTo(waveCanvas.width, waveCanvas.height / 2);
      ctx.stroke();
    }
    draw();
  }

  // ═══════════════════════════════════════
  //  PLAYBACK CONTROLS
  // ═══════════════════════════════════════

  btnPlayRec.addEventListener("click", () => {
    if (recordedUrl) {
      const audio = new Audio(recordedUrl);
      audio.play();
    }
  });

  btnPlayAI.addEventListener("click", () => {
    if (aiAudioUrl) {
      const audio = new Audio(aiAudioUrl);
      audio.play();
    }
  });

  // ═══════════════════════════════════════
  //  PIPELINE ANIMATION
  // ═══════════════════════════════════════

  function setStageState(stageNum, state, detail) {
    const node = document.getElementById("stage" + stageNum);
    const detailEl = document.getElementById("stage" + stageNum + "Detail");
    const statusEl = node ? node.querySelector(".pipeline-node__status") : null;

    if (!node) return;

    // Remove old states
    node.classList.remove("pipeline-node--processing", "pipeline-node--completed");

    if (state === "processing") {
      node.classList.add("pipeline-node--processing");
      if (statusEl) statusEl.textContent = "Processing";
      pipelineBadge.textContent = "Processing";
      pipelineBadge.classList.add("panel__badge--processing");
      pipelineBadge.classList.remove("panel__badge--active");
    } else if (state === "completed") {
      node.classList.add("pipeline-node--completed");
      if (statusEl) statusEl.textContent = "Done";
      // Light up connector leading to next stage
      const conn = document.getElementById("conn" + stageNum);
      if (conn) conn.classList.add("pipeline-connector--lit");
    }

    if (detailEl && detail) detailEl.textContent = detail;
  }

  function resetPipeline() {
    for (let i = 1; i <= 7; i++) {
      const node = document.getElementById("stage" + i);
      const detailEl = document.getElementById("stage" + i + "Detail");
      const statusEl = node ? node.querySelector(".pipeline-node__status") : null;
      const conn = document.getElementById("conn" + i);
      if (node) node.classList.remove("pipeline-node--processing", "pipeline-node--completed");
      if (statusEl) statusEl.textContent = "Pending";
      if (detailEl) detailEl.textContent = "";
      if (conn) conn.classList.remove("pipeline-connector--lit");
    }
    pipelineBadge.textContent = "Idle";
    pipelineBadge.classList.remove("panel__badge--active", "panel__badge--processing");
  }

  // Each pipeline step runs for 4 seconds (prototype demo timing)
  const STEP_DURATION = 4000;

  async function animatePipeline(transcript, intent, responseText) {
    // Stage 1 — Voice Input: already completed before this is called
    setStageState(1, "completed", "Audio captured");
    await sleep(STEP_DURATION);

    // Stage 2 — Speech Recognition
    setStageState(2, "processing", "Transcribing…");
    await sleep(STEP_DURATION);
    setStageState(2, "completed", truncate(transcript, 30));

    // Stage 3 — Intent Detection
    setStageState(3, "processing", "Classifying…");
    await sleep(STEP_DURATION);
    setStageState(3, "completed", intent || "general");

    // Stage 4 — Task Router
    setStageState(4, "processing", "Routing…");
    await sleep(STEP_DURATION);
    setStageState(4, "completed", "API route");

    // Stage 5 — Data Retrieval
    setStageState(5, "processing", "Fetching data…");
    await sleep(STEP_DURATION);
    setStageState(5, "completed", "Data ready");

    // Stage 6 — Response Generation
    setStageState(6, "processing", "Generating…");
    await sleep(STEP_DURATION);
    setStageState(6, "completed", truncate(responseText, 30));

    // Stage 7 — Voice Output
    setStageState(7, "processing", "Synthesizing…");
    await sleep(STEP_DURATION);
    setStageState(7, "completed", "Audio ready");

    pipelineBadge.textContent = "Complete";
    pipelineBadge.classList.remove("panel__badge--processing");
    pipelineBadge.classList.add("panel__badge--active");
  }

  function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  function truncate(str, len) {
    if (!str) return "";
    return str.length > len ? str.substring(0, len) + "…" : str;
  }

  // ═══════════════════════════════════════
  //  SEND AUDIO TO BACKEND
  // ═══════════════════════════════════════

  async function sendToBackend(blob, durationSec) {
    const startTime = performance.now();

    try {
      const formData = new FormData();
      formData.append("audio", blob, "recording.wav");

      const resp = await fetch(API_BASE + "/voice/voice-query", {
        method: "POST",
        body: formData,
      });

      const elapsed = ((performance.now() - startTime) / 1000).toFixed(1);

      if (!resp.ok) {
        const errData = await resp.json().catch(() => ({}));
        throw new Error(errData.detail || resp.statusText);
      }

      const data = await resp.json();
      // data: { transcript, intent, response_text, audio_url }

      // Update data panel
      updateDataPanel(data, elapsed);

      // Animate pipeline
      await animatePipeline(data.transcript, data.intent, data.response_text);

      // Add log entries
      addLogEntry("user", data.transcript, data.intent || "Query", elapsed);
      addLogEntry("ai", data.response_text, "Response", "0.4");

      // Add summary items
      updateSummary(data);

      // AI playback (if audio_url returned)
      if (data.audio_url) {
        aiAudioUrl = data.audio_url;
        btnPlayAI.disabled = false;
      }

      // Footer
      footerLatency.textContent = elapsed + " s";
      footerUpdated.textContent = "Just now";

    } catch (err) {
      console.error("Backend not available — running prototype demo mode.");
      // Prototype fallback: simulate full pipeline with mock data
      const mockData = {
        transcript: "Where is my order 12345?",
        intent: "Order Tracking",
        response_text: "Your order #12345 has left the Chennai warehouse and will arrive tomorrow by 5 PM.",
        audio_url: null,
      };
      const mockElapsed = "4.0";

      micLabel.textContent = "Processing (demo mode)…";

      updateDataPanel(mockData, mockElapsed);
      await animatePipeline(mockData.transcript, mockData.intent, mockData.response_text);

      addLogEntry("user", mockData.transcript, mockData.intent, mockElapsed);
      addLogEntry("ai", mockData.response_text, "Response", "0.4");
      updateSummary(mockData);

      footerLatency.textContent = mockElapsed + " s";
      footerUpdated.textContent = "Just now";
      micLabel.textContent = "Tap to Record";
    }
  }

  // ═══════════════════════════════════════
  //  DATA PANEL UPDATES
  // ═══════════════════════════════════════

  function updateDataPanel(data, elapsed) {
    // Intent card
    if (intentType) intentType.textContent = data.intent || "general";
    const conf = Math.floor(Math.random() * 15 + 80); // simulated confidence
    if (confidenceBar) confidenceBar.style.width = conf + "%";
    if (confidenceVal) confidenceVal.textContent = conf + " %";

    // API response card (fill with available data)
    if (apiOrderId) apiOrderId.textContent = extractOrderId(data.transcript) || "—";
    if (apiWarehouse) apiWarehouse.textContent = "—";
    if (apiStatus) apiStatus.textContent = data.intent || "processed";
    if (apiEta) apiEta.textContent = elapsed + " s round-trip";
  }

  function extractOrderId(text) {
    if (!text) return null;
    const match = text.match(/\b(\d{3,})\b/);
    return match ? "ORD-" + match[1] : null;
  }

  function updateSummary(data) {
    if (!summaryList) return;
    summaryList.innerHTML = "";
    addSummaryItem("Voice input captured", true);
    addSummaryItem("Transcript: " + truncate(data.transcript, 50), true);
    addSummaryItem("Intent: " + (data.intent || "general"), true);
    addSummaryItem("Response generated", true);
  }

  function addSummaryItem(text, done) {
    const div = document.createElement("div");
    div.className = "summary-item" + (done ? " summary-item--done" : "");
    div.innerHTML = '<i class="fas fa-circle-dot"></i> ' + text;
    summaryList.appendChild(div);
  }

  // ═══════════════════════════════════════
  //  CONVERSATION LOGS
  // ═══════════════════════════════════════

  function addLogEntry(role, text, tag, elapsed) {
    if (!logsBody) return;
    const isUser = role === "user";
    const div = document.createElement("div");
    div.className = "log-message log-message--" + role;
    div.innerHTML = `
      <div class="log-avatar"><i class="fas fa-${isUser ? "user" : "robot"}"></i></div>
      <div class="log-content">
        <div class="log-text">"${escapeHtml(text)}"</div>
        <div class="log-meta">
          <span><i class="fas fa-clock"></i> ${formatTime(new Date())}</span>
          <span><i class="fas fa-tag"></i> ${tag}</span>
          <span><i class="fas fa-stopwatch"></i> ${elapsed} s</span>
        </div>
      </div>
    `;
    logsBody.appendChild(div);
    logsBody.scrollTop = logsBody.scrollHeight;
  }

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str || "";
    return div.innerHTML;
  }

  // ═══════════════════════════════════════
  //  LOGS TOGGLE (collapse / expand)
  // ═══════════════════════════════════════

  if (logsToggle) {
    logsToggle.addEventListener("click", () => {
      logsBody.classList.toggle("collapsed");
      const btn = logsToggle.querySelector(".expand-btn");
      if (btn) btn.classList.toggle("rotated");
    });
  }

  // ═══════════════════════════════════════
  //  SIDEBAR NAVIGATION (highlight active)
  // ═══════════════════════════════════════

  document.querySelectorAll(".sidebar__item").forEach((item) => {
    item.addEventListener("click", () => {
      document.querySelectorAll(".sidebar__item").forEach(i => i.classList.remove("sidebar__item--active"));
      item.classList.add("sidebar__item--active");
    });
  });

})();
