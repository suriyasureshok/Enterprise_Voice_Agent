# VoiceOps AI Gateway — Frontend Documentation

## Complete Frontend Architecture & Design Specification

---

## 1. System Overview

**Product Name:** VoiceOps AI Gateway  
**Subtitle:** Enterprise Voice Intelligence Platform  
**Version:** 2.4.1 — Quantum Core  

The dashboard is an enterprise-grade AI operations console that visualizes how an AI voice assistant processes customer requests in real time. It is designed for hackathon demonstration where judges can clearly observe the full AI workflow executing step by step.

---

## 2. Technology Stack

| Layer | Technology |
|-------|-----------|
| Markup | HTML5 semantic elements |
| Styling | CSS3 with Custom Properties, Glassmorphism, CSS Grid / Flexbox |
| Scripting | Vanilla ES2020+ JavaScript (IIFE module) |
| Fonts | Inter (sans-serif) + JetBrains Mono (monospace) via Google Fonts |
| Icons | Font Awesome 6.5 (CDN) |
| Audio | Web Audio API, MediaRecorder API, Web Speech API |
| Avatar | DiceBear API (SVG initials) |

No build tools, no frameworks — zero dependencies to install. Open `dashboard.html` in any modern browser.

---

## 3. File Structure

```
frontend/
  agent_dashboard/
    dashboard.html    ← Full page markup (single page)
    dashboard.css     ← Complete stylesheet (~650 lines)
    dashboard.js      ← Controller, simulation engine, animations (~480 lines)
```

---

## 4. Layout Architecture

The interface follows a four-region layout:

```
┌─────────────────────────────────────────────────┐
│                TOP NAVIGATION BAR               │  60px fixed
├────────┬────────────────────────────────────────┤
│        │                                        │
│  LEFT  │       MAIN DASHBOARD WORKSPACE         │
│  NAV   │                                        │
│ PANEL  │  ┌───────┐ ┌──────────┐ ┌───────┐    │
│        │  │ Voice  │ │ Pipeline │ │ Data  │    │
│ 230px  │  │Console │ │ Monitor  │ │Viewer │    │
│ fixed  │  └───────┘ └──────────┘ └───────┘    │
│        │                                        │
│        │  ┌─── Router Decision Map ───────┐    │
│        │  └───────────────────────────────┘    │
│        │  ┌─── Conversation Logs ─────────┐    │
│        │  └───────────────────────────────┘    │
├────────┴────────────────────────────────────────┤
│              FOOTER STATUS BAR                  │  38px fixed
└─────────────────────────────────────────────────┘
```

---

## 5. CSS Design System

### 5.1 Color Palette (Custom Properties)

| Token | Value | Usage |
|-------|-------|-------|
| `--bg-deep` | `#06081a` | Page background |
| `--bg-surface` | `#0c1029` | Surface elements |
| `--bg-card` | `rgba(15, 23, 60, 0.65)` | Glass card backgrounds |
| `--bg-card-inner` | `rgba(20, 30, 80, 0.35)` | Inner nested cards |
| `--glass-border` | `rgba(99, 102, 241, 0.18)` | Glassmorphism borders |
| `--accent` | `#6366f1` | Primary accent (Indigo) |
| `--accent-light` | `#818cf8` | Light accent |
| `--green` | `#22c55e` | Success / completed states |
| `--amber` | `#f59e0b` | Processing / warning states |
| `--red` | `#ef4444` | Recording / error states |
| `--cyan` | `#06b6d4` | AI response accent |
| `--purple` | `#a855f7` | Secondary accent |

### 5.2 Typography

- **Primary:** Inter (weights: 300–800)
- **Monospace:** JetBrains Mono (for session IDs, data values, code)
- **Base size:** 14px (`html`)

### 5.3 Glassmorphism System

Two utility classes provide the glassmorphism effect:

- `.glass-card` — Primary cards with `backdrop-filter: blur(18px)`, subtle border, deep shadow
- `.glass-card-inner` — Nested cards with lighter blur and thinner borders

### 5.4 Spacing & Sizing

| Token | Value |
|-------|-------|
| `--topnav-h` | 60px |
| `--sidebar-w` | 230px |
| `--footer-h` | 38px |
| `--radius` | 14px |
| `--radius-sm` | 8px |

---

## 6. Component Breakdown

### 6.1 Top Navigation Bar (`.topnav`)

**Position:** Fixed, top, full-width, z-index 1000  
**Background:** Semi-transparent with blur backdrop

**Left Section:**
- Logo icon: Gradient square (indigo → cyan) with broadcast tower icon
- Title: "VoiceOps AI Gateway"
- Subtitle: "Enterprise Voice Intelligence Platform"

