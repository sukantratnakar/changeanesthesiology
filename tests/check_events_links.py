#!/usr/bin/env python3
"""Checks that events are linked, not fed (Q10, D48 and D49, 16 Oct 2026).

Usage:  python3 tests/check_events_links.py <base-url>
  e.g.  python3 tests/check_events_links.py https://content-events-links-changeanesthesiology.sukantratnakar.workers.dev

Checks the pages served at <base-url>:
  EL-01  an "Upcoming Events" link to https://prechangeway.com/events in the menu, the home page
         event section and the footer (D49, D22b-7)
  EL-02  the launch photos link goes to prechangeway.com/events#spotlight-change-anesthesiology-2026-08
  EL-03  those "Upcoming Events" links count as register_click; photo links do not (D22b-9, D25-3)
  EL-04  nothing else changed against BASE_REF (default 27cf1c4, main after Q08), and nothing
         from Q09 is in the checkout. This replaces Q08's TL-05, as Q09 did; from Q12 on,
         TV-08 in tests/check_three_layers_v3.py shares it, and EL-04 also accepts Q12's
         exact edits to the diagram (Q12b) and Q13's CSS block.
  EL-05  no request to prechangeway.com when either page loads (headless Chrome, analytics blocked)
  EL-06  the Q04, Q06 (apart from its known PR-04 lines) and Q08 tests pass
Q11 (D50) adds, for the launch section as a past event:
  LP-01  the section reads as a past event (tag and heading)
  LP-02  the 12 launch photos, in album order, copied into images/launch/ (at most 800 px on the
         page, 1,000 px full size), each with width, height, lazy loading, alt text and a full-size link
  LP-03  the video as a local thumbnail with "Watch on YouTube ↗"; no embedded player
  LP-04  "Show more photos": 6 shown, 12 when opened; without the script all 12 show
  LP-05  photo and video links are not register_click (D25-3)
  LP-06  no file details in any copy, every photo served from this site; EL-05 also bars YouTube
Q11b (D51 to D54), after Sukant's review:
  LB-01  the speaker cards stay: the author, Tammy Martins and Ryan Myers, with their profiles
  LB-02  no community partner card or credit (name, photo, logo, text)
  LB-03  the programme is gone; the date, time and place stay
  LB-04  the highlight line, word for word, with the book title in italics
  LB-05  the "Next events" label and "Online and in person · on prechangeway.com" stay
  The photos link (EL-02), the Upcoming Events links (EL-01), the photos and video (LP) and the
  article page byte-identical to main (EL-04) are checked above.
Q11c (D55), unused files removed:
  LC-01  the 8 files are gone from the repo and return 404
  LC-02  every image, icon and share image on both pages is served, and none shows broken
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
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_price_and_events as q06  # noqa: E402  (shared parser, fetch, click harness, Chrome path)
import check_three_layers_v3 as v3  # noqa: E402  (Q12's exact edits to the diagram, for EL-04)
import check_anchor_position as q13  # noqa: E402  (Q13's CSS block, for EL-04)

from check_price_and_events import parse, text  # noqa: E402

q06.UA = "check_events_links.py (changeanesthesiology repo test)"
TESTS = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TESTS)
BASE_REF = os.environ.get("BASE_REF", "27cf1c4")
EVENTS_URL = "https://prechangeway.com/events"
PHOTOS_URL = EVENTS_URL + "#spotlight-change-anesthesiology-2026-08"
LABEL = "Upcoming Events"
PHOTOS_TEXT = "Photos from the launch →"
# Q11 (D50): the launch section becomes a past event, with a one-time copy of the launch photos
# and video. The new CSS, photos-and-video block and "Show more photos" script, word for word.
LAUNCH_CSS = r'''/* ── launch photos and video (Q11): a one-time copy, nothing loads from elsewhere ── */
#event .event-top{align-items:start}
.event-hl{margin-top:2.6rem;padding-top:1.6rem;border-top:1px solid rgba(212,177,95,.22);font-size:1rem;line-height:1.8;color:var(--cream-dim);max-width:520px}
.event-hl em{color:var(--cream)}
.lp-media{margin-top:3.5rem;padding-top:2.6rem;border-top:1px solid rgba(212,177,95,.2)}
.lp-photos,.lp-videos{list-style:none;display:grid;grid-template-columns:repeat(3,1fr);gap:.8rem}
.lp-photos a{display:block;background:var(--navy)}
.lp-photos img{width:100%;height:auto;aspect-ratio:3/2;object-fit:cover;transition:opacity .25s}
.lp-photos a:hover img{opacity:.85}
.lp-photos a:focus-visible,.lp-videos a:focus-visible,.lp-more .btn:focus-visible{outline:2px solid var(--gold);outline-offset:3px}
.lp-photos.lp-folded li:nth-child(n+7){display:none}
.lp-more{margin-top:1.6rem;text-align:center}
.lp-more .btn{background:none}
.lp-video{margin-top:3rem;padding-top:2.2rem;border-top:1px solid rgba(212,177,95,.14)}
.lp-videos a{display:block}
.lp-thumb{position:relative;display:block;background:var(--navy)}
.lp-thumb img{width:100%;height:auto;aspect-ratio:16/9;object-fit:cover}
.lp-play{position:absolute;left:50%;top:50%;width:56px;height:40px;transform:translate(-50%,-50%)}
.lp-vtitle{display:block;font-family:var(--serif);font-size:1.02rem;font-weight:700;color:var(--cream);margin-top:.8rem}
.lp-vlink{display:block;margin-top:.3rem;font-family:var(--mono);font-size:.62rem;letter-spacing:.12em;text-transform:uppercase;color:var(--gold)}
.lp-videos a:hover .lp-vlink{color:var(--cream)}
@media(max-width:680px){
  .lp-photos,.lp-videos{grid-template-columns:1fr 1fr;gap:.5rem}
  .lp-videos li{grid-column:1/-1}
}
'''
LAUNCH_MEDIA = r'''    <!-- Launch photos and video: a one-time copy of prechangeway.com's launch entry (Q11, D50) -->
    <div class="lp-media">
      <p class="tag reveal">Photos</p>
      <ul class="lp-photos" id="lp-photos">
        <li><a href="images/launch/full/01.jpg"><img src="images/launch/01.jpg" width="800" height="533" alt="Speakers and guests on stage holding copies of Change Anesthesiology" loading="lazy" decoding="async"></a></li>
        <li><a href="images/launch/full/02.jpg"><img src="images/launch/02.jpg" width="800" height="533" alt="A talk at the podium, with the audience in the auditorium at Alice Turner Library" loading="lazy" decoding="async"></a></li>
        <li><a href="images/launch/full/03.jpg"><img src="images/launch/03.jpg" width="800" height="533" alt="Group photo of guests at the Change Anesthesiology book launch" loading="lazy" decoding="async"></a></li>
        <li><a href="images/launch/full/04.jpg"><img src="images/launch/04.jpg" width="800" height="533" alt="The auditorium from the back during a talk" loading="lazy" decoding="async"></a></li>
        <li><a href="images/launch/full/05.jpg"><img src="images/launch/05.jpg" width="800" height="533" alt="Five guests, two of them holding books, one of them Change Anesthesiology" loading="lazy" decoding="async"></a></li>
        <li><a href="images/launch/full/06.jpg"><img src="images/launch/06.jpg" width="800" height="533" alt="A copy of Change Anesthesiology being presented" loading="lazy" decoding="async"></a></li>
        <li><a href="images/launch/full/07.jpg"><img src="images/launch/07.jpg" width="800" height="533" alt="A speaker in a light blue jacket at the podium" loading="lazy" decoding="async"></a></li>
        <li><a href="images/launch/full/08.jpg"><img src="images/launch/08.jpg" width="800" height="536" alt="A speaker in a teal shirt at the podium" loading="lazy" decoding="async"></a></li>
        <li><a href="images/launch/full/09.jpg"><img src="images/launch/09.jpg" width="800" height="533" alt="A speaker in a dark jacket and white shirt at the podium" loading="lazy" decoding="async"></a></li>
        <li><a href="images/launch/full/10.jpg"><img src="images/launch/10.jpg" width="800" height="533" alt="A speaker in glasses at the podium, with notes in hand" loading="lazy" decoding="async"></a></li>
        <li><a href="images/launch/full/11.jpg"><img src="images/launch/11.jpg" width="800" height="533" alt="A speaker in a red tie at the podium" loading="lazy" decoding="async"></a></li>
        <li><a href="images/launch/full/12.jpg"><img src="images/launch/12.jpg" width="800" height="533" alt="A speaker in a grey jacket at the podium" loading="lazy" decoding="async"></a></li>
      </ul>
      <div class="lp-video">
        <p class="tag reveal">Video</p>
        <ul class="lp-videos">
          <li><a href="https://youtu.be/DDxNcCjijgg" target="_blank" rel="noopener"><span class="lp-thumb"><img src="images/launch/video.jpg" width="800" height="450" alt="Video: Change Anesthesiology" loading="lazy" decoding="async"><svg class="lp-play" viewBox="0 0 68 48" aria-hidden="true" focusable="false"><rect width="68" height="48" rx="12" fill="#0C203B" fill-opacity="0.78"/><path d="M27 14v20l18-10z" fill="#D4B15F"/></svg></span><span class="lp-vtitle" aria-hidden="true">Change Anesthesiology</span><span class="lp-vlink">Watch on YouTube &#8599;</span></a></li>
        </ul>
      </div>
    </div>

'''
LAUNCH_PROGRAMME = r'''        <div class="prog">
          <div class="prog-row reveal"><b>5:30</b><div><em>Welcome &amp; Networking</em>Guests arrived and connected over evening snacks</div></div>
          <div class="prog-row reveal"><b>5:45</b><div><em>Book Launch</em>Sukant Ratnakar presented Change Anesthesiology</div></div>
          <div class="prog-row reveal"><b>6:05</b><div><em>Guest Author Talks</em>Tammy Martins and Ryan Myers</div></div>
          <div class="prog-row reveal"><b>6:25</b><div><em>Q&amp;A</em>Open questions with all three authors</div></div>
          <div class="prog-row reveal"><b>6:45 – 7:00</b><div><em>Closing</em>Conversations and networking</div></div>
          <div class="prog-row reveal" style="border-bottom:none;padding-top:1.3rem"><b style="color:var(--cream)">7:00</b><div style="color:var(--gold)">Event ended</div></div>
        </div>
'''
LAUNCH_HIGHLIGHT_HTML = r'''        <p class="event-hl reveal">Sukant Ratnakar launched <em>Change Anesthesiology: Why Resistance Is Never the Problem</em>, with short talks from guest authors Tammy Martins and Ryan Myers.</p>
'''
LAUNCH_PARTNER = r'''
    <div class="partner reveal">
      <img src="images/partner-masud.jpg" alt="Masud Alam" class="partner-photo">
      <div class="partner-body">
        <p class="partner-l">Community Partner</p>
        <p class="partner-name">Masud Alam</p>
        <p class="partner-role">President and Founder &middot; Elite Leadership Club of Canada</p>
        <p class="partner-p">Brought together leaders from across business, public service, and community life in Saskatchewan for the evening.</p>
      </div>
      <img src="images/elc-logo.png" alt="Elite Leadership Club of Canada" class="partner-mark">
    </div>
'''
LAUNCH_SCRIPT = r'''<script>
/* Launch photos (Q11): 6 show, the other 6 sit behind "Show more photos". Without this script
   all 12 show. Each photo opens its full-size copy, as on prechangeway.com. */
(function(){
  var list=document.getElementById('lp-photos');
  if(!list||list.children.length<=6)return;
  var wrap=document.createElement('div'),b=document.createElement('button');
  wrap.className='lp-more';b.type='button';b.className='btn btn-line';b.setAttribute('aria-controls','lp-photos');
  var set=function(open){list.classList.toggle('lp-folded',!open);b.setAttribute('aria-expanded',String(open));b.textContent=open?'Show fewer photos':'Show more photos'};
  b.addEventListener('click',function(){set(list.classList.contains('lp-folded'))});
  wrap.appendChild(b);list.insertAdjacentElement('afterend',wrap);set(false);
})();
</script>'''
# Edits to BASE_REF, as (file, before, after). Q10 needed none (the three links and the photos
# address were already in place on main); Q11 relabels the section and adds the photos and video.
APPROVED_EDITS = [
    ("index.html", '<p class="tag reveal">How the book launched</p>', '<p class="tag reveal">Past event</p>'),
    ("index.html", '<h2 class="head reveal">An evening of conversation,<br>ideas, and connection.</h2>',
     '<h2 class="head reveal">How the book<br>launched.</h2>'),
    ("index.html", "/* ── reveal ── */", LAUNCH_CSS + "/* ── reveal ── */"),
    ("index.html", '    <div class="speakers" style="margin-top:3.5rem">',
     LAUNCH_MEDIA + '    <div class="speakers" style="margin-top:3.5rem">'),
    ("index.html", "</body>", LAUNCH_SCRIPT + "\n</body>"),
    # Q11b (D53, D54): the programme gives way to one highlight line.
    ("index.html", LAUNCH_PROGRAMME, LAUNCH_HIGHLIGHT_HTML),
    # Q11b (D52): the community partner card goes.
    ("index.html", LAUNCH_PARTNER, ""),
]
# Q12b: design v3 of the three-layers diagram (D56, D57) is on the page too. Its exact edits live
# in tests/check_three_layers_v3.py (TV-08); EL-04 accepts those and nothing else outside the launch section.
# Q13 (D61) adds one CSS block so links land on their section (tests/check_anchor_position.py, AP-05).
APPROVED_EDITS += [("index.html", before, after) for before, after in v3.APPROVED_EDITS + q13.APPROVED_EDITS]
Q09_FILES = ("scripts/events-feed.mjs", ".github/workflows/events-feed.yml", "data/events.json", "images/events/")
# Q11: the 12 launch photos ("Website" copies, in album order) and the video, copied once.
LAUNCH_ALTS = [
    "Speakers and guests on stage holding copies of Change Anesthesiology",
    "A talk at the podium, with the audience in the auditorium at Alice Turner Library",
    "Group photo of guests at the Change Anesthesiology book launch",
    "The auditorium from the back during a talk",
    "Five guests, two of them holding books, one of them Change Anesthesiology",
    "A copy of Change Anesthesiology being presented",
    "A speaker in a light blue jacket at the podium",
    "A speaker in a teal shirt at the podium",
    "A speaker in a dark jacket and white shirt at the podium",
    "A speaker in glasses at the podium, with notes in hand",
    "A speaker in a red tie at the podium",
    "A speaker in a grey jacket at the podium",
]
VIDEO_URL = "https://youtu.be/DDxNcCjijgg"
# Q11b (D51 to D54): the launch section after Sukant's review.
HIGHLIGHT = ("Sukant Ratnakar launched Change Anesthesiology: Why Resistance Is Never the Problem, "
             "with short talks from guest authors Tammy Martins and Ryan Myers.")
HIGHLIGHT_TITLE = "Change Anesthesiology: Why Resistance Is Never the Problem"
WHEN = ("THURSDAY 13 AUGUST 2026", "5:30 – 7:00 pm", "Auditorium, Alice Turner Library Saskatoon, Saskatchewan")
SPEAKERS = ["Sukant Ratnakar", "Tammy Martins", "Ryan Myers"]
GUEST_BOOKS = ["Designing Your Second Act", "One Match, One Brick, One Life"]
PROGRAMME = ["Welcome & Networking", "Guests arrived and connected", "Guest Author Talks", "Open questions with all three authors",
             "Conversations and networking", "Event ended"]
# Q11c (D55): unused files Sukant had removed. They must be gone and must not be served.
D55_DELETED = ["images/partner-masud.jpg", "images/elc-logo.png", "ca-book-3d-spine.png", "ca-book-3d.png",
               "ca-cover-mockup.jpg", "elc-logo.png", "mola-fish.png", "partner-masud.jpg"]
PARTNER_WORDS = ["Masud Alam", "Elite Leadership Club", "Community Partner", "partner-masud", "elc-logo", "partner"]
LAUNCH_FILES = re.compile(r"^images/launch/(?:full/)?\d\d\.jpg$|^images/launch/video\.jpg$")
ELSEWHERE = r"^https?://([^/]*\.)?(prechangeway\.com|youtube\.com|youtu\.be|ytimg\.com|googlevideo\.com|youtube-nocookie\.com)(/|$)"
WIDTHS = (390, 1440)

RESULTS = []


def report(ok, req, what, detail=""):
    RESULTS.append((req, bool(ok)))
    print(f"{'PASS' if ok else 'FAIL'}  {req}  {what:<58} {detail}".rstrip())


def die(msg):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(2)


def git(*args):
    return subprocess.run(["git", "-C", REPO_ROOT, *args], check=True, capture_output=True, text=True).stdout


def first(nodes):
    return nodes[0] if nodes else None


def places(root):
    """The three places D49 names: the menu, the home page event section, the footer."""
    def inside(pred):
        return lambda n: n.tag == "a" and any(pred(x) for x in n.ancestors())
    return {
        "menu": root.find_all(inside(lambda x: x.tag == "nav")),
        "home page event section": root.find_all(inside(lambda x: x.tag == "section" and x.attrs.get("id") == "event")),
        "footer": root.find_all(inside(lambda x: x.tag == "footer")),
    }


def clicks(root):
    """GA4 events the page's own click script sends for each link (q06's Node harness)."""
    scripts = [" ".join(c for c in n.children if isinstance(c, str))
               for n in root.find_all(lambda n: n.tag == "script" and "src" not in n.attrs)]
    script = next((s for s in scripts if "register_click" in s), None)
    anchors = q06.anchors(root, "https://changeanesthesiology.com/")
    if script is None:
        return anchors, [[] for _ in anchors]

    def content(n):
        return "".join(c if isinstance(c, str) else content(c) for c in n.children)

    inp = [{"href": a["href"], "text": content(a["node"]),
            "attrs": {k: (v if v is not None else "") for k, v in a["node"].attrs.items()}} for a in anchors]
    r = subprocess.run(["node", "-e", q06.NODE_HARNESS], input=json.dumps({"script": script, "anchors": inp}),
                       capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        die(f"click harness failed: {r.stderr.strip()[:200]}")
    return anchors, [[e["name"] for e in evs] for evs in json.loads(r.stdout)["events"]]


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
    await send('Page.enable'); await send('Network.enable'); await send('Runtime.enable'); await send('Log.enable');
    await send('Network.setBlockedURLs', { urls: ['*googletagmanager.com*', '*google-analytics.com*',
      '*analytics.google.com*', '*cloudflareinsights.com*', '*doubleclick.net*'] });
    let errors = [], requests = [];
    events.push(m => {
      if (m.method === 'Network.requestWillBeSent') requests.push(m.params.request.url);
      if (m.method === 'Runtime.exceptionThrown') errors.push('exception: ' + (m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text));
      if (m.method === 'Runtime.consoleAPICalled' && m.params.type === 'error') errors.push('console: ' + m.params.args.map(a => a.value ?? a.description).join(' '));
      if (m.method === 'Log.entryAdded' && m.params.entry.level === 'error' && !/ERR_BLOCKED_BY_CLIENT/.test(m.params.entry.text)) errors.push('log: ' + m.params.entry.text);
    });
    const out = [];
    for (const c of input.cases) {
      await send('Emulation.setDeviceMetricsOverride', { width: c.width, height: 844, deviceScaleFactor: 1, mobile: c.width < 768 });
      await send('Page.navigate', { url: 'about:blank' }); await sleep(250);
      errors = []; requests = [];
      const loaded = new Promise(r => events.push(function f(m) {
        if (m.method === 'Page.loadEventFired') { events.splice(events.indexOf(f), 1); r(); } }));
      await send('Emulation.setScriptExecutionDisabled', { value: !!c.noJs });
      await send('Page.navigate', { url: c.url }); await loaded;
      await sleep(1500);
      if (c.noJs) {
        const doc = await send('DOM.getDocument', { depth: -1 });
        const html = (await send('DOM.getOuterHTML', { nodeId: doc.root.nodeId })).outerHTML;
        out.push({ name: c.name, over: 0, value: html, errors: [...errors], requests: [...requests] });
        continue;
      }
      if (c.pre) { await send('Runtime.evaluate', { expression: c.pre }); await sleep(1500); }
      const over = (await send('Runtime.evaluate', { returnByValue: true,
        expression: 'document.documentElement.scrollWidth - document.documentElement.clientWidth' })).result.value;
      const value = c.expr ? (await send('Runtime.evaluate', { returnByValue: true, expression: c.expr })).result.value : null;
      out.push({ name: c.name, over, value, errors: [...errors], requests: [...requests] });
    }
    console.log(JSON.stringify(out)); ws.close();
  } finally { chrome.kill(); }
})().catch(e => { console.error(e.message); process.exit(1); });
"""


