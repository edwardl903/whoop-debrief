"""Generate output/run_replay.html — an animated multi-run replay viewer.

The HTML file fetches runs.json from jsDelivr at runtime, so the replay always
reflects the latest pipeline run without requiring manual regeneration.

Features:
  - Filter runs by Year / Month / Week / Day
  - Simultaneous animation of all runs in the selected period
  - Progressive path reveal: completed route lights up as each dot moves
  - Duration-proportional speed: longer runs take longer to finish
  - Pause / resume / scrub via progress bar
  - Click any route or dot to see WHOOP + Strava stats for that run
  - CartoDB Dark Matter tiles (no API key needed)
  - Highlights: Longest / Fastest / Latest

Usage:
    python3 scripts/generate_run_replay.py
    make run-replay
"""
from __future__ import annotations

import logging
import pathlib

from utils.logging_setup import configure_logging

logger = logging.getLogger(__name__)

_RUNS_JSON = pathlib.Path("data/runs.json")
_OUT = pathlib.Path("output/run_replay.html")


# ---------------------------------------------------------------------------
# HTML template  (data is fetched from jsDelivr at runtime)
# ---------------------------------------------------------------------------

_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Run Replay — WHOOP + Strava</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0d1117;--panel:#161b22;--panel2:#1f2937;
  --border:#30363d;--text:#e6edf3;--muted:#8b949e;
  --accent:#f78166;--green:#3fb950;--yellow:#d29922;--red:#f85149;--blue:#58a6ff;
}
html,body{height:100%;overflow:hidden;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif;background:var(--bg);color:var(--text);font-size:13px}
#layout{display:flex;flex-direction:column;height:100vh}
header{background:var(--panel);border-bottom:1px solid var(--border);height:46px;padding:0 18px;display:flex;align-items:center;gap:10px;flex-shrink:0}
header h1{font-size:14px;font-weight:600;letter-spacing:-.01em}
header .sub{color:var(--muted);font-size:12px}
header .pip{color:var(--border);margin:0 2px}
#body{display:flex;flex:1;overflow:hidden}