**Center Section:**
- Green pulsing status dot (CSS `@keyframes pulse-dot`)
- Label: "AI Gateway Active"
- Session counter: Dynamic, updates on each pipeline run

**Right Section:**
- Search field with focus-glow animation
- Notification bell with animated red badge (`@keyframes notif-pop`)
- Uptime chip showing 99.97%
- Avatar from DiceBear API

### 6.2 Left Navigation Panel (`.sidebar`)

**Position:** Fixed, left, below nav, above footer  
**Width:** 230px (collapses to 60px on tablet)

**Menu Items (8):**

| Icon | Label | data-page |
|------|-------|-----------|
| `fa-th-large` | Dashboard | dashboard |
| `fa-microphone-alt` | Voice Interaction | voice |
| `fa-project-diagram` | Pipeline Monitor | pipeline |
| `fa-route` | Router Decision Map | router |
| `fa-database` | Enterprise Data | data |
| `fa-scroll` | Conversation Logs | logs |
| `fa-chart-line` | Analytics | analytics |
| `fa-cog` | Settings | settings |

**Interactions:**
- Hover: Soft glow background (`rgba(99,102,241,0.1)`) + box shadow
- Active: Gradient background + left accent bar (3px indigo with glow)

**Footer:** Version label "v2.4.1 · Quantum Core"

### 6.3 Stats Row (`.stats-row`)

Four stat cards in a 4-column CSS Grid:

| # | Icon | Value | Label | Trend |
|---|------|-------|-------|-------|
| 1 | `fa-headset` (blue) | 1,247 | Total Requests | ↑ 12% |
| 2 | `fa-bolt` (green) | 1.8 s | Avg Response Time | ↓ 6% |
| 3 | `fa-bullseye` (purple) | Order Tracking | Top Intent | 38% |
| 4 | `fa-check-double` (amber) | 96.2% | System Accuracy | ↑ 1.4% |

**Animations:**
- Staggered `fadeSlideUp` on page load (80ms intervals)
- Hover: `translateY(-2px)` + deepened shadow
- Value counter: Animated number increment on pipeline completion

### 6.4 Panel 1 — Voice Interaction Console (`.voice-panel`)

**Header:** "Voice Interaction Console" with "Live" badge

**Microphone Button (`.mic-btn`):**
- 80 × 80px circular button
- Gradient background: indigo → deep indigo
- Glow shadow: `0 0 30px var(--accent-glow)`
- **Recording state:** Turns red, two expanding ring animations (`@keyframes mic-ring`), pulse animation
- **Idle state:** Indigo with hover scale effect

**Waveform Canvas:**
- HTML5 `<canvas>` element (540 × 80)
- During recording: Real-time audio visualization using Web Audio API `AnalyserNode`
- After recording: Static sine-wave visualization
- Gradient stroke: indigo → cyan → green

**Voice Controls (3 buttons):**
1. **Record Voice** — Toggles recording on/off
2. **Play Recorded** — Plays back the captured audio blob
3. **Play AI Response** — Uses Web Speech API `SpeechSynthesisUtterance` to speak the AI reply

**Audio Details Card:**
- Duration (seconds)
- Timestamp (locale time string)
- Session ID (format: `VX-XXXXX`, incrementing)

### 6.5 Panel 2 — AI Pipeline Monitor (`.pipeline-panel`)

**Header:** "AI Pipeline Monitor" with dynamic status badge (Idle → Processing → Complete)

**Pipeline Visualization:**
Horizontal flow of 7 nodes connected by arrow connectors.

**7 Pipeline Stages:**

| # | Icon | Label | Detail on Completion |
|---|------|-------|---------------------|
| 1 | `fa-microphone` | Voice Input | "Audio captured" |
| 2 | `fa-language` | Speech Recognition | `"Where is my order 123?"` |
| 3 | `fa-brain` | Intent Detection | "Order Tracking · 94%" |
| 4 | `fa-route` | Task Router | "Route → Enterprise API" |
| 5 | `fa-database` | Data Retrieval | "Logistics · Order #123" |
| 6 | `fa-cogs` | Response Generation | "Response ready" |
| 7 | `fa-volume-up` | Voice Output | "Audio generated" |

**Node States & Animations:**

| State | CSS Class | Visual |
|-------|-----------|--------|
| Pending | (default) | Grey, low opacity |
| Processing | `.pipeline-node--processing` | Amber glow, pulsing box-shadow, amber icon |
| Completed | `.pipeline-node--completed` | Green border/icon, green checkmark badge pops in (`@keyframes check-pop`) |

**Connector Animation:**
- `.pipeline-connector--lit` turns green with glowing shadow
- Arrow tip changes color to green

**Timing:** Sequential with realistic delays (400–900ms per stage), creating the effect of watching an AI brain think step by step.

