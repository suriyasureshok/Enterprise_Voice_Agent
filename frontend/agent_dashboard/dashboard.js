/* ═══════════════════════════════════════════════════════════
   VoiceOps AI Gateway — Dashboard JavaScript (Fully Integrated)
   Handles: mic recording, text input, waveform, pipeline animation,
            voice controls, logs, backend API calls, health polling
   ═══════════════════════════════════════════════════════════ */

(() => {
  "use strict";

  // ── Backend URL ──
  const API_BASE = "http://localhost:8000";
  const HEALTH_URL = `${API_BASE}/health`;
  const VOICE_URL = `${API_BASE}/voice/voice-query`;

  // ── DOM References ──
  const micBtn         = document.getElementById("micBtn");
  const micLabel       = document.getElementById("micLabel");
  const waveContainer  = document.getElementById("waveformContainer");
  const waveCanvas     = document.getElementById("waveCanvas");
  const btnRecord      = document.getElementById("btnRecord");
  const btnPlayRec     = document.getElementById("btnPlayRec");
  const btnPlayAI      = document.getElementById("btnPlayAI");
  const textInput      = document.getElementById("textInput");
  const btnSendText    = document.getElementById("btnSendText");
  const audioDetails   = document.getElementById("audioDetails");
  const audioDuration  = document.getElementById("audioDuration");
  const audioTimestamp  = document.getElementById("audioTimestamp");
  const audioSession   = document.getElementById("audioSession");
  const pipelineBadge  = document.getElementById("pipelineBadge");
  const logsToggle     = document.getElementById("logsToggle");
  const logsBody       = document.getElementById("logsBody");

  // Data panel elements
  const intentType     = document.getElementById("intentType");
  const confidenceBar  = document.getElementById("confidenceBar");
  const confidenceVal  = document.getElementById("confidenceVal");
  const entitiesVal    = document.getElementById("entitiesVal");
  const escalationVal  = document.getElementById("escalationVal");
  const apiTranscript  = document.getElementById("apiTranscript");
  const apiOrderId     = document.getElementById("apiOrderId");
  const apiStatus      = document.getElementById("apiStatus");
  const apiTicket      = document.getElementById("apiTicket");
  const apiLatency     = document.getElementById("apiLatency");
  const summaryList    = document.getElementById("summaryList");

  // Footer
  const footerDot      = document.getElementById("footerDot");
  const footerGateway  = document.getElementById("footerGateway");
  const footerLatency  = document.getElementById("footerLatency");
  const footerQueries  = document.getElementById("footerQueries");
  const footerUpdated  = document.getElementById("footerUpdated");

  // Router paths
  const routeKB    = document.getElementById("routeKB");
  const routeAPI   = document.getElementById("routeAPI");
  const routeHuman = document.getElementById("routeHuman");

  // ── Recording State ──
  let isRecording      = false;
  let mediaRecorder    = null;   // kept for legacy reference
  let audioChunks      = [];     // kept for legacy reference
  let pcmChunks        = [];     // raw Float32 PCM samples
  let micStream        = null;   // MediaStream from getUserMedia
  let scriptProcessor  = null;   // ScriptProcessorNode for raw capture
  let recordedBlob     = null;
  let recordedUrl      = null;
  let aiAudioUrl       = null;
  let audioContext      = null;
  let analyser         = null;
  let animFrameId      = null;
  let recordStartTime  = null;
  let sessionId        = generateSessionId();
  let isBusy           = false;
  let backendOnline    = false;
  let queryCount       = 0;
  let latencySum       = 0;
  let healthTimer      = null;
  let lastResponseText = "";

  // ── Utility ──
  function generateSessionId() {
    return "sess-" + Math.random().toString(36).substring(2, 10);
  }

  function formatTime(date) {
    return date.toLocaleTimeString("en-US", { hour12: true, hour: "2-digit", minute: "2-digit", second: "2-digit" });
  }

  function truncate(str, len) {
    if (!str) return "";
    return str.length > len ? str.substring(0, len) + "…" : str;
  }

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str || "";
    return div.innerHTML;
  }

  function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

  // ═══════════════════════════════════════
  //  HEALTH CHECK + CONNECTION STATUS
  // ═══════════════════════════════════════

  async function checkHealth() {
    try {
      const r = await fetch(HEALTH_URL, { signal: AbortSignal.timeout(5000) });
      if (r.ok) {
        if (!backendOnline) {
          backendOnline = true;
          if (footerDot) footerDot.className = "footer-dot footer-dot--green";
          if (footerGateway) footerGateway.textContent = "Active";
          micLabel.textContent = "Tap to Record";
          setInputsEnabled(true);
        }
      } else {
        throw new Error(`HTTP ${r.status}`);
      }
    } catch {
      if (backendOnline || (footerGateway && footerGateway.textContent === "Connecting…")) {
        backendOnline = false;
        if (footerDot) footerDot.className = "footer-dot footer-dot--red";
        if (footerGateway) footerGateway.textContent = "Offline";
        micLabel.textContent = "Backend offline — start the server";
        setInputsEnabled(false);
      }
    }
    clearTimeout(healthTimer);
    healthTimer = setTimeout(checkHealth, backendOnline ? 15000 : 5000);
  }

  function setInputsEnabled(on) {
    btnRecord.disabled = !on;
    micBtn.style.opacity = on ? "" : "0.4";
    micBtn.style.pointerEvents = on ? "" : "none";
    if (btnSendText) btnSendText.disabled = !on;
    if (textInput) textInput.disabled = !on;
  }

  // Start health polling immediately
  checkHealth();

  // ═══════════════════════════════════════
  //  MICROPHONE RECORDING
  // ═══════════════════════════════════════

  // ── WAV encoding helpers (PCM → WAV blob) ──
  function encodeWavBlob(pcmArrays, sampleRate) {
    // Merge all Float32 chunks into one buffer
    const totalLen = pcmArrays.reduce((s, a) => s + a.length, 0);
    const merged   = new Float32Array(totalLen);
    let off = 0;
    for (const chunk of pcmArrays) { merged.set(chunk, off); off += chunk.length; }

    // Convert Float32 (-1..1) → Int16
    const pcm16 = new Int16Array(merged.length);
    for (let i = 0; i < merged.length; i++) {
      const s = Math.max(-1, Math.min(1, merged[i]));
      pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
    }

    // Build WAV file
    const wavBuf  = new ArrayBuffer(44 + pcm16.length * 2);
    const view    = new DataView(wavBuf);
    const writeStr = (o, s) => { for (let i = 0; i < s.length; i++) view.setUint8(o + i, s.charCodeAt(i)); };

    writeStr(0, "RIFF");
    view.setUint32(4, 36 + pcm16.length * 2, true);
    writeStr(8, "WAVE");
    writeStr(12, "fmt ");
    view.setUint32(16, 16, true);            // sub-chunk size
    view.setUint16(20, 1, true);             // PCM format
    view.setUint16(22, 1, true);             // mono
    view.setUint32(24, sampleRate, true);    // sample rate
    view.setUint32(28, sampleRate * 2, true);// byte rate
    view.setUint16(32, 2, true);             // block align
    view.setUint16(34, 16, true);            // bits per sample
    writeStr(36, "data");
    view.setUint32(40, pcm16.length * 2, true);

    const wavBytes = new Uint8Array(wavBuf);
    wavBytes.set(new Uint8Array(pcm16.buffer), 44);

    return new Blob([wavBytes], { type: "audio/wav" });
  }

  async function startRecording() {
    if (isBusy) return;
    try {
      // Request microphone with quality constraints
      micStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        }
      });

      audioContext = new (window.AudioContext || window.webkitAudioContext)();
      const source = audioContext.createMediaStreamSource(micStream);

      // Analyser for waveform visualisation (unchanged)
      analyser = audioContext.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);

      // ── Raw PCM capture via ScriptProcessorNode ──
      // bufferSize=4096, 1 input channel, 1 output channel
      scriptProcessor = audioContext.createScriptProcessor(4096, 1, 1);
      pcmChunks = [];

      scriptProcessor.onaudioprocess = (e) => {
        const input = e.inputBuffer.getChannelData(0);
        pcmChunks.push(new Float32Array(input));   // copy the buffer
      };

      source.connect(scriptProcessor);
      // Must connect to destination for the node to fire (output is silent)
      scriptProcessor.connect(audioContext.destination);

      recordStartTime = Date.now();
      isRecording = true;

      micBtn.classList.add("mic-btn--recording");
      micLabel.textContent = "Recording… Tap to Stop";
      btnRecord.innerHTML = '<i class="fas fa-stop"></i> Stop Recording';
      waveContainer.classList.add("active");

      drawWaveform();
      setStageState(1, "processing", "Capturing audio…");

    } catch (err) {
      console.error("Mic access denied:", err);
      micLabel.textContent = "Mic access denied — please allow microphone";
    }
  }

  function stopRecording() {
    isRecording = false;
    micBtn.classList.remove("mic-btn--recording");
    micLabel.textContent = "Tap to Record";
    btnRecord.innerHTML = '<i class="fas fa-circle"></i> Record Voice';

    // Disconnect ScriptProcessor & stop mic tracks
    if (scriptProcessor) { scriptProcessor.disconnect(); scriptProcessor = null; }

    const durationSec = ((Date.now() - recordStartTime) / 1000).toFixed(1);

    // Encode captured PCM to 16-bit mono WAV
    const sampleRate = audioContext ? audioContext.sampleRate : 16000;
    recordedBlob = encodeWavBlob(pcmChunks, sampleRate);
    recordedUrl  = URL.createObjectURL(recordedBlob);

    console.log(`[VoxOps] Recorded ${pcmChunks.length} chunks, WAV size=${recordedBlob.size}, rate=${sampleRate}`);

    audioDetails.style.display = "block";
    audioDuration.textContent = durationSec + " s";
    audioTimestamp.textContent = formatTime(new Date());
    audioSession.textContent = sessionId;

    btnPlayRec.disabled = false;

    cancelAnimationFrame(animFrameId);
    waveContainer.classList.remove("active");

    if (audioContext) { audioContext.close(); audioContext = null; }
    if (micStream) { micStream.getTracks().forEach(t => t.stop()); micStream = null; }

    sendToBackend(recordedBlob, null, durationSec);
  }

  function toggleRecording() {
    if (isBusy) return;
    if (isRecording) {
      stopRecording();
    } else {
      resetPipeline();
      btnPlayRec.disabled = true;
      btnPlayAI.disabled = true;
      aiAudioUrl = null;
      audioDetails.style.display = "none";
      sessionId = generateSessionId();
      startRecording();
    }
  }

  micBtn.addEventListener("click", toggleRecording);
  btnRecord.addEventListener("click", toggleRecording);

  // ═══════════════════════════════════════
  //  TEXT INPUT
  // ═══════════════════════════════════════

  function sendTextQuery() {
    if (isBusy || !backendOnline) return;
    const q = textInput.value.trim();
    if (!q) return;
    textInput.value = "";
    resetPipeline();
    btnPlayRec.disabled = true;
    btnPlayAI.disabled = true;
    audioDetails.style.display = "none";
    sessionId = generateSessionId();

    setStageState(1, "completed", "Text input");
    sendToBackend(null, q, null);
  }

  if (btnSendText) btnSendText.addEventListener("click", sendTextQuery);
  if (textInput) textInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendTextQuery(); }
  });

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
    if (recordedUrl) new Audio(recordedUrl).play();
  });

  btnPlayAI.addEventListener("click", () => {
    if (aiAudioUrl) new Audio(aiAudioUrl).play();
    else if (lastResponseText) speakText(lastResponseText);
  });

  function speakText(text) {
    if (!("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    const utter = new SpeechSynthesisUtterance(text);
    utter.rate = 0.95;
    utter.pitch = 1.0;
    const voices = window.speechSynthesis.getVoices();
    const preferred = voices.find(v => /en[-_](US|GB)/i.test(v.lang));
    if (preferred) utter.voice = preferred;
    window.speechSynthesis.speak(utter);
  }
  window.speechSynthesis?.addEventListener("voiceschanged", () => {});

  // ═══════════════════════════════════════
  //  PIPELINE ANIMATION
  // ═══════════════════════════════════════

  function setStageState(stageNum, state, detail) {
    const node = document.getElementById("stage" + stageNum);
    const detailEl = document.getElementById("stage" + stageNum + "Detail");
    const statusEl = node ? node.querySelector(".pipeline-node__status") : null;
    if (!node) return;

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
    [routeKB, routeAPI, routeHuman].forEach(r => r?.classList.remove("router-path--selected"));
  }

  // Real-time pipeline: animate stages with brief pauses so user can see flow
  async function animatePipelineReal(data, elapsed) {
    const STEP = 600;

    setStageState(1, "completed", data.transcript ? "Audio captured" : "Text input");
    await sleep(STEP);

    setStageState(2, "processing", "Transcribing…");
    await sleep(STEP);
    setStageState(2, "completed", truncate(data.transcript, 40));
    await sleep(STEP);

    setStageState(3, "processing", "Classifying…");
    await sleep(STEP);
    const confPct = Math.round((data.confidence || 0) * 100);
    setStageState(3, "completed", `${data.intent || "unknown"} (${confPct}%)`);
    await sleep(STEP);

    setStageState(4, "processing", "Routing…");
    await sleep(STEP);
    const routeLabel = getRouteLabel(data.intent, data.needs_escalation);
    setStageState(4, "completed", routeLabel);
    highlightRoute(data.intent, data.needs_escalation);
    await sleep(STEP);

    setStageState(5, "processing", "Fetching data…");
    await sleep(STEP);
    setStageState(5, "completed", "Data ready");
    await sleep(STEP);

    setStageState(6, "processing", "Generating…");
    await sleep(STEP);
    setStageState(6, "completed", truncate(data.response_text, 40));
    await sleep(STEP);

    setStageState(7, "processing", "Synthesizing…");
    await sleep(STEP);
    setStageState(7, "completed", "Audio ready");

    pipelineBadge.textContent = "Complete";
    pipelineBadge.classList.remove("panel__badge--processing");
    pipelineBadge.classList.add("panel__badge--active");
  }

  function getRouteLabel(intent, escalation) {
    if (escalation) return "Human Escalation";
    if (["faq", "unknown"].includes(intent)) return "Knowledge Base";
    return "Enterprise API";
  }

  function highlightRoute(intent, escalation) {
    [routeKB, routeAPI, routeHuman].forEach(r => r?.classList.remove("router-path--selected"));
    if (escalation) {
      routeHuman?.classList.add("router-path--selected");
    } else if (["faq", "unknown"].includes(intent)) {
      routeKB?.classList.add("router-path--selected");
    } else {
      routeAPI?.classList.add("router-path--selected");
    }
  }

  // ═══════════════════════════════════════
  //  SEND TO BACKEND
  // ═══════════════════════════════════════

  async function sendToBackend(audioBlob, textQuery, durationSec) {
    if (isBusy) return;
    isBusy = true;
    setInputsEnabled(false);

    // Show immediate feedback to user
    micLabel.textContent = "Processing query…";
    pipelineBadge.textContent = "Processing";
    pipelineBadge.classList.add("panel__badge--processing");

    const startTime = performance.now();

    try {
      const formData = new FormData();
      if (audioBlob) {
        // Determine file extension from MIME type
        let ext = ".webm";
        if (audioBlob.type.includes("wav"))       ext = ".wav";
        else if (audioBlob.type.includes("ogg"))  ext = ".ogg";
        formData.append("audio", audioBlob, `recording${ext}`);
      } else if (textQuery) {
        formData.append("text", textQuery);
      }

      if (!audioBlob) {
        setStageState(1, "completed", "Text input");
      }

      // Show user the query is being processed (LLM can take 30-90s on free tier)
      setStageState(2, "processing", audioBlob ? "Transcribing…" : "Sending to AI…");

      const resp = await fetch(VOICE_URL, {
        method: "POST",
        body: formData,
        signal: AbortSignal.timeout(120000),  // 2 min — free-tier LLM is slow
      });

      const elapsed = ((performance.now() - startTime) / 1000).toFixed(2);

      if (!resp.ok) {
        const errData = await resp.json().catch(() => ({}));
        throw new Error(errData.detail || `HTTP ${resp.status}`);
      }

      const data = await resp.json();

      queryCount++;
      latencySum += parseFloat(elapsed);

      updateDataPanel(data, elapsed);
      updateFooter(elapsed);

      await animatePipelineReal(data, elapsed);

      addLogEntry("user", data.transcript || textQuery, data.intent || "query", elapsed);
      addLogEntry("ai", data.response_text, "Response", "0.3");

      updateSummary(data, elapsed);

      lastResponseText = data.response_text || "";
      if (data.audio_url) {
        aiAudioUrl = data.audio_url.startsWith("http") ? data.audio_url : API_BASE + data.audio_url;
      }
      btnPlayAI.disabled = false;

      speakText(data.response_text);

    } catch (err) {
      console.error("Backend error:", err);
      const isTimeout = err.name === "TimeoutError" || err.message?.includes("timed out");
      const errMsg = isTimeout
        ? "Request timed out — the AI model is slow. Please try again."
        : `Error: ${err.message}`;
      addLogEntry("ai", errMsg, "Error", "—");
      setStageState(2, "completed", isTimeout ? "Timed out" : "Error!");
      pipelineBadge.textContent = "Error";
      pipelineBadge.classList.remove("panel__badge--processing");
    } finally {
      isBusy = false;
      setInputsEnabled(backendOnline);
      micLabel.textContent = "Tap to Record";
    }
  }

  // ═══════════════════════════════════════
  //  DATA PANEL UPDATES (Real Data)
  // ═══════════════════════════════════════

  function updateDataPanel(data, elapsed) {
    if (intentType) intentType.textContent = data.intent || "unknown";
    const conf = Math.round((data.confidence || 0) * 100);
    if (confidenceBar) confidenceBar.style.width = conf + "%";
    if (confidenceVal) confidenceVal.textContent = conf + " %";

    if (entitiesVal) {
      if (data.entities && Object.keys(data.entities).length > 0) {
        entitiesVal.innerHTML = Object.entries(data.entities)
          .map(([k, v]) => `<span class="entity-pill">${escapeHtml(k)}: ${escapeHtml(String(v))}</span>`)
          .join(" ");
      } else {
        entitiesVal.textContent = "none";
      }
    }

    if (escalationVal) {
      if (data.needs_escalation) {
        escalationVal.innerHTML = '<span class="badge badge--escalation">YES</span>';
      } else {
        escalationVal.textContent = "No";
      }
    }

    if (apiTranscript) apiTranscript.textContent = truncate(data.transcript, 80) || "—";
    if (apiOrderId) apiOrderId.textContent = (data.entities && data.entities.order_id) || "—";
    if (apiStatus) {
      apiStatus.textContent = data.intent || "—";
      apiStatus.className = "badge " + (data.needs_escalation ? "badge--escalation" : "badge--transit");
    }
    if (apiTicket) apiTicket.textContent = data.ticket_id || "—";
    if (apiLatency) apiLatency.textContent = elapsed + " s";
  }

  function updateFooter(elapsed) {
    if (footerLatency) footerLatency.textContent = (latencySum / queryCount).toFixed(1) + " s";
    if (footerQueries) footerQueries.textContent = queryCount;
    if (footerUpdated) footerUpdated.textContent = formatTime(new Date());
  }

  function updateSummary(data, elapsed) {
    if (!summaryList) return;
    summaryList.innerHTML = "";
    addSummaryItem("Voice/text input captured", true);
    addSummaryItem("Transcript: " + truncate(data.transcript, 50), true);
    addSummaryItem(`Intent: ${data.intent} (${Math.round((data.confidence || 0) * 100)}%)`, true);
    if (data.entities && Object.keys(data.entities).length > 0) {
      addSummaryItem("Entities: " + Object.entries(data.entities).map(([k,v]) => `${k}=${v}`).join(", "), true);
    }
    addSummaryItem("Response generated (" + elapsed + "s)", true);
    if (data.needs_escalation) {
      addSummaryItem("Escalated to human agent — Ticket: " + (data.ticket_id || "pending"), true);
    }
    if (data.ticket_id) {
      addSummaryItem("Ticket ID: " + data.ticket_id, true);
    }
  }

  function addSummaryItem(text, done) {
    const div = document.createElement("div");
    div.className = "summary-item" + (done ? " summary-item--done" : "");
    div.innerHTML = '<i class="fas fa-circle-dot"></i> ' + escapeHtml(text);
    summaryList.appendChild(div);
  }

  // ═══════════════════════════════════════
  //  CONVERSATION LOGS
  // ═══════════════════════════════════════

  // Clear initial placeholder logs
  if (logsBody) logsBody.innerHTML = "";

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
          <span><i class="fas fa-tag"></i> ${escapeHtml(tag)}</span>
          <span><i class="fas fa-stopwatch"></i> ${elapsed} s</span>
        </div>
      </div>
    `;
    logsBody.appendChild(div);
    logsBody.scrollTop = logsBody.scrollHeight;
  }

  // ═══════════════════════════════════════
  //  LOGS TOGGLE
  // ═══════════════════════════════════════

  if (logsToggle) {
    logsToggle.addEventListener("click", () => {
      logsBody.classList.toggle("collapsed");
      const btn = logsToggle.querySelector(".expand-btn");
      if (btn) btn.classList.toggle("rotated");
    });
  }

  // ═══════════════════════════════════════
  //  SIDEBAR NAVIGATION (scroll to sections)
  // ═══════════════════════════════════════

  const sectionMap = {
    "dashboard": null,               // scroll to top
    "voice":    ".voice-panel",
    "pipeline": ".pipeline-panel",
    "router":   ".router-section",
    "data":     "#sectionData",
  };

  document.querySelectorAll(".sidebar__item").forEach((item) => {
    item.addEventListener("click", () => {
      document.querySelectorAll(".sidebar__item").forEach(i => i.classList.remove("sidebar__item--active"));
      item.classList.add("sidebar__item--active");

      const page = item.dataset.page;
      const selector = sectionMap[page];
      if (selector) {
        const el = document.querySelector(selector);
        if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
      } else {
        window.scrollTo({ top: 0, behavior: "smooth" });
      }
    });
  });

  // ═══════════════════════════════════════
  //  ENTERPRISE DATA — ORDERS TABLE
  // ═══════════════════════════════════════

  const ORDERS_URL    = `${API_BASE}/orders/`;
  const SIM_URL       = (orderId) => `${API_BASE}/simulation/predict-delivery/${orderId}`;
  const ordersBody    = document.getElementById("ordersTableBody");
  const btnRefresh    = document.getElementById("btnRefreshOrders");
  const filterSelect  = document.getElementById("orderFilterStatus");
  const simResult     = document.getElementById("simulationResult");
  const simContent    = document.getElementById("simulationContent");

  async function loadOrders() {
    if (!backendOnline) return;
    const status = filterSelect ? filterSelect.value : "";
    const url = status ? `${ORDERS_URL}?status=${status}` : ORDERS_URL;

    try {
      ordersBody.innerHTML = '<tr><td colspan="8" style="text-align:center;color:rgba(255,255,255,0.5);padding:18px;"><i class="fas fa-spinner fa-pulse"></i> Loading…</td></tr>';

      const resp = await fetch(url, { signal: AbortSignal.timeout(10000) });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

      const orders = await resp.json();

      if (orders.length === 0) {
        ordersBody.innerHTML = '<tr><td colspan="8" style="text-align:center;color:rgba(255,255,255,0.35);padding:22px;">No orders found.</td></tr>';
        return;
      }

      ordersBody.innerHTML = orders.map(o => `
        <tr>
          <td><strong style="color:var(--accent-light);font-family:var(--font-mono);">${escapeHtml(o.order_id)}</strong></td>
          <td>${escapeHtml(o.customer_id)}</td>
          <td>${escapeHtml(o.origin)}</td>
          <td>${escapeHtml(o.destination)}</td>
          <td>${escapeHtml(o.vehicle_id || '—')}</td>
          <td>${o.distance} km</td>
          <td><span class="badge badge--${o.status === 'delivered' ? 'delivered' : 'transit'}">${escapeHtml(o.status)}</span></td>
          <td>
            <button class="ctrl-btn" style="font-size:0.7rem;padding:4px 10px;" onclick="window._predictDelivery('${escapeHtml(o.order_id)}')">
              <i class="fas fa-truck-fast"></i> Predict
            </button>
          </td>
        </tr>
      `).join("");

    } catch (err) {
      ordersBody.innerHTML = `<tr><td colspan="8" style="text-align:center;color:var(--red);padding:18px;">Error: ${escapeHtml(err.message)}</td></tr>`;
    }
  }

  // Expose predict function for inline onclick
  window._predictDelivery = async function(orderId) {
    if (!simResult || !simContent) return;
    simResult.style.display = "block";
    simContent.innerHTML = '<div style="text-align:center;padding:12px;color:rgba(255,255,255,0.5);"><i class="fas fa-spinner fa-pulse"></i> Running simulation for ' + escapeHtml(orderId) + '…</div>';

    try {
      const resp = await fetch(SIM_URL(orderId), { signal: AbortSignal.timeout(20000) });
      if (!resp.ok) {
        const errData = await resp.json().catch(() => ({}));
        throw new Error(errData.detail || `HTTP ${resp.status}`);
      }
      const d = await resp.json();

      simContent.innerHTML = `
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:10px;">
          <div class="data-row"><span>Order</span><span style="color:var(--accent-light);font-weight:700;">${escapeHtml(d.order_id)}</span></div>
          <div class="data-row"><span>Route</span><span>${escapeHtml(d.origin)} → ${escapeHtml(d.destination)}</span></div>
          <div class="data-row"><span>Vehicle</span><span>${escapeHtml(d.vehicle_id || '—')}</span></div>
          <div class="data-row"><span>Distance</span><span>${d.route.distance_km} km</span></div>
          <div class="data-row"><span>Traffic</span><span class="badge badge--transit">${escapeHtml(d.route.traffic_level)}</span></div>
          <div class="data-row"><span>Travel Time</span><span>${d.route.total_time_minutes.toFixed(0)} min</span></div>
          <div class="data-row"><span>Warehouse</span><span>${escapeHtml(d.warehouse.warehouse_id)}</span></div>
          <div class="data-row"><span>WH Processing</span><span>${d.warehouse.total_warehouse_minutes.toFixed(0)} min</span></div>
          <div class="data-row"><span>Total ETA</span><span style="color:var(--green);font-weight:700;font-size:1rem;">${d.total_hours.toFixed(1)} hrs (${d.total_minutes.toFixed(0)} min)</span></div>
          <div class="data-row"><span>Delay Prob.</span><span style="color:${d.delay_probability > 0.5 ? 'var(--red)' : 'var(--green)'};">${(d.delay_probability * 100).toFixed(0)}%</span></div>
          <div class="data-row" style="grid-column:1/-1;"><span>Confidence</span><span>${escapeHtml(d.confidence)}</span></div>
          <div class="data-row" style="grid-column:1/-1;"><span>Summary</span><span style="color:#fff;white-space:normal;word-break:break-word;">${escapeHtml(d.summary)}</span></div>
        </div>
      `;
    } catch (err) {
      simContent.innerHTML = `<div style="color:var(--red);padding:10px;"><i class="fas fa-exclamation-triangle"></i> ${escapeHtml(err.message)}</div>`;
    }
  };

  if (btnRefresh) btnRefresh.addEventListener("click", loadOrders);
  if (filterSelect) filterSelect.addEventListener("change", loadOrders);

  // Auto-load orders on startup once backend is online
  const _waitAndLoadOrders = setInterval(() => {
    if (backendOnline) {
      clearInterval(_waitAndLoadOrders);
      loadOrders();
    }
  }, 2000);

})();