/* LEFT — period selector */
#left{width:200px;background:var(--panel);border-right:1px solid var(--border);display:flex;flex-direction:column;flex-shrink:0}
#gran-tabs{display:flex;border-bottom:1px solid var(--border);flex-shrink:0}
.gtab{flex:1;border:none;background:none;color:var(--muted);padding:10px 0;cursor:pointer;font-size:12px;font-weight:500;border-bottom:2px solid transparent;transition:color .15s}
.gtab:hover{color:var(--text)}
.gtab.active{color:var(--accent);border-bottom-color:var(--accent)}
#highlights{display:flex;flex-direction:column;gap:2px;padding:8px 10px;border-bottom:1px solid var(--border);flex-shrink:0}
.hbtn{border:none;background:var(--panel2);color:var(--muted);padding:5px 8px;border-radius:5px;cursor:pointer;font-size:11px;font-weight:500;text-align:left;transition:background .12s,color .12s}
.hbtn:hover{background:rgba(88,166,255,.15);color:var(--accent)}
.hbtn.active{background:rgba(88,166,255,.2);color:var(--accent)}
#period-list{flex:1;overflow-y:auto;padding:4px 0}
.pitem{display:flex;align-items:center;justify-content:space-between;padding:9px 14px;cursor:pointer;transition:background .1s;gap:6px}
.pitem:hover{background:var(--panel2)}
.pitem.active{background:#0d2818;color:var(--green)}
.plabel{flex:1;font-size:13px}
.pbadge{background:var(--bg);color:var(--muted);border-radius:10px;padding:1px 7px;font-size:11px;flex-shrink:0}
.pitem.active .pbadge{background:#1a3a2a}

/* CENTER — map + controls */
#center{flex:1;display:flex;flex-direction:column;overflow:hidden;position:relative}
#map{flex:1}
/* Now-playing sidebar card */
#now-playing{
  overflow:hidden;max-height:0;
  transition:max-height .3s ease,padding .3s ease,border-bottom-width .3s ease;
  padding:0 16px;border-bottom:0px solid var(--border);
  background:linear-gradient(160deg,rgba(68,136,204,.08) 0%,transparent 60%);
}
#now-playing.visible{
  max-height:160px;padding:14px 16px 12px;border-bottom-width:1px;
}
#np-header{display:flex;align-items:center;gap:6px;margin-bottom:6px}
#np-pip{width:7px;height:7px;border-radius:50%;background:var(--accent);display:inline-block;animation:npPulse 1.4s ease-in-out infinite}
@keyframes npPulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.45;transform:scale(.75)}}
#np-label{font-size:9px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--muted)}
#np-name{font-size:14px;font-weight:700;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-bottom:2px}
#np-date{font-size:11px;color:var(--muted);margin-bottom:8px}
#np-vitals{display:flex;align-items:flex-end;justify-content:space-between;margin-bottom:5px}
#np-speed-col{display:flex;flex-direction:column;gap:1px}
#np-speed{font-size:11px;color:var(--muted)}
#np-pace-mi{font-size:22px;font-weight:800;line-height:1}
#np-secondary{display:flex;flex-direction:column;align-items:flex-end;gap:1px}
#np-dist,#np-time{font-size:11px;color:var(--muted)}
#np-bio{font-size:11px;color:var(--muted);margin-bottom:8px;min-height:14px}
#np-bar-wrap{height:3px;background:var(--border);border-radius:2px;overflow:hidden;margin-bottom:4px}
#np-bar-fill{height:100%;background:var(--accent);border-radius:2px;transition:width .1s linear}
#np-timer{font-size:9px;color:var(--muted);display:flex;justify-content:flex-end}
/* Speed buttons */
#speed-btns{display:flex;align-items:center;gap:2px;flex-shrink:0}
.speed-label{font-size:10px;color:var(--muted);margin-right:4px;white-space:nowrap}
.xbtn{border:none;background:none;color:var(--muted);padding:3px 6px;border-radius:4px;cursor:pointer;font-size:11px;font-weight:600;transition:background .12s,color .12s}
.xbtn:hover{background:var(--panel2);color:var(--text)}
.xbtn.active{background:var(--panel2);color:var(--accent)}
#legend{position:absolute;bottom:62px;right:12px;background:rgba(22,27,34,.92);border:1px solid var(--border);border-radius:8px;padding:10px 14px;z-index:500;pointer-events:none}
.lrow{display:flex;align-items:center;gap:8px;margin-bottom:5px;font-size:11px;color:var(--muted)}
.lrow:last-child{margin-bottom:0}
.ldot{width:10px;height:10px;border-radius:50%;flex-shrink:0}
#controls{height:50px;background:var(--panel);border-top:1px solid var(--border);display:flex;align-items:center;padding:0 14px;gap:10px;flex-shrink:0}
.cbtn{border:1px solid var(--border);background:transparent;color:var(--text);padding:6px 14px;border-radius:6px;cursor:pointer;font-size:12px;font-weight:500;white-space:nowrap;transition:background .15s}
.cbtn:hover:not(:disabled){background:#21262d}
.cbtn:disabled{opacity:.35;cursor:not-allowed}
.cbtn.primary{background:var(--accent);border-color:var(--accent);color:#fff}
.cbtn.primary:hover:not(:disabled){background:#ff9580}
#prog-wrap{flex:1;height:4px;background:var(--border);border-radius:2px;cursor:pointer;position:relative}
#prog-fill{position:absolute;left:0;top:0;bottom:0;background:var(--accent);border-radius:2px;width:0%;pointer-events:none}
#badge{color:var(--muted);font-size:11px;white-space:nowrap;min-width:90px;text-align:right}

/* RIGHT — run list / detail */
#right{width:252px;background:var(--panel);border-left:1px solid var(--border);display:flex;flex-direction:column;overflow:hidden;flex-shrink:0}
.ptitle{font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);padding:12px 14px 8px}
#run-list-panel{flex:1;display:flex;flex-direction:column;overflow:hidden}
#run-list{flex:1;overflow-y:auto}
.rrow{display:flex;align-items:center;gap:9px;padding:9px 14px;cursor:pointer;transition:background .1s;border-bottom:1px solid var(--border)}
.rrow:hover{background:var(--panel2)}
.rrow.active{background:#1a1f2e}
.rdot{width:10px;height:10px;border-radius:50%;flex-shrink:0;margin-top:3px}
.rinfo{flex:1;min-width:0}
.rname{font-size:12px;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.rmeta{font-size:11px;color:var(--muted);margin-top:2px}
.rrec{font-size:13px;font-weight:600;flex-shrink:0}
.empty{padding:20px 14px;color:var(--muted);font-size:12px;line-height:1.6}
/* Sim-mode expanded run cards */
.rrow.sim-card{align-items:flex-start;padding:11px 14px}
.sim-speed-row{display:flex;align-items:baseline;gap:7px;margin-top:4px}
.sim-pace-mi{font-size:15px;font-weight:800}
.sim-mph{font-size:11px;color:var(--muted)}
.sim-meta-row{font-size:11px;color:var(--muted);margin-top:3px}
.sim-bio-row{display:flex;gap:10px;margin-top:3px;font-size:11px}
.sim-stat{color:var(--muted)}
.sim-stat.green{color:var(--green)}.sim-stat.yellow{color:var(--yellow)}.sim-stat.red{color:var(--red)}
.sim-prog-wrap{height:2px;background:var(--border);border-radius:1px;overflow:hidden;margin-top:6px}
.sim-prog-fill{height:100%;border-radius:1px;transition:width .06s linear}

/* Detail panel */
#detail-panel{flex:1;overflow-y:auto;display:none;flex-direction:column}
.dback{display:block;width:calc(100% - 28px);margin:10px 14px 0;background:none;border:1px solid var(--border);color:var(--muted);border-radius:6px;padding:7px;font-size:12px;cursor:pointer;text-align:center;transition:background .15s,color .15s}
.dback:hover{background:#21262d;color:var(--text)}
.dtitle{padding:12px 14px;border-bottom:1px solid var(--border)}
.dtitle h3{font-size:14px;font-weight:600;line-height:1.3}
.dtitle .ddate{font-size:11px;color:var(--muted);margin-top:3px}
.dsec{padding:10px 14px;border-bottom:1px solid var(--border)}
.dsec-title{font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin-bottom:8px}
.srow{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:6px}
.srow:last-child{margin-bottom:0}
.sname{color:var(--muted);font-size:11px}
.sval{font-size:12px;font-weight:600}
.green{color:var(--green)}.yellow{color:var(--yellow)}.red{color:var(--red)}.muted{color:var(--muted)}

/* Sort bar */
.list-header{display:flex;align-items:center;justify-content:space-between;padding:9px 14px;border-bottom:1px solid var(--border);flex-shrink:0}
.ptitle-inline{font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}
#sort-bar{display:flex;gap:2px;align-items:center}
.sbtn{border:none;background:none;color:var(--muted);padding:3px 8px;border-radius:4px;cursor:pointer;font-size:11px;font-weight:500;transition:background .12s,color .12s}
.sbtn:hover{background:var(--panel2);color:var(--text)}
.sbtn.active{background:var(--panel2);color:var(--accent)}
#dir-btn{border:none;background:none;color:var(--muted);padding:3px 6px;border-radius:4px;cursor:pointer;font-size:12px;transition:color .12s;margin-left:1px}
#dir-btn:hover{color:var(--text)}
/* Mode toggle */
#mode-toggle{display:flex;border:1px solid var(--border);border-radius:6px;overflow:hidden;flex-shrink:0}
.mbtn{border:none;background:none;color:var(--muted);padding:5px 9px;font-size:11px;font-weight:500;cursor:pointer;transition:background .12s,color .12s;white-space:nowrap}
.mbtn:hover:not(.active){background:var(--panel2);color:var(--text)}
.mbtn.active{background:var(--panel2);color:var(--accent)}

/* Leaflet tooltip override */
.run-tip.leaflet-tooltip{background:rgba(22,27,34,.96)!important;border:1px solid var(--border)!important;color:var(--text)!important;border-radius:6px!important;font-size:11px!important;padding:5px 9px!important;box-shadow:0 4px 14px rgba(0,0,0,.5)!important;white-space:nowrap}
.run-tip.leaflet-tooltip-top::before{border-top-color:var(--border)!important}

/* Keyboard hint */
#kbd-hint{position:absolute;top:10px;left:50%;transform:translateX(-50%);background:rgba(22,27,34,.85);border:1px solid var(--border);border-radius:6px;padding:5px 12px;font-size:11px;color:var(--muted);z-index:500;pointer-events:none;opacity:0;transition:opacity .4s}
#kbd-hint.show{opacity:1}

::-webkit-scrollbar{width:4px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:var(--border);border-radius:2px}
</style>
</head>
<body>
<div id="layout">
  <header>
    <h1>Run Replay</h1>
    <span class="pip">·</span>
    <span class="sub">WHOOP + Strava</span>
  </header>
  <div id="body">
    <!-- LEFT -->
    <div id="left">
      <div id="gran-tabs">
        <button class="gtab" data-gran="year">Year</button>
        <button class="gtab active" data-gran="month">Month</button>
        <button class="gtab" data-gran="week">Week</button>
        <button class="gtab" data-gran="day">Day</button>
      </div>
      <div id="highlights">
        <button class="hbtn" data-hl="longest">&#9632; Longest</button>
        <button class="hbtn" data-hl="fastest">&#9650; Fastest</button>
        <button class="hbtn" data-hl="latest">&#9654; Latest</button>
      </div>
      <div id="period-list"></div>
    </div>
    <!-- CENTER -->
    <div id="center">
      <div id="map"></div>
      <div id="kbd-hint">Space play/pause &nbsp;&#8592;&#8594; period</div>
      <div id="legend">
        <div style="font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);margin-bottom:6px">Speed</div>
        <div class="lrow" style="gap:0;margin-bottom:4px">
          <span style="font-size:10px;color:var(--muted);margin-right:7px">Slow</span>
          <div style="width:72px;height:7px;border-radius:3px;background:linear-gradient(to right,#4488cc,#f0b429,#f85149)"></div>
          <span style="font-size:10px;color:var(--muted);margin-left:7px">Fast</span>
        </div>
        <div id="speed-range" style="font-size:10px;color:var(--muted);text-align:center"></div>
      </div>
      <div id="controls">
        <button id="play-btn" class="cbtn primary" disabled>&#9654; Play</button>
        <button id="reset-btn" class="cbtn" disabled>&#8635; Reset</button>
        <div id="mode-toggle">
          <button class="mbtn active" data-mode="sim">All at once</button>
          <button class="mbtn" data-mode="seq">One by one</button>
        </div>
        <div id="speed-btns">
          <span class="speed-label">Speed</span>
          <button class="xbtn" data-mult="0.5">½×</button>
          <button class="xbtn active" data-mult="1">1×</button>
          <button class="xbtn" data-mult="2">2×</button>
          <button class="xbtn" data-mult="4">4×</button>
        </div>
        <div id="prog-wrap"><div id="prog-fill"></div></div>
        <span id="badge">Select a period</span>
      </div>
    </div>
    <!-- RIGHT -->
    <div id="right">
      <!-- Now Playing card (sequential mode only) -->
      <div id="now-playing">
        <div id="np-header">
          <span id="np-pip"></span>
          <span id="np-label">NOW PLAYING</span>
        </div>
        <div id="np-name"></div>
        <div id="np-date"></div>
        <div id="np-vitals">
          <div id="np-speed-col">
            <span id="np-speed"></span>
            <span id="np-pace-mi"></span>
          </div>
          <div id="np-secondary">
            <span id="np-dist"></span>
            <span id="np-time"></span>
          </div>
        </div>
        <div id="np-bio"></div>
        <div id="np-bar-wrap"><div id="np-bar-fill"></div></div>
        <div id="np-timer"></div>
      </div>
      <!-- List view -->
      <div id="run-list-panel">
        <div class="list-header">
          <span class="ptitle-inline">Runs</span>
          <div id="sort-bar">
            <button class="sbtn active" data-sort="time">Time</button>
            <button class="sbtn" data-sort="dist">Dist</button>
            <button class="sbtn" data-sort="speed">Speed</button>
            <button id="dir-btn" title="Toggle sort direction">↑</button>
          </div>
        </div>
        <div id="run-list"><div class="empty">Select a period from the left to see runs and start the animation.</div></div>
      </div>
      <!-- Detail view -->
      <div id="detail-panel">
        <button class="dback" id="back-btn">&#8592; All Runs</button>
        <div id="detail-content"></div>
      </div>
    </div>
  </div>
</div>

<div id="loading" style="position:fixed;inset:0;display:flex;align-items:center;justify-content:center;background:var(--bg);z-index:9999;color:var(--muted);font-size:13px">Loading runs…</div>

<script>
// ── Data ──────────────────────────────────────────────────────────────────
const RUNS_URL = 'https://cdn.jsdelivr.net/gh/edwardl903/whoop-analytics@main/data/runs.json';
let RUNS = [];

// ── State ─────────────────────────────────────────────────────────────────
const S = {
  gran: 'month',
  sort: 'time',
  sortDir: 'asc',   // 'asc' | 'desc'
  mode: 'sim',      // 'sim' (simultaneous) | 'seq' (sequential / one-by-one)
  speedMult: 1,     // playback speed multiplier
  period: null,
  activeRuns: [],
  animating: false,
  animId: null,
  startTime: null,
  progress: 0,
  selectedId: null,
  map: null,
  completedLines: {},
  remainingLines: {},
  markers: {},
};

const ANIM_MS = 25000; // 25 s = full animation regardless of period length

// ── Speed color scale (blue → gold → red = slow → fast) ──────────────────
let _ALL_SPEEDS = [], MIN_SPEED = 5, MAX_SPEED = 10;
const _STOPS = [[68,136,204],[240,180,41],[248,81,73]]; // #4488cc #f0b429 #f85149

function speedColor(mph) {
  if (mph == null) return '#4488cc';
  const t = Math.max(0, Math.min(1, (mph - MIN_SPEED) / Math.max(MAX_SPEED - MIN_SPEED, 0.1)));
  const [c1, c2, u] = t < 0.5 ? [_STOPS[0], _STOPS[1], t * 2] : [_STOPS[1], _STOPS[2], (t - 0.5) * 2];
  const r = Math.round(c1[0] + (c2[0] - c1[0]) * u);
  const g = Math.round(c1[1] + (c2[1] - c1[1]) * u);
  const b = Math.round(c1[2] + (c2[2] - c1[2]) * u);
  return '#' + [r, g, b].map(v => v.toString(16).padStart(2, '0')).join('');
}

// ── Utilities ─────────────────────────────────────────────────────────────
function recClass(r) {
  if (r == null) return 'muted';
  if (r >= 67)   return 'green';
  if (r >= 34)   return 'yellow';
  return 'red';
}
function fmtMph(mph) {
  if (mph == null) return 'n/a';
  return mph.toFixed(1) + ' mph';
}
function fmtPaceMi(mph) {
  if (!mph) return 'n/a';
  const mpm = 60 / mph;
  const mins = Math.floor(mpm);
  const secs = Math.round((mpm - mins) * 60);
  return mins + ':' + String(secs).padStart(2, '0') + '/mi';
}
function fmtPace(p) {
  if (p == null) return 'n/a';
  const m = Math.floor(p), s = Math.round((p - m) * 60);
  return m + ':' + String(s).padStart(2,'0') + ' /km';
}
function fmtDur(mins) {
  if (mins == null) return 'n/a';
  const h = Math.floor(mins / 60), m = Math.round(mins % 60);
  return h > 0 ? h + 'h ' + m + 'm' : m + 'm';
}
function fmtRec(r) { return r == null ? 'n/a' : Math.round(r) + '%'; }
function fmtDelta(d) {
  if (d == null) return 'n/a';
  const v = Math.round(d);
  return (v > 0 ? '+' : '') + v + ' pts';
}
function esc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
function srow(label, val, cls) {
  return '<div class="srow"><span class="sname">' + label +
         '</span><span class="sval ' + (cls||'') + '">' + val + '</span></div>';
}

// ── Period helpers ─────────────────────────────────────────────────────────
function groupKey(run) { return run[S.gran]; }
function groupLabel(run) {
  if (S.gran === 'year')  return run.year_label;
  if (S.gran === 'month') return run.month_label;
  if (S.gran === 'week')  return run.week_label;
  return run.day_label;
}

function periodsWithCounts() {
  const map = {};
  RUNS.forEach(r => {
    const k = r[S.gran];
    if (!k) return;
    if (!map[k]) map[k] = { key: k, label: groupLabel(r), count: 0 };
    map[k].count++;
  });
  return Object.values(map).sort((a, b) => b.key < a.key ? -1 : 1);
}

// ── Period list ────────────────────────────────────────────────────────────
function buildPeriodList() {
  const el = document.getElementById('period-list');
  el.innerHTML = '';
  periodsWithCounts().forEach(({ key, label, count }) => {
    const d = document.createElement('div');
    d.className = 'pitem' + (key === S.period ? ' active' : '');
    d.innerHTML = '<span class="plabel">' + esc(label) + '</span>' +
                  '<span class="pbadge">' + count + '</span>';
    d.addEventListener('click', () => selectPeriod(key));
    el.appendChild(d);
  });
}

// ── Select period ──────────────────────────────────────────────────────────
function sortedActiveRuns() {
  const runs = [...S.activeRuns];
  const d = S.sortDir === 'asc' ? 1 : -1;
  if (S.sort === 'dist')  return runs.sort((a, b) => d * ((a.distance_km || 0) - (b.distance_km || 0)));
  if (S.sort === 'speed') return runs.sort((a, b) => d * ((a.speed_mph || 0) - (b.speed_mph || 0)));
  return runs.sort((a, b) => d * (a.date < b.date ? -1 : 1));
}

function autoPlay() {
  if (!S.activeRuns.some(r => r.coords) || S.animating) return;
  S.progress = 0;
  resetVisuals();
  S.animating = true;
  S.startTime = performance.now();
  document.getElementById('play-btn').innerHTML = '&#9646;&#9646; Pause';
  S.animId = requestAnimationFrame(tick);
}

function selectPeriod(key) {
  S.period = key;
  S.activeRuns = RUNS.filter(r => r[S.gran] === key);
  S.selectedId = null;
  resetAnim();
  clearMap();
  drawRoutes();
  fitBounds();
  buildPeriodList();
  buildRunList();
  updateControls();
  updateBadge();
  // Ensure list panel is visible (in case detail was open)
  document.getElementById('run-list-panel').style.display = 'flex';
  document.getElementById('detail-panel').style.display = 'none';
  // Auto-start after map finishes fitting
  setTimeout(autoPlay, 400);
}

// ── Map setup ──────────────────────────────────────────────────────────────
S.map = L.map('map', { zoomControl: true });
L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
  subdomains: 'abcd',
  maxZoom: 20,
}).addTo(S.map);

// Default center (Boston fallback) — recalculated in initApp() after RUNS loads
S.map.setView([42.37, -71.1], 13);

// ── Map drawing ────────────────────────────────────────────────────────────
function clearMap() {
  Object.values(S.completedLines).forEach(l => l.remove());
  Object.values(S.remainingLines).forEach(l => l.remove());
  Object.values(S.markers).forEach(m => m.remove());
  S.completedLines = {}; S.remainingLines = {}; S.markers = {};
  hideNowPlaying();
}

function drawRoutes() {
  S.activeRuns.forEach(run => {
    if (!run.coords || run.coords.length < 2) return;
    const col = speedColor(run.speed_mph);

    // Remaining line — full route, dim dashed background
    const rem = L.polyline(run.coords, { color: col, weight: 2.5, opacity: 0.22, dashArray: '4 7' }).addTo(S.map);
    rem.on('click', () => selectRun(run.run_id));
    S.remainingLines[run.run_id] = rem;

    // Completed line — starts empty, fills as dot moves
    const done = L.polyline([], { color: col, weight: 4, opacity: 0.9 }).addTo(S.map);
    S.completedLines[run.run_id] = done;

    // Moving dot — starts at route start
    const dot = L.circleMarker(run.coords[0], {
      radius: 8, fillColor: col, color: '#0d1117', weight: 2, opacity: 1, fillOpacity: 1,
    }).addTo(S.map);
    dot.on('click', () => selectRun(run.run_id));
    dot.bindTooltip(
      esc(run.run_name) + '<br>' + fmtPaceMi(run.speed_mph) + ' &nbsp;·&nbsp; ' + fmtMph(run.speed_mph) + '<br>' +
      (run.distance_km || 0).toFixed(1) + ' km',
      { direction: 'top', offset: [0, -10], className: 'run-tip' }
    );
    S.markers[run.run_id] = dot;
    S.markers[run.run_id]._done = false;
  });
}

function fitBounds() {
  const gps = S.activeRuns.filter(r => r.coords && r.coords.length);
  if (!gps.length) return;
  const all = gps.flatMap(r => r.coords);
  const lats = all.map(c => c[0]), lngs = all.map(c => c[1]);
  S.map.fitBounds([[Math.min(...lats), Math.min(...lngs)], [Math.max(...lats), Math.max(...lngs)]], { padding: [40, 40] });
}

// ── Interpolation ──────────────────────────────────────────────────────────
function interpolate(run, p) {
  const coords = run.coords, dists = run.distances;
  if (p <= 0) return coords[0];
  if (p >= 1) return coords[coords.length - 1];
  const total = dists[dists.length - 1];
  const target = p * total;
  let lo = 0, hi = dists.length - 1;
  while (lo < hi - 1) { const mid = (lo + hi) >> 1; dists[mid] <= target ? lo = mid : hi = mid; }
  const seg = dists[hi] - dists[lo];
  const t = seg === 0 ? 0 : (target - dists[lo]) / seg;
  return [coords[lo][0] + t * (coords[hi][0] - coords[lo][0]),
          coords[lo][1] + t * (coords[hi][1] - coords[lo][1])];
}

// ── Per-frame visual update ────────────────────────────────────────────────
function updateRunVisuals(run, runP) {
  if (!run.coords || run.coords.length < 2) return;
  const m = S.markers[run.run_id];
  if (!m) return;

  // Sequential: queued (not yet started)
  if (runP < 0) {
    m.setLatLng(run.coords[0]);
    if (!m._queued) {
      m.setStyle({ fillOpacity: 0.12 });
      m._queued = true; m._done = false;
    }
    if (S.completedLines[run.run_id]) S.completedLines[run.run_id].setLatLngs([]);
    if (S.remainingLines[run.run_id]) {
      S.remainingLines[run.run_id].setLatLngs(run.coords);
      S.remainingLines[run.run_id].setStyle({ opacity: 0.07 });
    }
    return;
  }

  // Restore when transitioning out of queued state
  if (m._queued) {
    m.setStyle({ fillOpacity: 1 });
    if (S.remainingLines[run.run_id]) S.remainingLines[run.run_id].setStyle({ opacity: 0.22 });
    m._queued = false;
  }

  const p = Math.min(runP, 1);
  const pos = interpolate(run, p);

  m.setLatLng(pos);

  // Fade dot when its own route is done but global animation continues
  if (runP >= 1 && !m._done) {
    m.setStyle({ fillOpacity: 0.35, weight: 1 });
    m._done = true;
  }

  // Completed line: route[0..splitIdx] + interpolated pos
  const total = run.distances[run.distances.length - 1];
  const target = p * total;
  let si = 0;
  for (let i = 0; i < run.distances.length - 1; i++) {
    if (run.distances[i + 1] <= target) si = i + 1; else break;
  }
  S.completedLines[run.run_id].setLatLngs([...run.coords.slice(0, si + 1), pos]);

  // Remaining line: interpolated pos to end
  S.remainingLines[run.run_id].setLatLngs([pos, ...run.coords.slice(si + 1)]);
}

// ── Live stats overlay ────────────────────────────────────────────────────
let _npCurrent = null; // track last-shown run_id to detect transitions

const _fmtMin = m => {
  const mins = Math.floor(m);
  const secs = Math.round((m - mins) * 60);
  return mins + ':' + String(secs).padStart(2, '0');
};

function updateNowPlaying(run, runP) {
  const el = document.getElementById('now-playing');
  if (!run) { hideNowPlaying(); return; }

  const isNew = run.run_id !== _npCurrent;
  el.classList.add('visible');
  _npCurrent = run.run_id;

  if (isNew) {
    // Flash pip to signal new run
    const pip = document.getElementById('np-pip');
    pip.style.animation = 'none';
    void pip.offsetWidth;
    pip.style.animation = '';
  }

  const p = Math.min(Math.max(runP, 0), 1);
  const totalMin = run.moving_time_min || 0;
  const elapsedMin = p * totalMin;

  document.getElementById('np-name').textContent = run.run_name;
  document.getElementById('np-date').textContent = run.day_label || run.date;

  const paceEl = document.getElementById('np-pace-mi');
  paceEl.textContent = fmtPaceMi(run.speed_mph);
  paceEl.style.color = speedColor(run.speed_mph);
  document.getElementById('np-speed').textContent = fmtMph(run.speed_mph);

  document.getElementById('np-dist').textContent =
    run.distance_km != null ? run.distance_km.toFixed(1) + ' km' : '';
  document.getElementById('np-time').textContent = fmtDur(totalMin);

  const hr  = run.run_avg_hr != null ? 'HR ' + Math.round(run.run_avg_hr) + ' bpm' : null;
  const rec = run.same_day_recovery != null ? 'Rec ' + Math.round(run.same_day_recovery) + '%' : null;
  document.getElementById('np-bio').textContent = [hr, rec].filter(Boolean).join('  ·  ');

  document.getElementById('np-bar-fill').style.width = (p * 100) + '%';
  document.getElementById('np-timer').textContent = _fmtMin(elapsedMin) + ' / ' + _fmtMin(totalMin);
}

function hideNowPlaying() {
  document.getElementById('now-playing').classList.remove('visible');
  _npCurrent = null;
}

// ── Animation loop ─────────────────────────────────────────────────────────
function tick(ts) {
  const elapsed = ts - S.startTime;
  const gP = Math.min(elapsed * S.speedMult / ANIM_MS, 1);
  S.progress = gP;

  const gpsRuns = S.activeRuns.filter(r => r.coords);

  if (S.mode === 'sim') {
    // Simultaneous: all runs animate together; longer runs take longer
    const maxDur = Math.max(...gpsRuns.map(r => r.moving_time_min || 1), 1);
    gpsRuns.forEach(run => {
      const runP = gP / ((run.moving_time_min || maxDur) / maxDur);
      updateRunVisuals(run, runP);
      const pb = document.getElementById('pb-' + run.run_id);
      if (pb) pb.firstElementChild.style.width = (Math.min(runP, 1) * 100) + '%';
    });
    hideNowPlaying();
  } else {
    // Sequential: runs play one-by-one in chronological order, each slot
    // proportional to its actual duration relative to the period total.
    const ordered = [...gpsRuns].sort((a, b) => a.date < b.date ? -1 : 1);
    const totalDur = ordered.reduce((s, r) => s + (r.moving_time_min || 1), 0);
    let offset = 0;
    let activeRun = null, activeRunP = 0;
    ordered.forEach(run => {
      const dur = run.moving_time_min || 1;
      const slotStart = offset / totalDur;
      const slotEnd = (offset + dur) / totalDur;
      offset += dur;
      const runP = (gP - slotStart) / (slotEnd - slotStart); // negative = queued
      updateRunVisuals(run, runP);
      if (runP >= 0 && runP <= 1) { activeRun = run; activeRunP = runP; }
      // keep last finished run visible until next one starts
      else if (runP > 1 && !activeRun) { activeRun = run; activeRunP = 1; }
    });
    updateNowPlaying(activeRun, activeRunP);
  }

  document.getElementById('prog-fill').style.width = (gP * 100) + '%';

  if (gP < 1) {
    S.animId = requestAnimationFrame(tick);
  } else {
    S.animating = false;
    document.getElementById('play-btn').innerHTML = '&#9654; Play';
  }
}

// ── Reset visuals (dots to start, paths cleared) ───────────────────────────
function resetVisuals() {
  const isSeq = S.mode === 'seq';
  S.activeRuns.forEach(run => {
    if (!run.coords) return;
    const col = speedColor(run.speed_mph);
    const m = S.markers[run.run_id];
    if (m) {
      m.setLatLng(run.coords[0]);
      m.setStyle({ radius: 8, fillOpacity: isSeq ? 0.12 : 1, weight: 2, fillColor: col });
      m._done = false; m._queued = isSeq;
    }
    if (S.completedLines[run.run_id]) S.completedLines[run.run_id].setLatLngs([]);
    if (S.remainingLines[run.run_id]) {
      S.remainingLines[run.run_id].setLatLngs(run.coords);
      S.remainingLines[run.run_id].setStyle({ opacity: isSeq ? 0.07 : 0.22 });
    }
  });
  document.getElementById('prog-fill').style.width = '0%';
  // Reset per-run sim progress bars
  S.activeRuns.forEach(run => {
    const pb = document.getElementById('pb-' + run.run_id);
    if (pb) pb.firstElementChild.style.width = '0%';
  });
}

function resetAnim() {
  cancelAnimationFrame(S.animId);
  S.animating = false; S.startTime = null; S.progress = 0;
  document.getElementById('play-btn').innerHTML = '&#9654; Play';
  resetVisuals();
  hideNowPlaying();
}

// ── Scrub progress bar ─────────────────────────────────────────────────────
document.getElementById('prog-wrap').addEventListener('click', function(e) {
  if (!S.period || !S.activeRuns.some(r => r.coords)) return;
  const rect = this.getBoundingClientRect();
  const newP = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));

  if (S.animating) { cancelAnimationFrame(S.animId); S.animating = false; document.getElementById('play-btn').innerHTML = '&#9654; Play'; }
  S.progress = newP;

  const gpsRuns = S.activeRuns.filter(r => r.coords);
  gpsRuns.forEach(r => { const m = S.markers[r.run_id]; if (m) { m._done = false; m._queued = false; } });
  if (S.mode === 'sim') {
    const maxDur = Math.max(...gpsRuns.map(r => r.moving_time_min || 1), 1);
    gpsRuns.forEach(run => updateRunVisuals(run, newP / ((run.moving_time_min || maxDur) / maxDur)));
  } else {
    const ordered = [...gpsRuns].sort((a, b) => a.date < b.date ? -1 : 1);
    const totalDur = ordered.reduce((s, r) => s + (r.moving_time_min || 1), 0);
    let offset = 0;
    ordered.forEach(run => {
      const dur = run.moving_time_min || 1;
      const slotStart = offset / totalDur, slotEnd = (offset + dur) / totalDur;
      offset += dur;
      updateRunVisuals(run, (newP - slotStart) / (slotEnd - slotStart));
    });
  }
  document.getElementById('prog-fill').style.width = (newP * 100) + '%';
});

// ── Controls ───────────────────────────────────────────────────────────────
document.getElementById('play-btn').addEventListener('click', () => {
  if (!S.period) return;
  if (S.animating) {
    cancelAnimationFrame(S.animId); S.animating = false;
    document.getElementById('play-btn').innerHTML = '&#9654; Play';
  } else {
    if (S.progress >= 1) { resetVisuals(); S.progress = 0; }
    S.animating = true;
    S.startTime = performance.now() - S.progress * ANIM_MS / S.speedMult;
    document.getElementById('play-btn').innerHTML = '&#9646;&#9646; Pause';
    S.animId = requestAnimationFrame(tick);
  }
});

document.getElementById('reset-btn').addEventListener('click', resetAnim);

// ── Granularity tabs ───────────────────────────────────────────────────────
document.querySelectorAll('.gtab').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.gtab').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    S.gran = btn.dataset.gran; S.period = null; S.selectedId = null;
    resetAnim(); clearMap();
    // Auto-select the most recent period and play it
    const periods = periodsWithCounts();
    if (periods.length) {
      selectPeriod(periods[periods.length - 1].key);
    } else {
      buildPeriodList();
      document.getElementById('run-list').innerHTML = '<div class="empty">No runs found.</div>';
      document.getElementById('run-list-panel').style.display = 'flex';
      document.getElementById('detail-panel').style.display = 'none';
      document.getElementById('badge').textContent = 'Select a period';
      document.getElementById('play-btn').disabled = true;
      document.getElementById('reset-btn').disabled = true;
    }
  });
});