def browser(cases):
    if not os.path.exists(q06.CHROME):
        die(f"Chrome not found at {q06.CHROME} (set CHROME)")
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    profile = tempfile.mkdtemp(prefix="check-events-links-")
    try:
        r = subprocess.run(["node", "-e", BROWSER], capture_output=True, text=True, timeout=300,
                           input=json.dumps({"chrome": q06.CHROME, "port": port, "profile": profile, "cases": cases}))
    finally:
        time.sleep(0.5)
        shutil.rmtree(profile, ignore_errors=True)
    if r.returncode != 0:
        die(f"browser check failed to run: {r.stderr.strip()[:300]}")
    return json.loads(r.stdout)


def expected(path, old):
    for f, before, after in APPROVED_EDITS:
        if f == path:
            if old.count(before) != 1:
                return None
            old = old.replace(before, after)
    return old


def changes(path, old, new):
    """Every way the served file differs from BASE_REF plus the approved edits; [] if none."""
    want = expected(path, old)
    if want is None:
        return ["an approved edit no longer applies"]
    if new == want:
        return []
    w, n = want.split("\n"), new.split("\n")
    k = next((i for i, (a, b) in enumerate(zip(w, n)) if a != b), min(len(w), len(n)))
    return [f"line {k + 1} differs: {(n[k] if k < len(n) else '(end of file)').strip()[:60]!r}"]


