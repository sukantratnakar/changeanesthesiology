#!/usr/bin/env python3
"""Checks the three-layers diagram, design v3 (Q12, D56 and D57, 17 Oct 2026).

Usage:  python3 tests/check_three_layers_v3.py <base-url>
  e.g.  python3 tests/check_three_layers_v3.py https://content-three-layers-v3-changeanesthesiology.sukantratnakar.workers.dev

Checks the pages served at <base-url>:
  TV-01  the figure's words, word for word, part by part and in reading order
  TV-02  the anchor #where-this-fits, with CA's own heading and one sentence
  TV-03  no sideways scroll at 390 px (also 360, 820, 1280 and 1440), no console errors
  TV-04  reading order on a phone: arch, Prechange, launch, after launch, ribbon, foundation
  TV-05  the screen-reader description, word for word (with D57's "designed to build")
  TV-06  v3's differences: "This book" beside Change Anesthesiology, no "This site", no zone
         names, no "The Mola Series · Book Two"; CA's fonts (Playfair Display, DM Sans, the
         label font), no Cormorant Garamond or Jost; HTML and CSS only (no image, no script)
  TV-07  v3's palette, scoped to the figure (.tl3); the routines colour is --routines, and the
         page source never says "habits"
  TV-08  nothing else changed against BASE_REF (default 2a2f919, main after PR #5, so the
         launch section must be exactly as live); article untouched. With EL-04 in
         tests/check_events_links.py, this replaces Q08's TL-05 (Q12b). From Q13 on it also
         accepts Q13's CSS block and Q15's arrival script (tests/check_anchor_position.py).
  TV-09  the Q04, Q06 (apart from its known PR-04 lines) and Q08 tests pass
Prints one PASS/FAIL line per check. Exits 1 if any check fails, 2 if the test can't run.
Node and Chrome must be installed.
"""

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_price_and_events as q06  # noqa: E402  (shared parser, fetch, Chrome path)
import check_three_layers as tl  # noqa: E402  (design v3's words and the figure reader)
import check_anchor_position as q13  # noqa: E402  (Q13's CSS block, which TV-08 accepts too)

from check_price_and_events import parse, text  # noqa: E402

q06.UA = "check_three_layers_v3.py (changeanesthesiology repo test)"
TESTS = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TESTS)
BASE_REF = os.environ.get("BASE_REF", "2a2f919")
WIDTHS = (360, 390, 820, 1280, 1440)
PALETTE = {"--energy": "#7A2E2A", "--slate": "#5C7385", "--sage": "#687B5A", "--routines": "#B07A3B",
           "--ink": "#0C203B", "--navy-deep": "#071426", "--gold": "#D4B15F", "--gold-ln": "#B8995A",
           "--accent": "#2E6B66"}
GONE = ["Broaden · Expand · Reduce · Increase", "Broaden", "Mola Series", "Book Two", "This site",
        "Where the Prechange Way comes from"]
ORDER = [".tl3-why", ".tl3-pc", ".tl3-launch", ".tl3-sf", ".tl3-ribbon", ".tl3-found"]
ORDER_NAMES = ["arch (why)", "Prechange", "launch", "after launch", "ribbon (how)", "foundation"]