// ── Sort buttons + direction ───────────────────────────────────────────────
function updateDirBtn() {
  document.getElementById('dir-btn').textContent = S.sortDir === 'asc' ? '↑' : '↓';
}

document.querySelectorAll('.sbtn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.sbtn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    const prev = S.sort;
    S.sort = btn.dataset.sort;
    // Sensible default directions when switching sort dimension
    if (S.sort !== prev) {
      S.sortDir = S.sort === 'time' ? 'asc' : 'desc';
      updateDirBtn();
    }
    if (S.period) buildRunList();
  });
});

document.getElementById('dir-btn').addEventListener('click', () => {
  S.sortDir = S.sortDir === 'asc' ? 'desc' : 'asc';
  updateDirBtn();
  if (S.period) buildRunList();
});

// ── Playback speed ─────────────────────────────────────────────────────────
document.querySelectorAll('.xbtn').forEach(btn => {
  btn.addEventListener('click', () => {
    const mult = parseFloat(btn.dataset.mult);
    if (S.animating) {
      // Preserve progress: recalculate startTime for new speed
      const now = performance.now();
      S.startTime = now - S.progress * ANIM_MS / mult;
    }
    S.speedMult = mult;
    document.querySelectorAll('.xbtn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
  });
});

// ── Mode toggle (simultaneous / sequential) ────────────────────────────────
document.querySelectorAll('.mbtn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.mbtn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    S.mode = btn.dataset.mode;
    if (S.period && S.activeRuns.some(r => r.coords)) {
      resetAnim();      // stop and reset visuals for new mode
      setTimeout(autoPlay, 100); // re-start with new mode
    }
  });
});