### 6.6 Panel 3 — Enterprise Data Viewer (`.data-panel`)

Three stacked data cards:

**Card 1 — Detected Intent:**
- Intent Type: "Order Tracking"
- Confidence Score: Animated bar (0% → 94%) + percentage text

**Card 2 — API Response Data:**
- Order ID: #123
- Warehouse: Chennai
- Status: "In Transit" (amber badge)
- ETA: "Tomorrow 5 PM"

**Card 3 — Conversation Summary:**
- Three checklist items with green dot icons
- Staggered fade-in animation

### 6.7 Router Decision Map (`.router-section`)

**Source Node:** "Task Router" with gradient icon (indigo → purple)

**Three Destination Paths:**

| Route | Icon | Label |
|-------|------|-------|
| Knowledge Base | `fa-book` | Knowledge Base |
| Enterprise API | `fa-server` | Enterprise API |
| Human Escalation | `fa-user-tie` | Human Escalation |

**Visual Behavior:**
- Selected path: Full opacity, green glowing connection line (`@keyframes line-glow`), green-tinted node
- Unselected paths: 40% opacity, grey
- On pipeline completion, the API route highlights with animation

### 6.8 Conversation Logs (`.logs-section`)

**Collapsible panel** with click-to-toggle header.

**Log Message Types:**

| Type | Avatar | Background |
|------|--------|------------|
| User | `fa-user` in indigo | Indigo-tinted glass |
| AI | `fa-robot` in cyan | Cyan-tinted glass |

**Metadata per message:**
- Timestamp (locale time)
- Intent classification tag
- Processing time

**Expand/Collapse:** Smooth `max-height` transition, chevron icon rotates 180°.

### 6.9 Footer Status Bar (`.footer-bar`)

**Position:** Fixed, bottom, full-width, z-index 1000

**Four status indicators:**

| Icon/Indicator | Label | Dynamic Value |
|---------------|-------|---------------|
| Green pulsing dot | AI Gateway | Active |
| `fa-gauge-high` | Avg Latency | 1.2–2.4 s (randomized) |
| `fa-users` | Active Sessions | 3–5 (randomized) |
| `fa-clock` | Updated | "Just now" → "5s ago" |

---

## 7. Animation Catalog

| Animation | Keyframes | Duration | Usage |
|-----------|-----------|----------|-------|
| `pulse-dot` | Scale 1 → 1.6, opacity toggle | 2s infinite | Status dots |
| `notif-pop` | Scale 0 → 1.3 → 1 | 0.4s | Notification badge |
| `mic-ring` | Scale 1 → 1.8, fade out | 1.5s infinite | Mic recording rings |
| `mic-pulse` | Scale 1 → 1.06 | 1s infinite | Mic button during recording |
| `node-processing` | Box-shadow amber pulse | 1.2s infinite | Pipeline processing node |
| `check-pop` | Scale 0 → 1 (elastic) | 0.35s | Green checkmark appear |
| `badge-glow` | Box-shadow green pulse | 2s infinite | Pipeline complete badge |
| `line-glow` | Box-shadow green pulse | 2s infinite | Router selected path |
| `fadeSlideUp` | Y +8px → 0, opacity 0 → 1 | 0.4s | Card/panel entrance |
| `fadeIn` | Opacity 0 → 1 | 0.4s | General fade |
| `slideInLeft` | X -20px → 0 | 0.5s | Voice panel entrance |
| `slideInRight` | X +20px → 0 | 0.5s | Data panel entrance |

**Staggered Entrance Animation:**
- Stat cards: 80ms delay between each
- Panels: 100–350ms staggered delays

---

## 8. JavaScript Architecture

### 8.1 Module Structure

Single IIFE `(() => { ... })()` with strict mode. No globals polluted.

### 8.2 State Management

```js
const state = {
  isRecording: false,
  pipelineRunning: false,
  audioCtx: null,        // Web Audio context
  analyser: null,        // Analyser node for waveform
  micStream: null,       // MediaStream
  recordedChunks: [],    // Audio chunks
  mediaRecorder: null,   // MediaRecorder instance
  recordedBlob: null,    // Final recorded audio
  waveAnimFrame: null,   // Animation frame ID
  sessionCounter: 10234, // Incrementing session ID
  totalRequests: 1247,   // Request counter
  activeSessions: 3,     // Current session count
};
```

### 8.3 Key Functions