# Q12's edits to BASE_REF's index.html, as (before, after), word for word: the old figure and its
# CSS (including .sr-only, which only it used) give way to design v3 and its CSS, scoped to .tl3.
OLD_SR = r'''.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
'''
OLD_CSS = r'''.fit{display:grid;grid-template-columns:1fr 270px;gap:1.5rem;margin-top:3rem}
.fit-stack{display:grid;gap:.9rem}
.fit-layer{display:grid;grid-template-columns:128px 1fr;gap:1.8rem;background:#fff;padding:1.8rem 2rem;border-top:3px solid var(--gold)}
.fit .fit-role{font-family:var(--serif);font-size:1.75rem;font-style:italic;color:var(--gold-dim);line-height:1.1}
.fit .fit-role small{display:block;font-family:var(--mono);font-size:.56rem;font-style:normal;letter-spacing:.16em;text-transform:uppercase;color:#8A857A;margin-top:.6rem;line-height:1.7}
.fit h3{font-family:var(--serif);font-size:1.3rem;font-weight:700;color:var(--ink);margin-bottom:.4rem;line-height:1.25}
.fit p{font-size:.88rem;line-height:1.7;color:#55524E}
.fit .fit-sub{font-family:var(--mono);font-size:.6rem;letter-spacing:.1em;text-transform:uppercase;color:var(--gold-dim);margin-top:.8rem;line-height:1.9}
.fit-name{display:flex;flex-wrap:wrap;align-items:center;gap:.45rem .7rem;margin-bottom:.4rem}
.fit .fit-name h3{margin:0}
.fit-here{font-family:var(--mono);font-size:.52rem;letter-spacing:.16em;text-transform:uppercase;color:var(--gold);border:1px solid rgba(212,177,95,.6);padding:.2rem .5rem}
.fit-layer.here{background:var(--navy)}
.fit-layer.here h3{color:var(--cream)}
.fit-layer.here p{color:var(--cream-dim)}
.fit-layer.here .fit-role{color:var(--gold)}
.fit-layer.here .fit-role small{color:var(--slate)}
.fit-layer.here .fit-sub{color:var(--gold)}
.fit-side{position:relative;border:1px solid rgba(169,141,82,.55);padding:1.8rem 1.7rem;display:flex;flex-direction:column;justify-content:center}
.fit-side::before{content:'';position:absolute;right:100%;top:50%;width:1.5rem;border-top:1px solid var(--gold-dim)}
.fit-side h3{font-style:italic}
.fit .fit-k{font-family:var(--mono);font-size:.6rem;letter-spacing:.18em;text-transform:uppercase;color:var(--gold-dim);margin-bottom:.8rem}
.fit-base{grid-column:1/-1;background:var(--navy-deep);padding:1.4rem 2rem;display:grid;grid-template-columns:128px 1fr;gap:1.8rem;align-items:baseline}
.fit .fit-base .fit-k{color:var(--gold);margin:0}
.fit-base p{color:var(--cream-dim)}
.fit-base b{font-family:var(--serif);font-size:1.15rem;color:var(--cream);font-weight:700;margin-right:.4rem}
'''
V3_CSS = r'''/* Three layers, one system: design v3 (Sukant, 17 Oct 2026, D56). A picture of time around one
   change. Scoped to .tl3, so nothing else on the page changes; CA's own fonts. */
.tl3{--ink:#0C203B;--navy-deep:#071426;--text:#1F2530;--grey:#535B68;--pale:#C8C6BE;--line:#D9D6CC;--accent:#2E6B66;--gold:#D4B15F;--gold-ln:#B8995A;--num:#735A26;--energy:#7A2E2A;--slate:#5C7385;--sage:#687B5A;--routines:#B07A3B;--fs-label:11px;--track-caps:.18em;--e:var(--energy);--h:var(--slate);--p:var(--sage);--r:var(--routines);--teal:var(--accent);color:var(--text);font-size:15px;line-height:1.65}
.tl3 *{box-sizing:border-box}
.tl3-cap{display:block;font-family:var(--mono);font-size:var(--fs-label);font-weight:500;letter-spacing:var(--track-caps);text-transform:uppercase}
.tl3-q{font-family:var(--serif);font-style:italic;font-size:30px;line-height:1}
.tl3-name{font-family:var(--serif);font-weight:500;font-size:23px;line-height:1.15;color:var(--ink)}
.tl3-txt{font-size:14px;line-height:1.5;margin-top:4px}
.tl3-sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.tl3-fig{margin-top:34px;display:grid;gap:0;max-width:956px}
.tl3-why{position:relative;text-align:center;padding:26px 22px 22px;border:2px solid var(--gold);border-bottom:0;border-radius:50% 50% 0 0/ 60px 60px 0 0;background:linear-gradient(#FBF6EA,rgba(251,246,234,0))}
.tl3-why .tl3-q,.tl3-why .tl3-cap{color:var(--num)}
.tl3-why .tl3-head{display:flex;justify-content:center;align-items:baseline;gap:12px;flex-wrap:wrap}
.tl3-why .tl3-txt{color:var(--text);max-width:34em;margin:6px auto 0}
.tl3-time{display:grid;gap:0;padding:0 0 0}
.tl3-seg{padding:20px 20px 22px;position:relative}
.tl3-pc{background:var(--ink);color:#E9E6DD}
.tl3-pc .tl3-q{color:var(--gold)}
.tl3-pc .tl3-cap{color:var(--pale)}
.tl3-pc .tl3-name{color:#fff}
.tl3-tag{display:inline-block;font-family:var(--mono);font-size:10px;font-weight:500;letter-spacing:var(--track-caps);text-transform:uppercase;border:1px solid var(--gold);color:var(--gold);padding:2px 7px;margin-left:8px;vertical-align:4px}
.tl3-why .tl3-tag{border-color:var(--num);color:var(--num);margin-left:0;align-self:center}
.tl3-bars{display:flex;align-items:flex-end;gap:10px;height:62px;margin-top:16px}
.tl3-bar{flex:1;max-width:58px;background:var(--c);border-radius:2px 2px 0 0;position:relative}
.tl3-bar.weak{outline:2px dashed var(--gold);outline-offset:3px}
.tl3-barlab{display:flex;gap:10px;margin-top:6px}
.tl3-barlab span{flex:1;max-width:58px;font-family:var(--mono);font-size:8.5px;letter-spacing:0;text-transform:uppercase;color:#C9C6BC;text-align:center}
.tl3-pc .tl3-note{font-size:13px;color:var(--gold);margin-top:10px}
.tl3-launch{display:flex;align-items:center;justify-content:center;gap:10px;padding:10px;background:var(--gold);color:var(--ink)}
.tl3-launch .tl3-cap{font-weight:600}
.tl3-flag{width:0;height:0;border-left:9px solid var(--ink);border-top:6px solid transparent;border-bottom:6px solid transparent}
.tl3-sf{background:#EFE7D6}
.tl3-sf .tl3-q{color:var(--num)}
.tl3-sf .tl3-cap{color:var(--num)}
.tl3-sf .tl3-name{font-style:italic}
.tl3-slip{margin-top:14px;height:46px;position:relative}
.tl3-slip svg{width:100%;height:100%;display:block}
.tl3-how{position:relative;padding:18px 20px 18px;background:#fff;border:1px solid var(--line);border-top:0}
.tl3-ribbon{height:10px;border-radius:5px;background:repeating-linear-gradient(90deg,var(--e) 0 40px,var(--h) 40px 80px,var(--p) 80px 120px,var(--r) 120px 160px);position:relative;margin-bottom:14px}
.tl3-ribbon::after{content:"";position:absolute;right:-10px;top:-5px;border-left:12px solid var(--ink);border-top:10px solid transparent;border-bottom:10px solid transparent}
.tl3-how .tl3-q{color:var(--teal)}
.tl3-how .tl3-cap{color:var(--teal)}
.tl3-head{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap}
.tl3-prac{display:flex;flex-wrap:wrap;gap:8px 16px;list-style:none;padding:0;margin-top:10px}
.tl3-prac li{display:flex;align-items:center;gap:7px;font-family:var(--mono);font-size:11px;font-weight:500;letter-spacing:.12em;text-transform:uppercase;color:var(--ink)}
.tl3-prac .d{width:9px;height:9px;border-radius:50%;background:var(--c)}
.tl3-found{background:var(--navy-deep);color:#D8D5CC;padding:16px 20px;display:flex;flex-wrap:wrap;align-items:baseline;gap:6px 16px;position:relative}
.tl3-found::before{content:"";position:absolute;left:0;right:0;top:-6px;height:6px;background:repeating-linear-gradient(90deg,var(--navy-deep) 0 6px,transparent 6px 12px)}
.tl3-found .tl3-cap{color:var(--gold)}
.tl3-found .tl3-name{color:#fff;font-size:20px}
.tl3-found .tl3-txt{margin:0;color:var(--pale)}
.tl3-legend{display:flex;flex-wrap:wrap;gap:4px 18px;margin-top:6px;font-family:var(--mono);font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--grey)}
.tl3-legend i{display:inline-block;width:18px;vertical-align:middle;margin-right:6px;border-top:2.5px solid var(--ink)}
.tl3-legend i.dash{border-top:1.5px dashed var(--gold-ln)}
@media(max-width:759px){
  .tl3-why .tl3-name{font-size:20px}
}
@media(min-width:760px){
  .tl3-why{padding:30px 40px 24px}
  .tl3-time{grid-template-columns:minmax(0,1.25fr) 44px minmax(0,1fr)}
  .tl3-seg{padding:24px 26px 26px}
  .tl3-launch{flex-direction:column;padding:12px 0}
  .tl3-launch .tl3-cap{writing-mode:vertical-rl;transform:rotate(180deg);letter-spacing:.22em}
  .tl3-flag{border-left:6px solid transparent;border-right:6px solid transparent;border-top:9px solid var(--ink);border-bottom:0}
  .tl3-how{padding:20px 26px}
  .tl3-found{padding:16px 26px}
  .tl3-q{font-size:34px}
}
'''
OLD_MEDIA_1024 = r'''@media(max-width:1024px){
  .fit{grid-template-columns:1fr}
  .fit-side::before{display:none}
}
'''
OLD_MEDIA_680 = r'''  .fit-layer{grid-template-columns:1fr;gap:.7rem;padding:1.5rem 1.4rem}
  .fit .fit-role{font-size:1.35rem}
  .fit .fit-role small{display:inline;margin:0}
  .fit .fit-sep{position:static;width:auto;height:auto;margin:0;overflow:visible;clip:auto;font-family:var(--mono);font-style:normal;font-size:.7rem;color:#8A857A;vertical-align:middle}
  .fit-side{padding:1.5rem 1.4rem}
  .fit-base{grid-template-columns:1fr;gap:.4rem;padding:1.3rem 1.4rem}
'''
OLD_FIGURE = r'''    <figure class="fit reveal">
      <figcaption class="sr-only">Diagram of how the parts fit. Three layers are stacked: Prechange says when, Change Anesthesiology says why, and Morphosis says how. The Sunfish Paradox sits beside them for depth. Iknetix and ZERO lie underneath as the foundation.</figcaption>
      <div class="fit-stack">
        <div class="fit-layer">
          <p class="fit-role">When <span class="sr-only fit-sep">·</span> <small>The stage</small></p>
          <div>
            <h3>Prechange</h3>
            <p>The stage before each change, and its measure, the Check.</p>
            <p class="fit-sub">Energy · Headroom · Perspective · Routines</p>
          </div>
        </div>
        <div class="fit-layer here">
          <p class="fit-role">Why <span class="sr-only fit-sep">·</span> <small>The philosophy and the model</small></p>
          <div>
            <div class="fit-name"><h3>Change Anesthesiology</h3><span class="fit-here">This book</span></div>
            <p>People adapt when the conditions around them let them. Resistance is often a signal that those conditions are missing.</p>
            <p class="fit-sub">Four zones · Broaden · Expand · Reduce · Increase</p>
          </div>
        </div>
        <div class="fit-layer">
          <p class="fit-role">How <span class="sr-only fit-sep">·</span> <small>The practice</small></p>
          <div>
            <h3>Morphosis</h3>
            <p>Five daily practices designed to build the four conditions.</p>
            <p class="fit-sub">White Space Thinking · Perspective Thinking · OmniMeta Mindfulness · Tinergy · The Habit Machine</p>
          </div>
        </div>
      </div>
      <div class="fit-side">
        <p class="fit-k">Depth · beside the three layers</p>
        <h3>The Sunfish Paradox</h3>
        <p>The book on carrying out change, and keeping it from slipping back after launch.</p>
        <p class="fit-sub">The Mola Series · Book Two</p>
      </div>
      <div class="fit-base">
        <p class="fit-k">Foundation</p>
        <p><b>Iknetix and ZERO</b> The author's earlier books.</p>
      </div>
    </figure>
'''
V3_FIGURE = r'''    <figure class="tl3 tl3-fig reveal" aria-describedby="tl3-desc">
     <div class="tl3-why">
      <div class="tl3-head"><span class="tl3-q">Why</span><span class="tl3-name">Change Anesthesiology</span><span class="tl3-tag">This book</span></div>
      <span class="tl3-cap" style="margin-top:6px">The philosophy and the model · four zones</span>
      <p class="tl3-txt">People adapt when the conditions around them let them. Resistance is often a signal that those conditions are missing.</p>
     </div>
     <div class="tl3-time">
      <div class="tl3-seg tl3-pc">
       <div class="tl3-head"><span class="tl3-q">When</span><span class="tl3-cap">Before each change</span></div>
       <div class="tl3-name" style="margin-top:8px">Prechange</div>
       <p class="tl3-txt">The stage before each change, and its measure, the Check.</p>
       <div class="tl3-bars" aria-hidden="true">
        <div class="tl3-bar" style="--c:var(--e);height:78%"></div><div class="tl3-bar weak" style="--c:var(--h);height:38%"></div><div class="tl3-bar" style="--c:var(--p);height:90%"></div><div class="tl3-bar" style="--c:var(--r);height:66%"></div>
       </div>
       <div class="tl3-barlab" aria-hidden="true"><span>Energy</span><span>Headroom</span><span>Perspective</span><span>Routines</span></div>
       <p class="tl3-note">The Check finds the weakest condition; a focused boost builds it before launch.</p>
      </div>
      <div class="tl3-launch"><span class="tl3-flag" aria-hidden="true"></span><span class="tl3-cap">Change launches</span></div>
      <div class="tl3-seg tl3-sf">
       <div class="tl3-head"><span class="tl3-q">Depth</span><span class="tl3-cap">During and after launch</span></div>
       <div class="tl3-name" style="margin-top:8px">The Sunfish Paradox</div>
       <p class="tl3-txt">Carrying out change, and keeping it from slipping back after launch.</p>
       <div class="tl3-slip" aria-hidden="true"><svg viewBox="0 0 300 40" preserveAspectRatio="none">
        <path d="M0 10 C60 10 90 34 150 34 S240 14 300 12" fill="none" stroke="#B8995A" stroke-width="1.5" stroke-dasharray="4 4"/>
        <path d="M0 10 L300 10" fill="none" stroke="#0C203B" stroke-width="2.5"/>
       </svg></div>
       <div class="tl3-legend" aria-hidden="true"><span><i></i>The change holds</span><span><i class="dash"></i>Without it, it slips back</span></div>
      </div>
     </div>
     <div class="tl3-how">
      <div class="tl3-ribbon" aria-hidden="true"></div>
      <div class="tl3-head"><span class="tl3-q">How</span><span class="tl3-name">Morphosis</span><span class="tl3-cap">Every day, before, during and after</span></div>
      <p class="tl3-txt">Five daily practices designed to build the four conditions.</p>
      <ul class="tl3-prac">
       <li style="--c:var(--e)"><span class="d"></span>Tinergy</li><li style="--c:var(--h)"><span class="d"></span>White Space Thinking</li><li style="--c:var(--h)"><span class="d"></span>OmniMeta Mindfulness</li><li style="--c:var(--p)"><span class="d"></span>Perspective Thinking</li><li style="--c:var(--r)"><span class="d"></span>Habit Machine</li>
      </ul>
     </div>
     <div class="tl3-found">
      <span class="tl3-cap">Foundation</span><span class="tl3-name"><em>Iknetix</em> and <em>ZERO</em></span>
      <p class="tl3-txt">The author's earlier books. <em>Iknetix</em> also feeds the perspective tools.</p>
     </div>
     <p class="tl3-sr" id="tl3-desc">A picture of time around one change. Over everything, the why: Change Anesthesiology, the philosophy and the model. On the timeline, before the change launches: Prechange, the stage before each change, where the Check measures energy, headroom, perspective and routines, finds the weakest, and a focused boost builds it. After the change launches: The Sunfish Paradox, on carrying out change and keeping it from slipping back. Running underneath the whole timeline, every day: Morphosis, five daily practices, each designed to build one of the four conditions. At the base, the foundation: Iknetix and ZERO, the author's earlier books.</p>
    </figure>
'''
APPROVED_EDITS = [(OLD_SR, ""), (OLD_CSS, V3_CSS), (OLD_MEDIA_1024, ""), (OLD_MEDIA_680, ""), (OLD_FIGURE, V3_FIGURE)]
# Q13 (D61) adds one CSS block so links land on their section, and Q15 (D65) a short arrival
# script; their exact edits live in tests/check_anchor_position.py (AP-05), and TV-08 accepts
# them and nothing else.
LATER_EDITS = q13.APPROVED_EDITS