PLANTED = {
    "label changed": lambda h: h.replace(f">{LABEL}</a>", ">Events</a>", 1),
    "photos link moved": lambda h: h.replace(PHOTOS_URL, EVENTS_URL + "#gallery", 1),
    "script calling prechangeway.com": lambda h: h.replace("</body>", "<script>fetch('https://prechangeway.com/events.json')</script></body>", 1),
    "events feed spot added": lambda h: h.replace("</footer>", "<!-- events-feed:upcoming --></footer>", 1),
}


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": q06.UA, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.headers.get("Content-Type", ""), r.read()
    except urllib.error.HTTPError as e:
        return e.code, "", b""


def jpeg_info(b):
    """((width, height), file-detail segments) of a JPEG; only a plain JFIF header may remain."""
    if b[:2] != b"\xff\xd8":
        return None, ["not a JPEG"]
    i, size, extra = 2, None, []
    while i + 4 <= len(b) and b[i] == 0xFF:
        m = b[i + 1]
        if m == 0xFF:
            i += 1
            continue
        if m == 0xDA:
            break
        if 0xD0 <= m <= 0xD7 or m == 0x01:
            i += 2
            continue
        ln = int.from_bytes(b[i + 2:i + 4], "big")
        if (0xE0 <= m <= 0xEF and not (m == 0xE0 and b[i + 4:i + 9] == b"JFIF\0")) or m == 0xFE:
            extra.append("COM" if m == 0xFE else f"APP{m - 0xE0}")
        if 0xC0 <= m <= 0xCF and m not in (0xC4, 0xC8, 0xCC):
            size = (int.from_bytes(b[i + 7:i + 9], "big"), int.from_bytes(b[i + 5:i + 7], "big"))
        i += 2 + ln
    return size, extra