// ── Keyboard shortcuts ─────────────────────────────────────────────────────
(function() {
  const hint = document.getElementById('kbd-hint');
  let hintTimer;

  function showHint() {
    hint.classList.add('show');
    clearTimeout(hintTimer);
    hintTimer = setTimeout(() => hint.classList.remove('show'), 2000);
  }

  document.addEventListener('keydown', e => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

    if (e.key === ' ' || e.code === 'Space') {
      e.preventDefault();
      document.getElementById('play-btn').click();
    }

    if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
      e.preventDefault();
      showHint();
      if (!S.period) return;
      const periods = periodsWithCounts();
      const idx = periods.findIndex(p => p.key === S.period);
      const next = e.key === 'ArrowRight' ? idx + 1 : idx - 1;
      if (next >= 0 && next < periods.length) selectPeriod(periods[next].key);
    }

    if (e.key === 'Escape') clearSelection();
  });
})();

// ── Controls state ─────────────────────────────────────────────────────────
function updateControls() {
  const hasGps = S.activeRuns.some(r => r.coords);
  document.getElementById('play-btn').disabled = !hasGps;
  document.getElementById('reset-btn').disabled = !hasGps;
}

function updateBadge() {
  const total = S.activeRuns.length;
  const gps = S.activeRuns.filter(r => r.coords).length;
  document.getElementById('badge').textContent = total + ' run' + (total !== 1 ? 's' : '') + ' · ' + gps + ' GPS';
}