RESULTS = []


def report(ok, req, what, detail=""):
    RESULTS.append((req, bool(ok)))
    print(f"{'PASS' if ok else 'FAIL'}  {req}  {what:<60} {detail}".rstrip())


def die(msg):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(2)


def git(*args):
    return subprocess.run(["git", "-C", REPO_ROOT, *args], check=True, capture_output=True, text=True).stdout


def first(nodes):
    return nodes[0] if nodes else None


BROWSER = r"""
const { spawn } = require('child_process');
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const chrome = spawn(input.chrome, ['--headless=new', '--disable-gpu', '--hide-scrollbars', '--no-first-run',
    `--user-data-dir=${input.profile}`, `--remote-debugging-port=${input.port}`, 'about:blank'], { stdio: 'ignore' });
  try {
    let t = [];
    for (let i = 0; i < 75 && !t.length; i++) {
      try { t = await (await fetch(`http://127.0.0.1:${input.port}/json/list`)).json(); } catch {}
      if (!t.length) await sleep(200);
    }
    const page = t.find(x => x.type === 'page');
    if (!page) throw new Error('Chrome did not start');
    const ws = new WebSocket(page.webSocketDebuggerUrl);
    await new Promise((ok, bad) => { ws.addEventListener('open', ok, { once: true }); ws.addEventListener('error', bad, { once: true }); });
    let id = 0; const waiting = new Map(), events = [];
    ws.addEventListener('message', e => { const m = JSON.parse(e.data);
      if (m.id && waiting.has(m.id)) { waiting.get(m.id)(m); waiting.delete(m.id); } else events.forEach(f => f(m)); });
    const send = (method, params = {}) => new Promise((ok, bad) => { const i = ++id;
      waiting.set(i, m => m.error ? bad(new Error(method + ': ' + m.error.message)) : ok(m.result));
      ws.send(JSON.stringify({ id: i, method, params })); });
    await send('Page.enable'); await send('Runtime.enable'); await send('Log.enable'); await send('Network.enable');
    await send('Network.setBlockedURLs', { urls: ['*googletagmanager.com*', '*google-analytics.com*',
      '*analytics.google.com*', '*cloudflareinsights.com*', '*doubleclick.net*'] });
    let errors = [];
    events.push(m => {
      if (m.method === 'Runtime.exceptionThrown') errors.push('exception: ' + (m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text));
      if (m.method === 'Runtime.consoleAPICalled' && m.params.type === 'error') errors.push('console: ' + m.params.args.map(a => a.value ?? a.description).join(' '));
      if (m.method === 'Log.entryAdded' && m.params.entry.level === 'error' && !/ERR_BLOCKED_BY_CLIENT/.test(m.params.entry.text)) errors.push('log: ' + m.params.entry.text);
    });
    const out = [];
    for (const c of input.cases) {
      await send('Emulation.setDeviceMetricsOverride', { width: c.width, height: 900, deviceScaleFactor: 1, mobile: c.width < 768 });
      await send('Page.navigate', { url: 'about:blank' }); await sleep(250);
      errors = [];
      const loaded = new Promise(r => events.push(function f(m) {
        if (m.method === 'Page.loadEventFired') { events.splice(events.indexOf(f), 1); r(); } }));
      await send('Page.navigate', { url: c.url }); await loaded;
      await send('Runtime.evaluate', { expression: 'document.fonts.ready.then(() => 1)', awaitPromise: true });
      await sleep(800);
      const value = (await send('Runtime.evaluate', { returnByValue: true, expression: c.expr })).result.value;
      out.push({ name: c.name, value, errors: [...errors] });
    }
    console.log(JSON.stringify(out)); ws.close();
  } finally { chrome.kill(); }
})().catch(e => { console.error(e.message); process.exit(1); });
"""