def check_launch(base, root):
    """Q11 (D50): the launch section as a past event, with its photos and video."""
    band = first(root.find_all(lambda n: n.tag == "section" and n.attrs.get("id") == "event"))
    tag = first(band.find_all(lambda n: "tag" in n.classes())) if band else None
    head = first(band.find_all(lambda n: n.tag == "h2")) if band else None
    got = (text(tag) if tag else "", text(head) if head else "")
    report(got == ("Past event", "How the book launched."), "LP-01", "Section reads as a past event", " / ".join(got))

    photos = root.find_all(lambda n: n.tag == "ul" and n.attrs.get("id") == "lp-photos")
    items = photos[0].find_all(lambda n: n.tag == "li") if photos else []
    rows = []
    for li in items:
        a, img = first(li.find_all(lambda n: n.tag == "a")), first(li.find_all(lambda n: n.tag == "img"))
        rows.append((a.attrs.get("href") if a else None, img.attrs if img else {}))
    want_src = [f"images/launch/{i:02d}.jpg" for i in range(1, 13)]
    ok = (len(rows) == 12 and [r[1].get("src") for r in rows] == want_src
          and [r[0] for r in rows] == [f"images/launch/full/{i:02d}.jpg" for i in range(1, 13)]
          and [r[1].get("alt") for r in rows] == LAUNCH_ALTS
          and all(r[1].get("width") and r[1].get("height") and r[1].get("loading") == "lazy" for r in rows))
    report(ok and band and any(x is band for x in photos[0].ancestors()), "LP-02",
           "12 photos in album order: width, height, lazy, alt, full-size link", f"{len(rows)} photos")
    files = want_src + [f"images/launch/full/{i:02d}.jpg" for i in range(1, 13)] + ["images/launch/video.jpg"]
    bad_size, details, not_served = [], [], []
    for f in files:
        code, ctype, body = get(f"{base}/{f}")
        if code != 200 or not ctype.startswith("image/jpeg"):
            not_served.append(f"{f} {code}")
            continue
        size, extra = jpeg_info(body)
        limit = 1000 if "/full/" in f else 800
        if not size or max(size) > limit:
            bad_size.append(f"{f} {size}")
        details += [f"{f}: {e}" for e in extra]
    report(not not_served, "LP-02", f"All {len(files)} images served from this site", ", ".join(not_served[:3]) or "ok")
    report(not bad_size, "LP-02", "Page copies at most 800 px, full size at most 1,000 px", ", ".join(bad_size[:3]) or "ok")
    report(not details, "LP-06", "No file details (EXIF, GPS, colour profile, comments) in any copy",
           ", ".join(details[:3]) or "ok")
    report(all(not (r[1].get("src") or "").startswith(("http:", "https:", "//")) for r in rows), "LP-06",
           "Every photo is served from this site, none hotlinked")

    video = root.find_all(lambda n: n.tag == "ul" and "lp-videos" in n.classes())
    links = video[0].find_all(lambda n: n.tag == "a") if video else []
    vimg = first(video[0].find_all(lambda n: n.tag == "img")) if video else None
    report(len(links) == 1 and links[0].attrs.get("href") == VIDEO_URL and links[0].attrs.get("target") == "_blank"
           and "Watch on YouTube ↗" in text(links[0]) and vimg is not None
           and vimg.attrs.get("src") == "images/launch/video.jpg" and vimg.attrs.get("alt") == "Video: Change Anesthesiology",
           "LP-03", "Video: local thumbnail, 'Watch on YouTube ↗' in a new tab",
           links[0].attrs.get("href") if links else "missing")
    embeds = [n.tag for n in root.walk() if n.tag in ("iframe", "embed", "object", "video")]
    report(not embeds, "LP-03", "No embedded player or YouTube code", ", ".join(embeds) or "ok")

    anchors, fired = clicks(root)
    media = [(a["href"], evs) for a, evs in zip(anchors, fired)
             if a["href"].startswith((base + "/images/launch/", "https://changeanesthesiology.com/images/launch/")) or a["href"] == VIDEO_URL]
    report(len(media) == 13 and not any("register_click" in evs for _, evs in media), "LP-05",
           "Photo and video links are not register_click", f"{len(media)} links checked")

    expr = ("(() => { const l = document.getElementById('lp-photos'), b = document.querySelector('.lp-more button');"
            " return { shown: [...l.children].filter(li => getComputedStyle(li).display !== 'none').length,"
            " button: b ? b.textContent : null, expanded: b ? b.getAttribute('aria-expanded') : null }; })()")
    click = "document.querySelector('.lp-more button').click()"
    res = {x["name"]: x for x in browser([
        {"name": "closed", "url": base + "/", "width": 1440, "expr": expr},
        {"name": "opened", "url": base + "/", "width": 1440, "pre": click, "expr": expr},
        {"name": "closed again", "url": base + "/", "width": 390, "pre": click + ";" + click, "expr": expr},
        {"name": "no script", "url": base + "/", "width": 390, "noJs": True}])}
    c, o, again = res["closed"]["value"], res["opened"]["value"], res["closed again"]["value"]
    report(c == {"shown": 6, "button": "Show more photos", "expanded": "false"}, "LP-04", "6 photos shown, 'Show more photos'", str(c))
    report(o == {"shown": 12, "button": "Show fewer photos", "expanded": "true"}, "LP-04", "Opened: all 12, 'Show fewer photos'", str(o))
    report(again == {"shown": 6, "button": "Show more photos", "expanded": "false"}, "LP-04", "Closes again to 6", str(again))
    nojs = parse(res["no script"]["value"] or "")
    lst = first(nojs.find_all(lambda n: n.attrs.get("id") == "lp-photos"))
    report(lst is not None and "lp-folded" not in lst.classes() and len(lst.find_all(lambda n: n.tag == "li")) == 12
           and not nojs.find_all(lambda n: "lp-more" in n.classes()), "LP-04", "Without the script, all 12 photos show")