// ── Run selection ──────────────────────────────────────────────────────────
function selectRun(id) {
  S.selectedId = id;
  const run = RUNS.find(r => r.run_id === id);
  if (!run) return;

  // Visual highlight
  Object.entries(S.completedLines).forEach(([rid, l]) =>
    l.setStyle({ opacity: rid === id ? 1 : 0.55, weight: rid === id ? 6 : 4 }));
  Object.entries(S.remainingLines).forEach(([rid, l]) =>
    l.setStyle({ opacity: rid === id ? 0.45 : 0.1, weight: rid === id ? 4 : 2 }));
  Object.entries(S.markers).forEach(([rid, m]) =>
    m.setStyle({ radius: rid === id ? 11 : 8, weight: rid === id ? 3 : 2 }));

  // Highlight in run list
  document.querySelectorAll('.rrow').forEach(el =>
    el.classList.toggle('active', el.dataset.id === id));

  renderDetail(run);
  document.getElementById('run-list-panel').style.display = 'none';
  document.getElementById('detail-panel').style.display = 'flex';
}

function clearSelection() {
  S.selectedId = null;
  S.activeRuns.forEach(run => {
    if (!run.coords) return;
    const col = speedColor(run.speed_mph);
    if (S.completedLines[run.run_id]) S.completedLines[run.run_id].setStyle({ opacity: 0.9, weight: 4, color: col });
    if (S.remainingLines[run.run_id]) S.remainingLines[run.run_id].setStyle({ opacity: 0.22, weight: 2.5, color: col });
    if (S.markers[run.run_id]) S.markers[run.run_id].setStyle({ radius: 8, weight: 2 });
  });
  document.getElementById('run-list-panel').style.display = 'flex';
  document.getElementById('detail-panel').style.display = 'none';
}

