/* ══════════════════════════════════════════════════════════════
   VoxOps AI — Phone-Call UI Application
   Voice fillers, live captions, call-screen experience
   ══════════════════════════════════════════════════════════════ */
(() => {
  "use strict";

  // Dynamically use the same host the page was loaded from (works for localhost AND remote IP)
  const API = window.location.origin;

  /* ─── Session Memory ─── */
  let sessionId = null;

  /* ─── Voice Fillers ─── */
  const FILLERS_THINKING = [
    "Umm, let me check that for you…",
    "One moment please…",
    "Hmm, just a second…",
    "Let me look that up…",
    "Bear with me…",
    "Fetching the details, please wait…",
    "Alright, pulling that up now…",
    "Give me just a moment…"
  ];
  const FILLERS_GREETING = [
    "Hey there! How can I help you today?",
    "Hi! VoxOps AI here. What can I do for you?",
    "Hello! I'm your logistics assistant. Go ahead!"
  ];

  /* ─── State ─── */
  let callActive = false;
  let callMuted = false;
  let callTimerSec = 0;
  let callTimerInterval = null;
  let mediaStream = null;
  let mediaRecorder = null;
  let audioChunks = [];
  let audioCtx = null;
  let analyser = null;
  let animFrame = null;
  let recognition = null;
  let recognitionResult = "";
  let recognitionRunning = false;
  let silenceTimer = null;
  let isProcessing = false;
  let allOrders = [];
  let lastFiller = -1;

  /* ─── DOM Refs ─── */
  const $ = (s) => document.querySelector(s);
  const $$ = (s) => document.querySelectorAll(s);

  const sidebar      = $("#sidebar");
  const overlay      = $("#sidebarOverlay");
  const menuToggle   = $("#menuToggle");
  const statusDot    = $("#statusDot");
  const statusDotM   = $("#statusDotMobile");
  const statusText   = $("#statusText");

  // Call idle
  const callIdleEl   = $("#callIdle");
  const callActiveEl = $("#callActive");
  const callStartBtn = $("#callStartBtn");
  const textInput    = $("#textInput");
  const sendBtn      = $("#sendBtn");

  // Call active
  const pulseRing    = $("#pulseRing");
  const callTimerEl  = $("#callTimer");
  const callStatusEl = $("#callStatus");
  const captionsBox  = $("#captionsBox");
  const captionsInner= $("#captionsInner");
  const waveCanvas   = $("#waveCanvas");
  const muteBtn      = $("#muteBtn");
  const callEndBtn   = $("#callEndBtn");
  const keypadBtn    = $("#keypadBtn");
  const callTypeArea = $("#callTypeArea");
  const callTextBox  = $("#callTextBox");
  const callSendBtn  = $("#callSendBtn");

  // Conversation log
  const convLog      = $("#convLog");
  const logBody      = $("#logBody");
  const clearLog     = $("#clearLog");

  // Pages
  const pages        = $$(".page");
  const navItems     = $$(".nav-item");

  /* ═════════════════════════════════════
     NAVIGATION
     ═════════════════════════════════════ */
  navItems.forEach(n => n.addEventListener("click", () => {
    const pg = n.dataset.page;
    navItems.forEach(x => x.classList.remove("active"));
    n.classList.add("active");
    pages.forEach(p => { p.classList.remove("page--active"); if (p.id === "page-" + pg) p.classList.add("page--active"); });
    sidebar.classList.remove("open"); overlay.classList.remove("show");
    if (pg === "orders")   loadOrders();
    if (pg === "tickets")  loadTickets();
  }));
  menuToggle.addEventListener("click", () => { sidebar.classList.toggle("open"); overlay.classList.toggle("show"); });
  overlay.addEventListener("click", () => { sidebar.classList.remove("open"); overlay.classList.remove("show"); });

  /* ═════════════════════════════════════
     HEALTH
     ═════════════════════════════════════ */
  async function checkHealth() {
    try {
      const r = await fetch(API + "/health", { signal: AbortSignal.timeout(4000) });
      if (r.ok) setStatus("online"); else setStatus("offline");
    } catch { setStatus("offline"); }
  }
  function setStatus(s) {
    const on = s === "online";
    statusDot.className  = "status-dot" + (on ? " online" : " offline");
    if (statusDotM) statusDotM.className = "status-dot-sm" + (on ? " online" : "");
    statusText.textContent = on ? "System Online" : "Offline";
  }
  checkHealth();
  setInterval(checkHealth, 15000);

  /* ═════════════════════════════════════
     TRANSCRIPT NORMALIZATION
     ═════════════════════════════════════ */
  function normalize(raw) {
    let t = raw;
    const wordNum = { zero:0,one:1,two:2,three:3,four:4,five:5,six:6,seven:7,eight:8,nine:9,ten:10,
      eleven:11,twelve:12,thirteen:13,fourteen:14,fifteen:15,sixteen:16,seventeen:17,eighteen:18,nineteen:19,
      twenty:20,thirty:30,forty:40,fifty:50 };
    // compound numbers like "twenty five"
    t = t.replace(/\b(twenty|thirty|forty|fifty)[- ]?(one|two|three|four|five|six|seven|eight|nine)\b/gi, (_, tens, ones) => {
      return String((wordNum[tens.toLowerCase()]||0)+(wordNum[ones.toLowerCase()]||0));
    });
    // simple word→number
    Object.entries(wordNum).forEach(([w, n]) => {
      t = t.replace(new RegExp("\\b" + w + "\\b", "gi"), String(n));
    });
    // "order 5" → "order ORD-005"
    t = t.replace(/\border[#\s-]*(\d{1,3})\b/gi, (_, n) => "order ORD-" + n.padStart(3, "0"));
    // "oh are dee" artefacts
    t = t.replace(/\boh\s*are\s*dee[- ]*(\d{1,3})\b/gi, (_, n) => "ORD-" + n.padStart(3, "0"));
    t = t.replace(/\bORD[- ]*(\d{1,3})\b/gi, (_, n) => "ORD-" + n.padStart(3, "0"));
    // "customer 5" → CUST-005
    t = t.replace(/\bcustomer[#\s-]*(\d{1,3})\b/gi, (_, n) => "customer CUST-" + n.padStart(3, "0"));
    t = t.replace(/\bCUST[- ]*(\d{1,3})\b/gi, (_, n) => "CUST-" + n.padStart(3, "0"));
    return t.trim();
  }

  /* ═════════════════════════════════════
     CALL FLOW
     ═════════════════════════════════════ */

  // Start call
  callStartBtn.addEventListener("click", startCall);

  async function startCall() {
    // Show active UI
    callIdleEl.hidden = true;
    callActiveEl.hidden = false;
    callActiveEl.style.display = "flex";
    convLog.hidden = false;
    callActive = true;
    isProcessing = false;
    callMuted = false;
    callTimerSec = 0;
    captionsInner.innerHTML = "";
    callStatusEl.textContent = "Connecting…";
    pulseRing.className = "pulse-ring ringing";

    // Timer
    callTimerInterval = setInterval(() => {
      callTimerSec++;
      const m = String(Math.floor(callTimerSec / 60)).padStart(2, "0");
      const s = String(callTimerSec % 60).padStart(2, "0");
      callTimerEl.textContent = m + ":" + s;
    }, 1000);

    // Open mic
    try {
      mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      setupAudio(mediaStream);
    } catch (e) {
      console.warn("Mic denied:", e);
    }

    // Greeting (after short pause)
    await delay(800);
    pulseRing.className = "pulse-ring speaking";
    callStatusEl.textContent = "Agent speaking…";
    const greeting = pick(FILLERS_GREETING);
    addCaption("agent", greeting);
    addLog("ai", greeting);
    await speakTTS(greeting);
    startListening();
  }

  // End call
  callEndBtn.addEventListener("click", endCall);

  function endCall() {
    callActive = false;
    sessionId = null;
    stopListening();
    stopAudio();
    clearInterval(callTimerInterval);
    callTimerInterval = null;
    pulseRing.className = "pulse-ring";
    callStatusEl.textContent = "Call ended";
    callTypeArea.hidden = true;

    // Back to idle after brief pause
    setTimeout(() => {
      callActiveEl.hidden = true;
      callActiveEl.style.display = "none";
      callIdleEl.hidden = false;
    }, 1200);
  }

  // Mute
  muteBtn.addEventListener("click", () => {
    callMuted = !callMuted;
    muteBtn.classList.toggle("active", callMuted);
    muteBtn.querySelector("i").className = callMuted ? "fas fa-microphone-slash" : "fas fa-microphone";
    muteBtn.querySelector("span").textContent = callMuted ? "Unmute" : "Mute";
    if (mediaStream) mediaStream.getAudioTracks().forEach(t => t.enabled = !callMuted);
    if (callMuted) stopListening(); else if (callActive && !isProcessing) startListening();
  });

  // Keypad toggle
  keypadBtn.addEventListener("click", () => {
    const show = callTypeArea.hidden;
    callTypeArea.hidden = !show;
    keypadBtn.classList.toggle("active", show);
    if (show) callTextBox.focus();
  });

  // Send from call text box
  callSendBtn.addEventListener("click", () => sendCallText());
  callTextBox.addEventListener("keydown", e => { if (e.key === "Enter") sendCallText(); });

  function sendCallText() {
    const txt = callTextBox.value.trim();
    if (!txt || isProcessing) return;
    callTextBox.value = "";
    processQuery(txt);
  }

  // Idle text input
  sendBtn.addEventListener("click", () => sendIdleText());
  textInput.addEventListener("keydown", e => { if (e.key === "Enter") sendIdleText(); });

  async function sendIdleText() {
    const txt = textInput.value.trim();
    if (!txt) return;
    textInput.value = "";
    // Auto-start call if not active
    if (!callActive) {
      callIdleEl.hidden = true;
      callActiveEl.hidden = false;
      callActiveEl.style.display = "flex";
      convLog.hidden = false;
      callActive = true;
      callTimerSec = 0;
      captionsInner.innerHTML = "";
      callStatusEl.textContent = "Connected";
      pulseRing.className = "pulse-ring";
      callTimerInterval = setInterval(() => {
        callTimerSec++;
        const m = String(Math.floor(callTimerSec / 60)).padStart(2, "0");
        const s = String(callTimerSec % 60).padStart(2, "0");
        callTimerEl.textContent = m + ":" + s;
      }, 1000);
    }
    processQuery(txt);
  }

  // Quick chips
  document.querySelectorAll(".chip").forEach(c => c.addEventListener("click", () => {
    const q = c.dataset.q;
    if (q) { textInput.value = q; sendIdleText(); }
  }));

  /* ═════════════════════════════════════
     PROCESS QUERY (core)
     ═════════════════════════════════════ */
  async function processQuery(text) {
    if (isProcessing) return;
    isProcessing = true;
    stopListening();

    const norm = normalize(text);
    addCaption("you", norm);
    addLog("user", norm);

    // Show filler while waiting
    callStatusEl.textContent = "Thinking…";
    pulseRing.className = "pulse-ring";
    const filler = pickFiller();
    addCaption("filler", filler);
    speakTTS(filler); // speak filler (non-blocking is fine)

    try {
      const fd = new FormData();
      fd.append("text", norm);
      if (sessionId) fd.append("session_id", sessionId);
      const r = await fetch(API + "/voice/voice-query", { method: "POST", body: fd });
      if (!r.ok) throw new Error("HTTP " + r.status);
      const data = await r.json();

      // Stop filler TTS if still playing
      window.speechSynthesis.cancel();

      if (data.session_id) sessionId = data.session_id;
      const answer = data.response_text || "Sorry, I didn't get that.";
      addCaption("agent", answer);
      addLog("ai", answer, data.intent, data.confidence);

      pulseRing.className = "pulse-ring speaking";
      callStatusEl.textContent = "Agent speaking…";
      await speakTTS(answer);

      if (data.needs_escalation && data.ticket_id) {
        const esc = "I've created ticket " + data.ticket_id + " for you. A human agent will follow up soon.";
        addCaption("agent", esc);
        addLog("ai", esc);
        await speakTTS(esc);
      }
    } catch (e) {
      console.error("Query error:", e);
      const errMsg = "Hmm, I'm having trouble connecting. Could you try again?";
      addCaption("agent", errMsg);
      addLog("ai", errMsg);
      await speakTTS(errMsg);
    }

    isProcessing = false;
    if (callActive && !callMuted) {
      callStatusEl.textContent = "Listening…";
      pulseRing.className = "pulse-ring";
      startListening();
    } else {
      callStatusEl.textContent = callActive ? "Muted" : "Call ended";
    }
  }

  /* ═════════════════════════════════════
     SPEECH RECOGNITION (Web Speech API)
     ═════════════════════════════════════ */
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

  function startListening() {
    if (!SpeechRecognition || recognitionRunning || isProcessing) return;
    recognition = new SpeechRecognition();
    recognition.lang = "en-US";
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.maxAlternatives = 3;
    recognitionResult = "";

    recognition.onresult = (e) => {
      let interim = "";
      let finalT = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const alt = pickBestAlt(e.results[i]);
        if (e.results[i].isFinal) finalT += alt;
        else interim += alt;
      }
      if (finalT) {
        recognitionResult += finalT;
        // User finished a phrase — wait 1.5s of silence then process
        clearTimeout(silenceTimer);
        silenceTimer = setTimeout(() => {
          if (recognitionResult.trim() && callActive && !isProcessing) {
            stopListening();
            clearLiveCaption();
            processQuery(recognitionResult.trim());
          }
        }, 1500);
      }
      // Show interim as live caption
      const live = (recognitionResult + " " + interim).trim();
      if (live) setLiveCaption(live);
    };

    recognition.onend = () => {
      recognitionRunning = false;
      if (recognitionResult.trim() && callActive && !isProcessing) {
        clearLiveCaption();
        processQuery(recognitionResult.trim());
      } else if (callActive && !isProcessing && !callMuted) {
        // Restart if still in call
        startListening();
      }
    };

    recognition.onerror = (e) => {
      if (e.error === "no-speech" || e.error === "aborted") return;
      console.warn("SpeechRecognition error:", e.error);
    };

    try {
      recognition.start();
      recognitionRunning = true;
      callStatusEl.textContent = "Listening…";
    } catch (e) { console.warn("Recognition start failed:", e); }
  }

  function stopListening() {
    clearTimeout(silenceTimer);
    if (recognition && recognitionRunning) {
      try { recognition.stop(); } catch {}
      recognitionRunning = false;
    }
  }

  function pickBestAlt(result) {
    // Prefer alternatives with ORD-/CUST- patterns
    const idPat = /\b(ORD|CUST|ord|cust)[- ]?\d/i;
    for (let i = 0; i < result.length; i++) {
      if (idPat.test(result[i].transcript)) return result[i].transcript;
    }
    return result[0].transcript;
  }

  /* ─── Live caption (interim) ─── */
  let liveCaptionEl = null;
  function setLiveCaption(text) {
    if (!liveCaptionEl) {
      liveCaptionEl = document.createElement("div");
      liveCaptionEl.className = "cap-line you";
      liveCaptionEl.style.opacity = ".55";
      liveCaptionEl.innerHTML = '<span class="cap-label">You</span><span class="cap-text"></span>';
      captionsInner.appendChild(liveCaptionEl);
    }
    liveCaptionEl.querySelector(".cap-text").textContent = text;
    captionsBox.scrollTop = captionsBox.scrollHeight;
  }
  function clearLiveCaption() {
    if (liveCaptionEl) { liveCaptionEl.remove(); liveCaptionEl = null; }
  }

  /* ═════════════════════════════════════
     CAPTIONS & LOG
     ═════════════════════════════════════ */
  function addCaption(role, text) {
    clearLiveCaption();
    const div = document.createElement("div");
    if (role === "filler") {
      div.className = "cap-line cap-filler";
      div.textContent = text;
    } else {
      div.className = "cap-line " + (role === "you" ? "you" : "agent");
      const label = role === "you" ? "You" : "Agent";
      div.innerHTML = '<span class="cap-label">' + label + '</span>' + escapeHtml(text);
    }
    captionsInner.appendChild(div);
    captionsBox.scrollTop = captionsBox.scrollHeight;
  }

  function addLog(role, text, intent, confidence) {
    const div = document.createElement("div");
    div.className = "log-msg " + (role === "user" ? "user" : "ai");
    let html = escapeHtml(text);
    if (intent || confidence) {
      html += '<div class="log-meta">';
      if (intent) html += '<span class="badge badge--intent">' + escapeHtml(intent) + '</span>';
      if (confidence != null) html += '<span class="badge badge--conf">' + (confidence * 100).toFixed(0) + '%</span>';
      html += '</div>';
    }
    div.innerHTML = html;
    logBody.appendChild(div);
    logBody.scrollTop = logBody.scrollHeight;
  }

  clearLog.addEventListener("click", () => { logBody.innerHTML = ""; });

  /* ═════════════════════════════════════
     TTS (Browser speechSynthesis)
     ═════════════════════════════════════ */
  function speakTTS(text) {
    return new Promise((resolve) => {
      if (!window.speechSynthesis || !text) { resolve(); return; }
      window.speechSynthesis.cancel();
      const utt = new SpeechSynthesisUtterance(text);
      utt.rate = 1.05;
      utt.pitch = 1;
      // Prefer a natural-sounding voice
      const voices = window.speechSynthesis.getVoices();
      const pref = voices.find(v => /samantha|zira|google us english|google uk english female/i.test(v.name));
      if (pref) utt.voice = pref;
      utt.onend = () => resolve();
      utt.onerror = () => resolve();
      window.speechSynthesis.speak(utt);
    });
  }
  // Load voices
  if (window.speechSynthesis) {
    window.speechSynthesis.getVoices();
    window.speechSynthesis.onvoiceschanged = () => window.speechSynthesis.getVoices();
  }

  /* ═════════════════════════════════════
     AUDIO VISUALIZER
     ═════════════════════════════════════ */
  function setupAudio(stream) {
    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    analyser = audioCtx.createAnalyser();
    analyser.fftSize = 256;
    const src = audioCtx.createMediaStreamSource(stream);
    src.connect(analyser);
    drawWaveform();
  }

  function drawWaveform() {
    if (!analyser) return;
    const bufLen = analyser.frequencyBinCount;
    const data = new Uint8Array(bufLen);
    const ctx = waveCanvas.getContext("2d");
    const W = waveCanvas.width, H = waveCanvas.height;

    function frame() {
      animFrame = requestAnimationFrame(frame);
      analyser.getByteFrequencyData(data);
      ctx.clearRect(0, 0, W, H);

      const bars = 40;
      const barW = W / bars;
      const step = Math.floor(bufLen / bars);
      for (let i = 0; i < bars; i++) {
        const val = data[i * step] / 255;
        const h = Math.max(2, val * H * 0.85);
        const x = i * barW;
        const y = (H - h) / 2;
        ctx.fillStyle = `rgba(129,140,248,${0.35 + val * 0.65})`;
        ctx.beginPath();
        ctx.roundRect(x + 1, y, barW - 2, h, 2);
        ctx.fill();
      }
    }
    frame();
  }

  function stopAudio() {
    if (animFrame) cancelAnimationFrame(animFrame);
    if (audioCtx) { audioCtx.close().catch(() => {}); audioCtx = null; analyser = null; }
    if (mediaStream) { mediaStream.getTracks().forEach(t => t.stop()); mediaStream = null; }
  }

  /* ═════════════════════════════════════
     HELPERS
     ═════════════════════════════════════ */
  function pick(arr) { return arr[Math.floor(Math.random() * arr.length)]; }
  function pickFiller() {
    let idx;
    do { idx = Math.floor(Math.random() * FILLERS_THINKING.length); } while (idx === lastFiller && FILLERS_THINKING.length > 1);
    lastFiller = idx;
    return FILLERS_THINKING[idx];
  }
  function delay(ms) { return new Promise(r => setTimeout(r, ms)); }
  function escapeHtml(s) { const d = document.createElement("div"); d.textContent = s; return d.innerHTML; }
  function toast(msg) {
    const t = document.createElement("div");
    t.className = "toast";
    t.innerHTML = '<i class="fas fa-info-circle"></i>' + escapeHtml(msg);
    document.body.appendChild(t);
    setTimeout(() => t.remove(), 4200);
  }

  /* ═════════════════════════════════════
     ORDERS PAGE
     ═════════════════════════════════════ */
  const ordersBody   = $("#ordersBody");
  const orderSearch  = $("#orderSearch");
  const orderFilter  = $("#orderFilter");
  const refreshOrders= $("#refreshOrders");

  async function loadOrders() {
    ordersBody.innerHTML = '<tr><td colspan="8" class="empty-row"><span class="spinner"></span> Loading…</td></tr>';
    try {
      const r = await fetch(API + "/orders/");
      if (!r.ok) throw new Error();
      allOrders = await r.json();
      renderOrders(allOrders);
    } catch {
      ordersBody.innerHTML = '<tr><td colspan="8" class="empty-row">Failed to load orders</td></tr>';
    }
  }

  function renderOrders(list) {
    if (!list.length) { ordersBody.innerHTML = '<tr><td colspan="8" class="empty-row">No orders found</td></tr>'; return; }
    ordersBody.innerHTML = list.map(o => `<tr>
      <td><strong>${esc(o.order_id)}</strong></td>
      <td>${esc(o.customer_id)}</td>
      <td>${esc(o.origin || "")}</td>
      <td>${esc(o.destination || "")}</td>
      <td>${esc(o.vehicle_id || "—")}</td>
      <td>${o.distance_km != null ? o.distance_km + " km" : "—"}</td>
      <td><span class="st st--${(o.status||"").replace(/ /g,"_")}">${esc(o.status||"")}</span></td>
      <td>${fmtDate(o.created_at)}</td>
    </tr>`).join("");
  }

  function filterOrders() {
    const q = orderSearch.value.toLowerCase();
    const s = orderFilter.value;
    let f = allOrders;
    if (s) f = f.filter(o => (o.status || "").toLowerCase().replace(/ /g, "_") === s);
    if (q) f = f.filter(o => [o.order_id, o.customer_id, o.origin, o.destination].some(v => (v || "").toLowerCase().includes(q)));
    renderOrders(f);
  }

  orderSearch.addEventListener("input", filterOrders);
  orderFilter.addEventListener("change", filterOrders);
  refreshOrders.addEventListener("click", loadOrders);

  /* ═════════════════════════════════════
     DELIVERY TRACKER
     ═════════════════════════════════════ */
  const trackOrderId    = $("#trackOrderId");
  const trackBtn        = $("#trackBtn");
  const predictionResult= $("#predictionResult");
  const predictionEmpty = $("#predictionEmpty");

  trackBtn.addEventListener("click", predictDelivery);
  trackOrderId.addEventListener("keydown", e => { if (e.key === "Enter") predictDelivery(); });

  async function predictDelivery() {
    let oid = trackOrderId.value.trim().toUpperCase();
    if (!oid) return;
    if (/^\d+$/.test(oid)) oid = "ORD-" + oid.padStart(3, "0");
    trackBtn.disabled = true;
    trackBtn.innerHTML = '<span class="spinner"></span> Predicting…';
    try {
      const r = await fetch(API + "/simulation/predict-delivery", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ order_id: oid })
      });
      if (!r.ok) throw new Error("HTTP " + r.status);
      const d = await r.json();
      renderPrediction(d);
    } catch (e) {
      predictionResult.hidden = false;
      predictionEmpty.hidden = true;
      predictionResult.innerHTML = '<div class="empty-state"><i class="fas fa-exclamation-circle"></i><p>Could not get prediction. Check the order ID.</p></div>';
    }
    trackBtn.disabled = false;
    trackBtn.innerHTML = '<i class="fas fa-chart-line"></i> Predict';
  }

  function renderPrediction(d) {
    predictionEmpty.hidden = true;
    predictionResult.hidden = false;
    const statusClass = d.delay_probability > 0.6 ? "delayed" : d.delay_probability > 0.3 ? "at_risk" : "on_time";
    const delay_pct = Math.round((d.delay_probability || 0) * 100);
    predictionResult.innerHTML = `
      <div class="pred-grid">
        <div class="pred-card"><div class="pred-icon">📦</div><div class="pred-val">${esc(d.order_id)}</div><div class="pred-label">Order</div></div>
        <div class="pred-card"><div class="pred-icon">⏱</div><div class="pred-val">${d.estimated_hours != null ? d.estimated_hours.toFixed(1) + "h" : "—"}</div><div class="pred-label">Est. Time</div></div>
        <div class="pred-card"><div class="pred-icon">📏</div><div class="pred-val">${d.distance_km != null ? d.distance_km.toFixed(0) + " km" : "—"}</div><div class="pred-label">Distance</div></div>
        <div class="pred-card status--${statusClass}"><div class="pred-icon">⚠️</div><div class="pred-val">${delay_pct}%</div><div class="pred-label">Delay Risk</div>
          <div class="delay-bar"><div class="delay-fill" style="width:${delay_pct}%;background:${statusClass==="on_time"?"var(--green)":statusClass==="at_risk"?"var(--yellow)":"var(--red)"}"></div></div>
        </div>
        <div class="pred-card"><div class="pred-icon">🚛</div><div class="pred-val">${esc(d.vehicle_id || "—")}</div><div class="pred-label">Vehicle</div></div>
        <div class="pred-card"><div class="pred-icon">🛣</div><div class="pred-val">${esc(d.route || d.origin + " → " + d.destination)}</div><div class="pred-label">Route</div></div>
      </div>`;
  }

  /* ═════════════════════════════════════
     TICKETS PAGE
     ═════════════════════════════════════ */
  const ticketsBody   = $("#ticketsBody");
  const refreshTickets= $("#refreshTickets");

  async function loadTickets() {
    ticketsBody.innerHTML = '<tr><td colspan="7" class="empty-row"><span class="spinner"></span> Loading…</td></tr>';
    try {
      const r = await fetch(API + "/agent/tickets");
      if (!r.ok) throw new Error();
      const list = await r.json();
      renderTickets(Array.isArray(list) ? list : list.tickets || []);
    } catch {
      ticketsBody.innerHTML = '<tr><td colspan="7" class="empty-row">Failed to load tickets</td></tr>';
    }
  }

  function renderTickets(list) {
    if (!list.length) { ticketsBody.innerHTML = '<tr><td colspan="7" class="empty-row">No tickets yet</td></tr>'; return; }
    ticketsBody.innerHTML = list.map(t => `<tr>
      <td><strong>${esc(t.ticket_id || t.id)}</strong></td>
      <td>${esc(t.customer_id || "—")}</td>
      <td><span class="pri pri--${(t.priority||"medium").toLowerCase()}">${esc(t.priority||"medium")}</span></td>
      <td><span class="st st--${(t.status||"open").toLowerCase()}">${esc(t.status||"open")}</span></td>
      <td>${esc(t.issue_summary || t.description || "—")}</td>
      <td>${esc(t.order_id || "—")}</td>
      <td>${fmtDate(t.created_at)}</td>
    </tr>`).join("");
  }

  refreshTickets.addEventListener("click", loadTickets);

  /* ═════════════════════════════════════
     UTILITY
     ═════════════════════════════════════ */
  function esc(s) { if (s == null) return ""; const d = document.createElement("div"); d.textContent = String(s); return d.innerHTML; }
  function fmtDate(d) {
    if (!d) return "—";
    try { return new Date(d).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }); } catch { return d; }
  }

  /* ─── Init ─── */
  // Preload orders page data
  loadOrders();

})();