def check_review(base, root):
    """Q11b (D51 to D54): the launch section after Sukant's review."""
    band = first(root.find_all(lambda n: n.tag == "section" and n.attrs.get("id") == "event"))
    if band is None:
        report(False, "LB-01", "Launch section found", "missing")
        return
    names = [text(n) for n in band.find_all(lambda n: "spk-name" in n.classes())]
    books = [text(n) for n in band.find_all(lambda n: "spk-book" in n.classes())]
    guests = [t for t in band.find_all(lambda n: "tag" in n.classes()) if text(t) == "Featured Guest Authors"]
    report(names == SPEAKERS and all(b in books for b in GUEST_BOOKS) and guests, "LB-01",
           "Speaker cards kept: the author, Tammy Martins and Ryan Myers", ", ".join(names))
    html = q06.fetch(base + "/")
    words = text(band)
    found = [w for w in PARTNER_WORDS if w.lower() in (words + " " + html[html.find('id="event"'):html.find("</section>", html.find('id="event"'))]).lower()]
    cards = band.find_all(lambda n: any(c.startswith("partner") for c in n.classes()))
    report(not found and not cards, "LB-02", "No community partner card or credit in the section", ", ".join(found) or "ok")
    report("Masud Alam" not in html and "partner-masud" not in html and "elc-logo" not in html, "LB-02",
           "No partner name, photo or logo anywhere on the home page")
    prog = band.find_all(lambda n: any(c in ("prog", "prog-row") for c in n.classes()))
    left = [w for w in PROGRAMME if w in words]
    report(not prog and not left, "LB-03", "Programme removed", ", ".join(left) or "ok")
    when = (text(first(band.find_all(lambda n: "event-date" in n.classes())) or band),
            text(first(band.find_all(lambda n: "event-time" in n.classes())) or band),
            text(first(band.find_all(lambda n: "event-place" in n.classes())) or band))
    report(when == WHEN, "LB-03", "Date, time and place kept", " | ".join(when)[:90])
    hl = band.find_all(lambda n: "event-hl" in n.classes())
    em = hl[0].find_all(lambda n: n.tag == "em") if hl else []
    line = re.sub(r"\s+([,.;:!?])", r"\1", text(hl[0])) if hl else ""  # text() spaces out inline tags
    report(len(hl) == 1 and line == HIGHLIGHT and len(em) == 1 and text(em[0]) == HIGHLIGHT_TITLE, "LB-04",
           "Highlight line word for word, book title in italics", line[:80] or "missing")
    kept = {"'Next events' label": "Next events", "'Online and in person · on prechangeway.com'": "Online and in person · on prechangeway.com"}
    for what, w in kept.items():
        report(w in words, "LB-05", f"Kept: {what}")