document.getElementById('back-btn').addEventListener('click', clearSelection);

// ── Run list (right sidebar) ───────────────────────────────────────────────
function runListMeta(run) {
  const dist = (run.distance_km || 0).toFixed(1) + ' km';
  const noGps = !run.coords ? ' · no GPS' : '';
  if (S.sort === 'dist')  return fmtMph(run.speed_mph) + ' · ' + run.day_label + noGps;
  if (S.sort === 'speed') return dist + ' · ' + run.day_label + noGps;
  return run.day_label + ' · ' + dist + noGps;
}

function runListRight(run) {
  const spCol = speedColor(run.speed_mph);
  if (S.sort === 'dist')  return { val: (run.distance_km || 0).toFixed(1) + ' km', col: 'var(--text)' };
  if (S.sort === 'speed') return { val: fmtPaceMi(run.speed_mph), col: spCol };
  return { val: fmtPaceMi(run.speed_mph), col: spCol };
}

function buildRunList() {
  const el = document.getElementById('run-list');
  if (!S.activeRuns.length) { el.innerHTML = '<div class="empty">No runs in this period.</div>'; return; }
  el.innerHTML = '';
  const simMode = S.mode === 'sim';
  sortedActiveRuns().forEach(run => {
    const spCol = speedColor(run.speed_mph);
    const d = document.createElement('div');
    d.dataset.id = run.run_id;
    if (run.run_id === S.selectedId) d.classList.add('active');

    if (simMode) {
      // Expanded stat card for "All at once" mode
      d.className = 'rrow sim-card';
      const recCls = run.same_day_recovery == null ? '' :
                     run.same_day_recovery >= 67 ? 'green' :
                     run.same_day_recovery >= 34 ? 'yellow' : 'red';
      const hr  = run.run_avg_hr != null ? 'HR ' + Math.round(run.run_avg_hr) + ' bpm' : null;
      const rec = run.same_day_recovery != null ? 'Rec ' + Math.round(run.same_day_recovery) + '%' : null;
      d.innerHTML =
        '<div class="rdot" style="background:' + spCol + ';margin-top:4px"></div>' +
        '<div class="rinfo">' +
          '<div class="rname">' + esc(run.run_name) + '</div>' +
          '<div class="sim-speed-row">' +
            '<span class="sim-pace-mi" style="color:' + spCol + '">' + fmtPaceMi(run.speed_mph) + '</span>' +
            '<span class="sim-mph">' + fmtMph(run.speed_mph) + '</span>' +
          '</div>' +
          '<div class="sim-meta-row">' +
            run.day_label + ' &nbsp;·&nbsp; ' +
            (run.distance_km != null ? run.distance_km.toFixed(1) + ' km' : '') +
            (run.moving_time_min ? ' &nbsp;·&nbsp; ' + fmtDur(run.moving_time_min) : '') +
          '</div>' +
          (hr || rec ? '<div class="sim-bio-row">' +
            (hr  ? '<span class="sim-stat">' + hr  + '</span>' : '') +
            (rec ? '<span class="sim-stat ' + recCls + '">' + rec + '</span>' : '') +
          '</div>' : '') +
          '<div id="pb-' + run.run_id + '" class="sim-prog-wrap">' +
            '<div class="sim-prog-fill" style="background:' + spCol + ';width:0%"></div>' +
          '</div>' +
        '</div>';
    } else {
      // Compact row for "One by one" / default
      d.className = 'rrow';
      const right = runListRight(run);
      d.innerHTML =
        '<div class="rdot" style="background:' + spCol + '"></div>' +
        '<div class="rinfo">' +
          '<div class="rname">' + esc(run.run_name) + '</div>' +
          '<div class="rmeta">' + esc(runListMeta(run)) + '</div>' +
        '</div>' +
        '<div class="rrec" style="color:' + right.col + '">' + right.val + '</div>';
    }

    d.addEventListener('click', () => {
      if (run.coords) selectRun(run.run_id); else renderDetailOnly(run);
    });
    el.appendChild(d);
  });
}