PAGE_EXPR = """(() => {
  const d = document.documentElement, q = s => document.querySelector(s);
  const top = s => { const e = q(s); return e ? e.getBoundingClientRect().top + scrollY : null; };
  const font = s => { const e = q(s); return e ? getComputedStyle(e).fontFamily : null; };
  const desc = q('#tl3-desc'), r = desc ? desc.getBoundingClientRect() : null;
  return { over: d.scrollWidth - d.clientWidth,
           tops: %s.map(top),
           fonts: { q: font('.tl3 .tl3-q'), name: font('.tl3 .tl3-name'), txt: font('.tl3 .tl3-txt'),
                    cap: font('.tl3 .tl3-cap'), tag: font('.tl3 .tl3-tag') },
           desc: r ? [r.width, r.height] : null }; })()""" % json.dumps(ORDER)


def browser(cases):
    if not os.path.exists(q06.CHROME):
        die(f"Chrome not found at {q06.CHROME} (set CHROME)")
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    profile = tempfile.mkdtemp(prefix="check-three-layers-v3-")
    try:
        r = subprocess.run(["node", "-e", BROWSER], capture_output=True, text=True, timeout=300,
                           input=json.dumps({"chrome": q06.CHROME, "port": port, "profile": profile, "cases": cases}))
    finally:
        time.sleep(0.5)
        shutil.rmtree(profile, ignore_errors=True)
    if r.returncode != 0:
        die(f"browser check failed to run: {r.stderr.strip()[:300]}")
    return {x["name"]: x for x in json.loads(r.stdout)}