| Function | Purpose |
|----------|---------|
| `toggleRecording()` | Start/stop mic recording or simulation |
| `startRecording()` | Initializes Web Audio, MediaRecorder, waveform |
| `stopRecording()` | Stops streams, shows details, triggers pipeline |
| `simulateRecording()` | Fallback when mic is unavailable |
| `runPipeline(duration)` | Animates all 7 pipeline stages sequentially |
| `resetPipeline()` | Clears all node states to pending |
| `updateIntentCard()` | Fills intent data in Panel 3 |
| `updateApiCard()` | Fills API response data in Panel 3 |
| `updateSummaryCard()` | Builds summary checklist |
| `highlightRoute(route)` | Activates router path visualization |
| `addLogEntry(type, text, intent, time)` | Appends message to conversation logs |
| `updateStats(duration)` | Refreshes analytics counters |
| `updateFooter()` | Updates footer status indicators |
| `animateValue(el, start, end, dur)` | Smooth number counter animation |
| `drawWaveform(analyser, canvas)` | Real-time audio waveform on canvas |
| `drawStaticWave(canvas)` | Static sine-wave after recording |
| `runAutoDemo()` | Automatic demo sequence on page load |
| `showNotification(msg)` | Increments notification badge |

### 8.4 Auto-Demo Mode

The dashboard automatically runs a full demonstration **2 seconds after page load**:

1. Mic button activates with recording animation
2. Waveform generates animated sine visualization for 3.5 seconds
3. Recording stops, audio details appear
4. Pipeline runs all 7 stages with realistic delays
5. Data cards populate with order tracking information
6. Router highlights Enterprise API path
7. Conversation logs receive user + AI messages
8. Stats and footer update

This ensures judges see the full AI workflow immediately without any interaction.

### 8.5 Audio Capabilities

**Recording:**
- Uses `navigator.mediaDevices.getUserMedia({ audio: true })`
- Falls back to simulation if mic is blocked
- Records as WebM blobs via `MediaRecorder`
- Real-time visualization through `AnalyserNode.getByteTimeDomainData()`

**Playback:**
- Recorded audio: `Audio()` element with blob URL
- AI response: `SpeechSynthesisUtterance` (browser TTS)

---

## 9. Responsive Breakpoints

| Breakpoint | Changes |
|-----------|---------|
| ≤ 1280px | Panels grid → 2 columns, data panel spans full width |
| ≤ 960px | Sidebar collapses to 60px (icons only), stats → 2 columns, panels → 1 column, center nav hidden |
| ≤ 640px | Sidebar hidden, full-width layout, search/uptime hidden, footer wraps |

---

## 10. Design Principles

### Glassmorphism
- Semi-transparent backgrounds (`rgba` with low alpha)
- `backdrop-filter: blur()` on all surfaces
- Subtle luminous borders
- Multi-layer depth (card within card)

### Micro-Interactions
- Every state change is animated (never instant)
- Pipeline nodes transition through 3 visible states
- Connectors light up sequentially like flowing data
- Checkmarks pop in with elastic easing

### Color Semantics
- **Indigo (#6366f1):** Primary, brand, interactive
- **Green (#22c55e):** Success, completed, active
- **Amber (#f59e0b):** Processing, in-progress
- **Red (#ef4444):** Recording, errors
- **Cyan (#06b6d4):** AI responses, secondary accent

### Typography Hierarchy
- Card titles: 0.92rem, weight 600
- Values: 1.3rem, weight 700
- Labels: 0.72rem, weight 400, low opacity
- Monospace: Session IDs, data values, pipeline details

---

## 11. User Experience Flow

The dashboard tells a clear story in this order:

```
1. Voice Input Received
   └→ Mic pulses, waveform animates, audio details appear

2. AI Processing Begins
   └→ Pipeline nodes light up one by one (amber → green)

3. Intent Detected
   └→ Intent card fills, confidence bar animates

4. System Routes Task
   └→ Router map highlights Enterprise API path

5. Enterprise Data Retrieved
   └→ API response card populates with order information

6. AI Response Generated
   └→ Summary checklist completes

7. Voice Reply Delivered
   └→ Final pipeline node completes, Play AI Response enables
```

Everything feels like watching an AI brain process information live.

---

## 12. Browser Compatibility

| Browser | Support |
|---------|---------|
| Chrome 90+ | Full |
| Firefox 89+ | Full |
| Safari 15+ | Full (webkit prefix for backdrop-filter) |
| Edge 90+ | Full |

---

## 13. Performance Considerations

- No framework overhead — pure DOM manipulation
- Canvas-based waveform rendering (hardware accelerated)
- CSS animations use `transform` and `opacity` (GPU composited)
- Single IIFE prevents global scope pollution
- Efficient DOM queries cached in `dom` object at initialization
- `requestAnimationFrame` for all visual loops with proper cleanup

---

## 14. Design Inspiration

- Amazon CloudWatch dashboards
- Stripe developer console
- OpenAI playground interface
- n8n / LangGraph workflow visualizations
- Linear app design language
- Vercel deployment dashboards

The system feels like a real enterprise product used by AI operations teams — professional, clean, futuristic, and highly informative at a glance.