// ── Detail panel rendering ─────────────────────────────────────────────────
function renderDetail(run) {
  const rc = recClass(run.same_day_recovery);
  document.getElementById('detail-content').innerHTML =
    '<div class="dtitle">' +
      '<h3>' + esc(run.run_name) + '</h3>' +
      '<div class="ddate">' + esc(run.day_label) + '</div>' +
    '</div>' +
    '<div class="dsec"><div class="dsec-title">Run</div>' +
      srow('Distance', run.distance_km != null ? run.distance_km.toFixed(2) + ' km' : 'n/a') +
      srow('Moving Time', fmtDur(run.moving_time_min)) +
      srow('Pace', fmtPaceMi(run.speed_mph)) +
      srow('Speed', fmtMph(run.speed_mph) + '  (' + fmtPace(run.pace_min_per_km) + '/km)') +
      srow('Avg HR', run.run_avg_hr != null ? Math.round(run.run_avg_hr) + ' bpm' : 'n/a') +
      srow('Max HR', run.run_max_hr != null ? Math.round(run.run_max_hr) + ' bpm' : 'n/a') +
    '</div>' +
    '<div class="dsec"><div class="dsec-title">WHOOP — Day Of Run</div>' +
      srow('Recovery', fmtRec(run.same_day_recovery), rc) +
      srow('Sleep (prev night)', run.same_day_sleep_hours != null ? run.same_day_sleep_hours.toFixed(1) + ' h' : 'n/a') +
      srow('Sleep Quality', run.same_day_sleep_quality || 'n/a') +
    '</div>' +
    '<div class="dsec"><div class="dsec-title">WHOOP — Next Morning</div>' +
      srow('Recovery', fmtRec(run.next_day_recovery)) +
      srow('Recovery Delta', fmtDelta(run.recovery_delta), run.recovery_delta != null ? (run.recovery_delta >= 0 ? 'green' : 'red') : '') +
    '</div>';
}

function renderDetailOnly(run) {
  renderDetail(run);
  document.getElementById('run-list-panel').style.display = 'none';
  document.getElementById('detail-panel').style.display = 'flex';
}