def changes(old, new):
    """How the served page differs from BASE_REF plus Q12's (and Q13's) edits; [] if not at all."""
    if APPROVED_EDITS is None:
        return ["Q12's edits are not recorded in this test yet"]
    want = old
    for before, after in APPROVED_EDITS + LATER_EDITS:
        if want.count(before) != 1:
            return [f"approved edit not found once in {BASE_REF}: {before[:40]!r}"]
        want = want.replace(before, after)
    if new == want:
        return []
    w, n = want.split("\n"), new.split("\n")
    k = next((i for i, (a, b) in enumerate(zip(w, n)) if a != b), min(len(w), len(n)))
    return [f"line {k + 1} differs: {(n[k] if k < len(n) else '(end of file)').strip()[:60]!r}"]


PLANTED = {
    "word changed outside the band": lambda h: h.replace("surgery was torture", "surgery was agony", 1),
    "a font link added": lambda h: h.replace("</head>", '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Jost">\n</head>', 1),
    "page colour changed": lambda h: h.replace("--slate:#8792A6", "--slate:#5C7385", 1),
    "figure word changed": lambda h: h.replace("Change launches", "Launch day", 1),
    "script added": lambda h: h.replace("</body>", "<script>void 0</script></body>", 1),
}


def run_suite(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    except (OSError, subprocess.TimeoutExpired) as e:
        return None, [], str(e)
    return r, [l for l in r.stdout.splitlines() if l.startswith(("PASS", "FAIL"))], r.stderr.strip()


def main():
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} <base-url>", file=sys.stderr)
        sys.exit(2)
    base = sys.argv[1].rstrip("/")
    try:
        index, article = q06.fetch(base + "/"), q06.fetch(base + "/article")
    except Exception as e:  # noqa: BLE001
        die(f"cannot fetch {base}: {e}")
    root = parse(index)
    print(f"Checking {base} (base reference {BASE_REF})\n")
    band = first(root.find_all(lambda n: n.tag == "section" and n.attrs.get("id") == "where-this-fits"))
    fig = first(band.find_all(lambda n: n.tag == "figure")) if band else None

    # TV-01: the figure's words.
    parts = tl.v3_parts(fig)
    for key, want in tl.V3.items():
        report(parts[key] == want, "TV-01", f"Words: {key}", "ok" if parts[key] == want else str(parts[key])[:80])
    shown = text(fig, skip=lambda n: "tl3-sr" in n.classes()) if fig else ""
    report(shown == tl.FIG_TEXT, "TV-01", "The figure says exactly v3's words, in reading order, nothing more",
           "ok" if shown == tl.FIG_TEXT else f"{len(shown)} characters, expected {len(tl.FIG_TEXT)}")
    print()

    # TV-02: the anchor, with CA's own heading and sentence.
    secs = [n.attrs.get("id") for n in root.find_all(lambda n: n.tag == "section")]
    tag = first(band.find_all(lambda n: "tag" in n.classes())) if band else None
    head = first(band.find_all(lambda n: n.tag == "h2")) if band else None
    line = first(band.find_all(lambda n: "fit-line" in n.classes())) if band else None
    report(band is not None and secs.index("where-this-fits") == secs.index("morphosis") + 1 if band else False,
           "TV-02", "id=\"where-this-fits\" exists, right after #morphosis")
    got = (text(tag) if tag else "", text(head) if head else "", text(line) if line else "")
    report(got == (tl.BAND_TAG, tl.BAND_HEAD, tl.ONE_SENTENCE), "TV-02", "CA's heading and one sentence kept", " / ".join(got)[:80])
    print()

    # TV-05: the screen-reader description.
    desc = first(fig.find_all(lambda n: n.attrs.get("id") == "tl3-desc")) if fig else None
    report(desc is not None and text(desc) == tl.FIG_DESC and "tl3-sr" in desc.classes()
           and fig.attrs.get("aria-describedby") == "tl3-desc", "TV-05",
           "Screen-reader description, word for word (D57)", text(desc)[:70] if desc else "missing")
    print()

    # TV-06: v3's differences, fonts, HTML and CSS only.
    words = text(band) if band else ""
    why = first(fig.find_all(lambda n: "tl3-why" in n.classes())) if fig else None
    tagged = first(why.find_all(lambda n: "tl3-tag" in n.classes())) if why else None
    head = tagged.parent if tagged is not None else None
    sibs = [c for c in head.children if not isinstance(c, str)] if head is not None else []
    beside = (tagged in sibs and sibs.index(tagged) > 0 and "tl3-name" in sibs[sibs.index(tagged) - 1].classes()
              and text(sibs[sibs.index(tagged) - 1]) == "Change Anesthesiology")
    report(tagged is not None and text(tagged) == "This book" and beside, "TV-06", "'This book' beside Change Anesthesiology")
    found = [g for g in GONE if g.lower() in words.lower()]
    report(not found, "TV-06", "No 'This site', zone names, Mola Series line or file heading", ", ".join(found) or "ok")
    bad = [n.tag for n in fig.walk() if n.tag in ("img", "script", "canvas", "picture", "iframe", "object", "link", "style")] if fig else ["no figure"]
    report(not bad, "TV-06", "HTML and CSS only: no image, script or embed in the figure", ", ".join(bad) or "ok")
    report(not re.search(r"cormorant|jost", index, re.I), "TV-06", "No Cormorant Garamond or Jost anywhere")
    print()

    # TV-07: the palette, scoped to .tl3, and no "habits" in the source.
    rule = re.search(r"(?m)^\.tl3\{([^}]*)\}", index)
    decl = dict(re.findall(r"(--[\w-]+):([^;]+)", rule.group(1))) if rule else {}
    wrong = [f"{k} {decl.get(k)}" for k, v in PALETTE.items() if (decl.get(k) or "").upper() != v.upper()]
    report(rule and not wrong, "TV-07", "v3's palette set on .tl3 (only the figure)", ", ".join(wrong) or "ok")
    root_rule = re.search(r":root\{([^}]*)\}", index)
    leaked = [k for k in PALETTE if k not in ("--navy-deep", "--gold", "--ink", "--slate") and root_rule and k in root_rule.group(1)]
    report(not leaked, "TV-07", "Nothing added to the page's own colours (:root)", ", ".join(leaked) or "ok")
    report("--routines" in decl and not re.search(r"habits", index, re.I), "TV-07",
           "Routines colour is --routines; 'habits' is nowhere in the page source")
    print()

    # TV-03 and TV-04 in Chrome: no sideways scroll, reading order on a phone, fonts, hidden description.
    res = browser([{"name": f"{w}px", "url": base + "/", "width": w, "expr": PAGE_EXPR} for w in WIDTHS])
    for w in WIDTHS:
        x = res[f"{w}px"]
        report(x["value"]["over"] <= 0 and not x["errors"], "TV-03", f"{w} px: no sideways scroll, no console errors",
               "; ".join(x["errors"])[:60] or f"{x['value']['over']} px sideways")
    tops = res["390px"]["value"]["tops"]
    ordered = all(t is not None for t in tops) and all(a < b for a, b in zip(tops, tops[1:]))
    report(ordered, "TV-04", "390 px reading order: " + ", ".join(ORDER_NAMES),
           ", ".join(f"{n} {int(t) if t is not None else '-'}" for n, t in zip(ORDER_NAMES, tops))[:90])
    fonts = res["1280px"]["value"]["fonts"]
    ok = (all("Playfair Display" in (fonts[k] or "") for k in ("q", "name")) and "DM Sans" in (fonts["txt"] or "")
          and all("JetBrains Mono" in (fonts[k] or "") for k in ("cap", "tag")))
    report(ok, "TV-06", "Fonts: Playfair (Why/When/How/Depth, names), DM Sans (text), label font (capitals)",
           "; ".join(f"{k}: {(v or '').split(',')[0]}" for k, v in fonts.items()))
    d = res["390px"]["value"]["desc"]
    report(d is not None and d[0] <= 1 and d[1] <= 1, "TV-05", "Description hidden on screen, kept for screen readers", str(d))
    print()

    # TV-08: nothing else changed against main.
    try:
        changed = [f for f in git("diff", "--name-only", BASE_REF, "HEAD").split("\n") if f]
        dirty = git("status", "--porcelain", "--untracked-files=no").strip()
        old_index, old_article = git("show", f"{BASE_REF}:index.html"), git("show", f"{BASE_REF}:article.html")
    except subprocess.CalledProcessError as e:
        die(f"git failed: {e.stderr.strip()}")
    extra = [f for f in changed if f != "index.html" and not f.startswith("tests/")]
    report(not extra, "TV-08", f"Checkout: only index.html and tests/ changed since {BASE_REF}", ", ".join(extra) or f"{len(changed)} files")
    report(not dirty, "TV-08", "Checkout: no uncommitted changes to tracked files", dirty.replace("\n", ", ")[:80] or "clean")
    report(article == old_article, "TV-08", f"article.html is exactly as in {BASE_REF}")
    probs = changes(old_index, index)
    report(not probs, "TV-08", f"index.html: {BASE_REF} plus the v3 figure (and Q13 CSS) only", "; ".join(probs) or "ok")
    if probs:
        report(False, "TV-08", "Self-test: planted edits are caught", "needs a page that passes first")
    else:
        missed = [k for k, plant in PLANTED.items() if plant(index) == index or not changes(old_index, plant(index))]
        report(not missed, "TV-08", f"Self-test: all {len(PLANTED)} planted edits are caught", ", ".join(missed) or "ok")
    print()

    # TV-09: the earlier suites.
    for label, cmd, skip in (
            ("Q04 test: every check passes", ["bash", os.path.join(TESTS, "check_public_files.sh"), base], ()),
            ("Q06 test: every check but PR-04 passes", [sys.executable, os.path.join(TESTS, "check_price_and_events.py"), base], ("PR-04",)),
            ("Q08 test: every check passes (TL-05 replaced)", [sys.executable, os.path.join(TESTS, "check_three_layers.py"), base], ())):
        r, lines, err = run_suite(cmd)
        if r is None or not lines:
            report(False, "TV-09", label, (err or "no output")[:80])
            continue
        fails = [l for l in lines if l.startswith("FAIL") and l.split()[1] not in skip]
        skipped = sum(1 for l in lines if l.split()[1] in skip)
        report(not fails and r.returncode in ((0, 1) if skip else (0,)), "TV-09", label,
               f"{len(lines) - skipped - len(fails)} passed, {len(fails)} failed" + (f", {skipped} PR-04 lines" if skip else "")
               + (f": {fails[0][:50]}" if fails else ""))
    print()

    by_req = {}
    for req, ok in RESULTS:
        by_req.setdefault(req, []).append(ok)
    print("Summary: " + "  ".join(f"{r} {'PASS' if all(v) else 'FAIL'}" for r, v in sorted(by_req.items())))
    failed = sum(1 for _, ok in RESULTS if not ok)
    print(f"Result: {len(RESULTS) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