def check_cleanup(base):
    """Q11c (D55): the unused files are gone, and nothing on either page is broken."""
    tracked = set(git("ls-files").split("\n"))
    for f in D55_DELETED:
        code = get(f"{base}/{f}")[0]
        report(f not in tracked and code == 404, "LC-01", f"/{f} removed and not served", f"got {code}")
    for name, path in (("index", "/"), ("article", "/article")):
        page = parse(q06.fetch(base + path))
        refs = set()
        for n in page.walk():
            if n.tag in ("img", "source") and n.attrs.get("src"):
                refs.add(n.attrs["src"])
            if n.tag == "link" and "icon" in (n.attrs.get("rel") or "") and n.attrs.get("href"):
                refs.add(n.attrs["href"])
            if n.tag == "meta" and (n.attrs.get("property") or n.attrs.get("name") or "").endswith(":image"):
                refs.add(re.sub(r"^https://changeanesthesiology\.com/", "", n.attrs.get("content") or ""))
        bad = []
        for ref in sorted(refs):
            if ref.startswith(("http:", "https:", "//", "data:")):
                continue
            code, ctype, _ = get(f"{base}/{ref.lstrip('/')}")
            if code != 200 or not ctype.startswith("image/"):
                bad.append(f"{ref} {code}")
        report(not bad, "LC-02", f"{name}: every image, icon and share image is served", ", ".join(bad[:3]) or f"{len(refs)} files")
    expr = "[...document.images].filter(i => !(i.complete && i.naturalWidth > 0)).map(i => i.getAttribute('src'))"
    eager = "document.querySelectorAll('img').forEach(i => { i.loading = 'eager'; }); document.querySelector('.lp-more button') && document.querySelector('.lp-more button').click()"
    for x in browser([{"name": f"{p} {w}px", "url": base + p, "width": w, "pre": eager, "expr": expr}
                      for p in ("/", "/article") for w in WIDTHS]):
        report(x["value"] == [], "LC-02", f"{x['name']}: no broken image", ", ".join(x["value"] or [])[:80] or "ok")


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

    # EL-01: "Upcoming Events" in the menu, the home page event section and the footer.
    for where, links in places(root).items():
        hits = [a for a in links if a.attrs.get("href") == EVENTS_URL and text(a) == LABEL]
        report(len(hits) == 1 and hits[0].attrs.get("target") == "_blank", "EL-01",
               f"{where}: '{LABEL}' -> {EVENTS_URL}", f"{len(hits)} found")
    print()

    # EL-02: the launch photos link.
    photos = [a for a in root.find_all(lambda n: n.tag == "a") if a.attrs.get("href") == PHOTOS_URL]
    in_event = [a for a in photos if any(x.attrs.get("id") == "event" for x in a.ancestors())]
    report(len(photos) == 1 and in_event and text(in_event[0]) == PHOTOS_TEXT, "EL-02",
           "Launch photos link -> /events#spotlight-change-anesthesiology-2026-08",
           ", ".join(f"'{text(a)}'" for a in photos) or "missing")
    print()

    # EL-03: GA4. "Upcoming Events" links count as register_click; photo links do not.
    anchors, fired = clicks(root)
    reg = {id(a["node"]) for a, evs in zip(anchors, fired) if "register_click" in evs}
    for where, links in places(root).items():
        hits = [a for a in links if a.attrs.get("href") == EVENTS_URL]
        report(hits and all(id(a) in reg for a in hits), "EL-03", f"{where}: '{LABEL}' counts as register_click")
    not_reg = [a["text"] for a, evs in zip(anchors, fired) if a["href"] == PHOTOS_URL and "register_click" in evs]
    report(photos and not not_reg, "EL-03", "Photos link is not register_click", ", ".join(not_reg) or "ok")
    print()

    # EL-04: nothing else changed against main, and nothing from Q09 is here.
    try:
        changed = [f for f in git("diff", "--name-only", BASE_REF, "HEAD").split("\n") if f]
        dirty = git("status", "--porcelain", "--untracked-files=no").strip()
        old_index, old_article = git("show", f"{BASE_REF}:index.html"), git("show", f"{BASE_REF}:article.html")
        tracked = git("ls-files").split("\n")
    except subprocess.CalledProcessError as e:
        die(f"git failed: {e.stderr.strip()}")
    allowed = {"tests/"} | {f for f, _, _ in APPROVED_EDITS}
    extra = [f for f in changed if not (LAUNCH_FILES.match(f) or f in D55_DELETED
                                        or any(f == a or (a.endswith("/") and f.startswith(a)) for a in allowed))]
    report(not extra, "EL-04", f"Checkout: only index.html, images/launch/, D55 deletions, tests/ since {BASE_REF}",
           ", ".join(extra) or f"{len(changed)} files")
    report(not dirty, "EL-04", "Checkout: no uncommitted changes to tracked files", dirty.replace("\n", ", ")[:80] or "clean")
    q09 = [f for f in tracked if f.startswith(Q09_FILES)]
    report(not q09, "EL-04", "Nothing from Q09 (script, workflow, data, event photos)", ", ".join(q09[:3]) or "none")
    for path, old, new in (("index.html", old_index, index), ("article.html", old_article, article)):
        probs = changes(path, old, new)
        report(not probs, "EL-04", f"{path}: exactly as in {BASE_REF}", "; ".join(probs) or "ok")
    missed = [k for k, plant in PLANTED.items() if plant(index) == index or not changes("index.html", old_index, plant(index))]
    report(not missed, "EL-04", f"Self-test: all {len(PLANTED)} planted edits are caught", ", ".join(missed) or "ok")
    print()

    # EL-05: nothing reads or calls prechangeway.com.
    for name, html in (("index", index), ("article", article)):
        page = parse(html)
        src = [n.attrs.get("src") or n.attrs.get("href") for n in page.walk()
               if n.tag in ("script", "img", "link", "iframe", "source", "video", "audio", "object", "embed")
               and "prechangeway" in (n.attrs.get("src") or n.attrs.get("href") or "")]
        scripts = " ".join(" ".join(c for c in n.children if isinstance(c, str))
                           for n in page.find_all(lambda n: n.tag == "script"))
        src += [n.attrs.get("src") or n.attrs.get("href") for n in page.walk()
                if n.tag in ("script", "img", "link", "iframe", "source", "video", "audio", "object", "embed")
                and re.search(r"youtube|youtu\.be|ytimg", n.attrs.get("src") or n.attrs.get("href") or "")]
        calls = re.findall(r"(?:fetch|open|sendBeacon|EventSource|WebSocket)\(\s*['\"][^'\"]*(?:prechangeway|youtu)[^'\"]*['\"]", scripts)
        report(not src and not calls, "EL-05", f"{name}: no script, image or call to prechangeway.com or YouTube",
               ", ".join(src + calls)[:80] or "ok")
    more = "document.querySelector('.lp-more button') && document.querySelector('.lp-more button').click()"
    eager = "document.querySelectorAll('img').forEach(i => { i.loading = 'eager'; });" + more
    cases = [{"name": f"{p} {w}px", "url": base + p, "width": w} for p in ("/", "/article") for w in WIDTHS]
    cases += [{"name": f"/ {w}px, all photos opened", "url": base + "/", "width": w, "pre": eager} for w in WIDTHS]
    for x in browser(cases):
        pre = [u for u in x["requests"] if re.match(ELSEWHERE, u)]
        report(not pre and not x["errors"] and x["over"] <= 0, "EL-05",
               f"{x['name']}: zero requests to prechangeway.com or YouTube, no errors",
               ", ".join(pre + x["errors"])[:70] or f"{len(x['requests'])} requests, {x['over']} px sideways")
    print()

    check_launch(base, root)
    print()
    check_review(base, root)
    print()
    check_cleanup(base)
    print()

    # EL-06: the earlier suites.
    for label, cmd, skip in (
            ("Q04 test: every check passes", ["bash", os.path.join(TESTS, "check_public_files.sh"), base], ()),
            ("Q06 test: every check but PR-04 passes", [sys.executable, os.path.join(TESTS, "check_price_and_events.py"), base], ("PR-04",)),
            ("Q08 test: every check passes (TL-05 replaced)", [sys.executable, os.path.join(TESTS, "check_three_layers.py"), base], ())):
        r, lines, err = run_suite(cmd)
        if r is None or not lines:
            report(False, "EL-06", label, (err or "no output")[:80])
            continue
        fails = [l for l in lines if l.startswith("FAIL") and l.split()[1] not in skip]
        skipped = sum(1 for l in lines if l.split()[1] in skip)
        report(not fails and r.returncode in ((0, 1) if skip else (0,)), "EL-06", label,
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