// ── Data helpers (polyline decode + run processing) ─────────────────────────
function decodePolyline(encoded) {
  const coords = [];
  let lat = 0, lng = 0, idx = 0;
  while (idx < encoded.length) {
    let b, shift = 0, result = 0;
    do { b = encoded.charCodeAt(idx++) - 63; result |= (b & 0x1f) << shift; shift += 5; } while (b >= 0x20);
    lat += (result & 1) ? ~(result >> 1) : (result >> 1);
    shift = 0; result = 0;
    do { b = encoded.charCodeAt(idx++) - 63; result |= (b & 0x1f) << shift; shift += 5; } while (b >= 0x20);
    lng += (result & 1) ? ~(result >> 1) : (result >> 1);
    coords.push([lat / 1e5, lng / 1e5]);
  }
  return coords;
}

function haversineM(lat1, lon1, lat2, lon2) {
  const R = 6371000;
  const phi1 = lat1 * Math.PI/180, phi2 = lat2 * Math.PI/180;
  const dphi = (lat2 - lat1) * Math.PI/180;
  const dlam = (lon2 - lon1) * Math.PI/180;
  const a = Math.sin(dphi/2)**2 + Math.cos(phi1)*Math.cos(phi2)*Math.sin(dlam/2)**2;
  return 2*R*Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
}

function cumulativeDistances(coords) {
  const dists = [0];
  for (let i = 1; i < coords.length; i++)
    dists.push(dists[i-1] + haversineM(coords[i-1][0], coords[i-1][1], coords[i][0], coords[i][1]));
  return dists;
}

function periodKeys(dateStr) {
  const dt = new Date(dateStr + 'T12:00:00');
  const y = dt.getFullYear(), m = dt.getMonth(), d = dt.getDate();
  const mm = String(m + 1).padStart(2, '0');
  const MSHORT = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  const MLONG  = ['January','February','March','April','May','June','July','August','September','October','November','December'];
  // ISO week number
  const thu = new Date(Date.UTC(y, m, d));
  thu.setUTCDate(thu.getUTCDate() + 4 - (thu.getUTCDay() || 7));
  const jan1 = new Date(Date.UTC(thu.getUTCFullYear(), 0, 1));
  const wk = Math.ceil(((thu - jan1) / 86400000 + 1) / 7);
  const isoY = thu.getUTCFullYear();
  // Monday of the ISO week
  const mon = new Date(y, m, d);
  mon.setDate(mon.getDate() - (mon.getDay() || 7) + 1);
  return {
    year:        String(y),
    year_label:  String(y),
    month:       `${y}-${mm}`,
    month_label: `${MLONG[m]} ${y}`,
    week:        `${isoY}-W${String(wk).padStart(2,'00')}`,
    week_label:  `Week of ${MSHORT[mon.getMonth()]} ${mon.getDate()}`,
    day:         dateStr,
    day_label:   `${MSHORT[m]} ${d}, ${y}`,
  };
}

function processRuns(rawRuns) {
  return rawRuns.map(run => {
    const dateStr = run.run_date || '';
    if (!dateStr) return null;
    const periods = periodKeys(dateStr);
    const encoded = run.summary_polyline || '';
    let coords = null, distances = null;
    if (encoded) {
      try { coords = decodePolyline(encoded); distances = cumulativeDistances(coords); }
      catch(e) { coords = null; distances = null; }
    }
    const akph = run.avg_speed_kmh;
    const speed_mph = akph ? Math.round(akph * 0.621371 * 100) / 100 : null;
    return {
      run_id:              String(run.run_id || ''),
      run_name:            run.run_name || 'Run',
      date:                dateStr,
      ...periods,
      distance_km:         run.distance_km,
      moving_time_min:     run.moving_time_min || 1,
      pace_min_per_km:     run.pace_min_per_km,
      speed_mph,
      run_avg_hr:          run.run_avg_hr,
      run_max_hr:          run.run_max_hr,
      same_day_recovery:   run.same_day_recovery,
      same_day_sleep_hours: run.same_day_sleep_hours,
      same_day_sleep_quality: run.same_day_sleep_quality,
      next_day_recovery:   run.next_day_recovery,
      recovery_delta:      run.recovery_delta,
      coords,
      distances,
    };
  }).filter(Boolean);
}

// ── Highlights + init (deferred until RUNS loads) ───────────────────────────
let HL_GPS = [], HL_DEFS;

function centerMap() {
  const gps = RUNS.filter(r => r.coords && r.coords.length);
  if (!gps.length) return;
  const all = gps.flatMap(r => r.coords);
  const lat = all.reduce((s, c) => s + c[0], 0) / all.length;
  const lng = all.reduce((s, c) => s + c[1], 0) / all.length;
  S.map.setView([lat, lng], 13);
}

function initApp() {
  _ALL_SPEEDS = RUNS.filter(r => r.speed_mph).map(r => r.speed_mph);
  MIN_SPEED = _ALL_SPEEDS.length ? Math.min(..._ALL_SPEEDS) : 5;
  MAX_SPEED = _ALL_SPEEDS.length ? Math.max(..._ALL_SPEEDS) : 10;

  centerMap();

  HL_GPS = RUNS.filter(r => r.coords && r.speed_mph);
  HL_DEFS = {
    longest: { fn: rs => rs.reduce((a, b) => (b.distance_km||0) > (a.distance_km||0) ? b : a) },
    fastest: { fn: rs => rs.filter(r => r.speed_mph).reduce((a, b) => b.speed_mph > a.speed_mph ? b : a) },
    latest:  { fn: rs => rs.reduce((a, b) => b.date > a.date ? b : a) },
  };

  document.querySelectorAll('.hbtn').forEach(btn => {
    btn.addEventListener('click', () => {
      const def = HL_DEFS[btn.dataset.hl];
      if (!def || !HL_GPS.length) return;
      const run = def.fn(HL_GPS);
      if (!run) return;
      document.querySelectorAll('.hbtn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      // Switch to Day gran and play just that run's day
      document.querySelectorAll('.gtab').forEach(b => b.classList.remove('active'));
      document.querySelector('.gtab[data-gran="day"]').classList.add('active');
      S.gran = 'day';
      selectPeriod(run.day);
    });
  });

  document.getElementById('speed-range').textContent =
    MIN_SPEED.toFixed(1) + ' \u2013 ' + MAX_SPEED.toFixed(1) + ' mph';
  updateDirBtn();
  buildPeriodList();

  document.getElementById('loading').style.display = 'none';
}

// ── Bootstrap ───────────────────────────────────────────────────────────────
fetch(RUNS_URL)
  .then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
  .then(data => { RUNS = processRuns(data.runs || []); initApp(); })
  .catch(err => {
    document.getElementById('loading').innerHTML =
      '<p style="color:var(--red);padding:16px">Failed to load run data: ' + err.message + '</p>';
  });
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    configure_logging()

    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(_HTML, encoding="utf-8")

    logger.info("Run replay written (fetches runs.json from jsDelivr at runtime)", extra={"path": str(_OUT)})
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
