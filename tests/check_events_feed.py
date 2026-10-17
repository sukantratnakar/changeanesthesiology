#!/usr/bin/env python3
"""Checks the events taken from prechangeway.com's feed (EF-01 to EF-08).

Q09, 16 Oct 2026. Decisions D35 to D37, D40 to D45, D47 and Q09-7.

Usage:  python3 tests/check_events_feed.py <base-url>
  e.g.  python3 tests/check_events_feed.py https://content-events-feed-changeanesthesiology.sukantratnakar.workers.dev

Part 1 runs scripts/events-feed.mjs on the fixtures in tests/fixtures/events, in throwaway
copies of the site, with a fixed clock and no network (EF-01 to EF-06), then opens the result
in headless Chrome (EF-07, the "Your time" line, GA4 clicks).
Part 2 checks the site served at <base-url>: the page is BASE_REF (default 27cf1c4, main after
Q08) plus exactly Q09's code, the marked spots hold nothing invented while data/events.json is
absent (D42), nothing calls prechangeway.com, and the Q04, Q06 and Q08 tests pass (Q06's PR-04
lines excepted; Q08's TL-05 is replaced by EF-08, D43).
Prints one PASS/FAIL line per check. Exits 1 if any check fails, 2 if the test can't run.
Fetches pages with urllib (Accept */*, own User-Agent); browser checks block analytics.
Node and Chrome must be installed.
"""

import copy
import hashlib
import http.server
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from difflib import SequenceMatcher

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_price_and_events as q06  # noqa: E402  (shared parser, fetch and Chrome path)

from check_price_and_events import norm, parse, text  # noqa: E402

q06.UA = "check_events_feed.py (changeanesthesiology repo test)"
TESTS = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TESTS)
SCRIPT = os.path.join(REPO_ROOT, "scripts", "events-feed.mjs")
WORKFLOW = os.path.join(REPO_ROOT, ".github", "workflows", "events-feed.yml")
FIX = os.path.join(TESTS, "fixtures", "events")
FEED = os.path.join(FIX, "feed-valid.json")
MIRROR = os.path.join(FIX, "mirror")
BASE_REF = os.environ.get("BASE_REF", "27cf1c4")
LAUNCH = "spotlight-change-anesthesiology-2026-08"
EVENTS_URL = "https://prechangeway.com/events"
NOW = "2026-10-16T18:00:00-06:00"
WIDTHS = (360, 390, 820, 1440)
MARKERS = {"upcoming": ("<!-- events-feed:upcoming -->", "<!-- /events-feed:upcoming -->"),
           "gallery": ("<!-- events-feed:gallery -->", "<!-- /events-feed:gallery -->")}

# EF-03 with the fixture feed and the clock at NOW: next two per series, in date order.
UPCOMING_AT_NOW = [
    ("#live-online-2026-11", "Tuesday 17 November 2026 · 11:00 am – 12:30 pm Saskatchewan time",
     "FIXTURE · Prechange Live · Online", "Online →", True),
    ("#live-saskatoon-2026-11", "Wednesday 25 November 2026 · 4:00 pm – 5:30 pm Saskatchewan time",
     "FIXTURE · Prechange Live · Saskatoon", "Saskatoon →", False),
    ("#spotlight-fixture-2026-12", "Thursday 3 December 2026 · 6:00 pm – 7:30 pm Saskatchewan time",
     "FIXTURE · Prechange Spotlight · Saskatoon", "Saskatoon →", False),
    ("#spotlight-fixture-2027-02", "Wednesday 10 February 2027 · 11:00 am – 12:00 pm Saskatchewan time",
     "FIXTURE · Prechange Spotlight · Online", "Online →", True),
]
# After 17 November: Live moves on to Saskatoon and Regina (month only, no time).
UPCOMING_LATER = ["Wednesday 25 November 2026 · 4:00 pm – 5:30 pm Saskatchewan time",
                  "Thursday 3 December 2026 · 6:00 pm – 7:30 pm Saskatchewan time",
                  "January 2027",
                  "Wednesday 10 February 2027 · 11:00 am – 12:00 pm Saskatchewan time"]

# EF-08: Q09's code edits to BASE_REF's index.html, word for word. Apart from these, the page
# must be the same, plus one CSS block added whole before "reveal" and whatever the feed
# writes between the markers.
CSS_START, CSS_END = "/* ── events feed: filled from prechangeway.com by scripts/events-feed.mjs ── */", "/* ── reveal ── */"
CSS_PREFIXES = (".feed-", ".event-top:has(.feed-up)")
BUTTON = ('<a href="https://prechangeway.com/events" target="_blank" class="btn btn-gold" '
          'style="font-size:.82rem;padding:1rem 2.4rem">Upcoming Events</a>\n')
PARTNER = '<img src="images/elc-logo.png" alt="Elite Leadership Club of Canada" class="partner-mark">\n    </div>\n'
GA_BEFORE = "}else if(a.href==='https://prechangeway.com/events'){"
GA_AFTER = "}else if(a.href==='https://prechangeway.com/events'||a.hasAttribute('data-register-click')){"
LOCAL_TIME_SCRIPT = r'''<script>
/* "Your time" for online events (Q09, D45): converted in the visitor's browser, with no network
   calls, cookies or storage. Hidden where the clock already reads UTC-6 on that date. */
(function(){
  var parts=function(d,o,l){var r={};new Intl.DateTimeFormat(l||'en-GB',o).formatToParts(d).forEach(function(p){r[p.type]=p.value});return r};
  var clock=function(d){var p=parts(d,{hour:'numeric',minute:'2-digit',hour12:true},'en-US');return p.hour+':'+p.minute+' '+String(p.dayPeriod).toLowerCase()};
  var day=function(d,z){var p=parts(d,{weekday:'long',day:'numeric',month:'long',timeZone:z});return p.weekday+' '+p.day+' '+p.month};
  document.querySelectorAll('[data-local-start]').forEach(function(el){
    try{
      var s=new Date(el.getAttribute('data-local-start')),e=new Date(el.getAttribute('data-local-end'));
      if(isNaN(s)||isNaN(e)||s.getTimezoneOffset()===360)return;
      var zone=parts(s,{hour:'numeric',timeZoneName:'short'},'en-US').timeZoneName||'';
      var here=day(s);
      el.textContent='Your time: '+(here!==day(s,'America/Regina')?here+', ':'')+clock(s)+' \u2013 '+clock(e)+(zone?' '+zone:'');
      el.hidden=false;
    }catch(_){}
  });
})();
</script>'''
APPROVED_EDITS = [
    (BUTTON, BUTTON + "        <!-- events-feed:upcoming -->\n        <!-- /events-feed:upcoming -->\n"),
    (PARTNER, PARTNER + "    <!-- events-feed:gallery -->\n    <!-- /events-feed:gallery -->\n"),
    (GA_BEFORE, GA_AFTER),
    ("</body>", LOCAL_TIME_SCRIPT + "\n</body>"),
]
ALLOWED_FILES = re.compile(r"^(index\.html|\.assetsignore|scripts/events-feed\.mjs|\.github/workflows/events-feed\.yml"
                           r"|data/events\.json|images/events/[^/]+/\d\d\.(?:jpg|png|webp)|tests/.+)$")

# --- helpers ---------------------------------------------------------------------------------

RESULTS = []


def report(ok, req, what, detail=""):
    RESULTS.append((req, bool(ok)))
    print(f"{'PASS' if ok else 'FAIL'}  {req}  {what:<58} {detail}".rstrip())


def die(msg):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(2)


def git(*args):
    return subprocess.run(["git", "-C", REPO_ROOT, *args], check=True, capture_output=True, text=True).stdout


def status(url):
    req = urllib.request.Request(url, headers={"User-Agent": q06.UA, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def first(root, pred):
    found = root.find_all(pred)
    return found[0] if found else None


def has_class(*names):
    return lambda n: all(c in n.classes() for c in names)


def new_site(full=False):
    """A throwaway copy of the site: the page only, or (full) every visitor file for Chrome."""
    root = tempfile.mkdtemp(prefix="events-feed-test-")
    shutil.copy(os.path.join(REPO_ROOT, "index.html"), root)
    os.makedirs(os.path.join(root, "images"))
    if full:
        for f in git("ls-files").split("\n"):
            if f and not f.startswith(("tests/", "scripts/", ".", "data/", "images/events/")) and f != "wrangler.jsonc":
                os.makedirs(os.path.dirname(os.path.join(root, f)) or root, exist_ok=True)
                shutil.copy(os.path.join(REPO_ROOT, f), os.path.join(root, f))
    return root


def run_script(root, feed=None, now=NOW, **env):
    e = {**os.environ, "REPO_ROOT": root, "PRECHANGE_MIRROR": MIRROR, "NOW": now}
    e.pop("FEED_URL", None)
    if feed is not None:
        e["FEED_FILE"] = feed
    e.update(env)
    return subprocess.run(["node", SCRIPT], env=e, capture_output=True, text=True, timeout=120)


def snapshot(root):
    out = {}
    for base, _, files in os.walk(root):
        for f in files:
            p = os.path.join(base, f)
            rel = os.path.relpath(p, root)
            if rel == "index.html" or rel.startswith(("data", os.path.join("images", "events"))):
                out[rel] = hashlib.sha256(open(p, "rb").read()).hexdigest()
    return out


def write_feed(feed, folder):
    path = os.path.join(folder, f"feed-{len(os.listdir(folder))}.json")
    with open(path, "w", encoding="utf-8") as f:
        f.write(feed if isinstance(feed, str) else json.dumps(feed))
    return path


def page_of(root):
    return parse(open(os.path.join(root, "index.html"), encoding="utf-8").read())


def upcoming(root_node):
    out = []
    for li in root_node.find_all(lambda n: n.tag == "li" and any("feed-up" in a.classes() for a in n.ancestors())):
        a = first(li, lambda n: n.tag == "a")
        local = first(li, has_class("feed-local"))
        out.append({"href": a.attrs.get("href") if a else None, "attrs": a.attrs if a else {},
                    "when": text(first(li, has_class("feed-when")) or li),
                    "title": text(first(li, has_class("feed-title")) or li),
                    "city": text(first(li, has_class("feed-city")) or li), "local": local})
    return out


def image_info(b):
    """(type, (width, height), file-detail parts still inside) for JPEG, PNG and WebP."""
    if b[:2] == b"\xff\xd8":
        i, size, meta = 2, None, []
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
            if 0xE0 <= m <= 0xEF:
                meta.append(f"APP{m - 0xE0}")
            if m == 0xFE:
                meta.append("COM")
            if 0xC0 <= m <= 0xCF and m not in (0xC4, 0xC8, 0xCC):
                size = (int.from_bytes(b[i + 7:i + 9], "big"), int.from_bytes(b[i + 5:i + 7], "big"))
            i += 2 + ln
        return "jpg", size, meta
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        i, size, meta = 8, None, []
        while i + 12 <= len(b):
            ln, kind = int.from_bytes(b[i:i + 4], "big"), b[i + 4:i + 8].decode("latin1")
            if kind == "IHDR":
                size = (int.from_bytes(b[i + 8:i + 12], "big"), int.from_bytes(b[i + 12:i + 16], "big"))
            if kind in ("tEXt", "iTXt", "zTXt", "eXIf", "tIME", "iCCP"):
                meta.append(kind)
            i += 12 + ln
        return "png", size, meta
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        i, size, meta = 12, None, []
        while i + 8 <= len(b):
            kind, ln = b[i:i + 4].decode("latin1"), int.from_bytes(b[i + 4:i + 8], "little")
            d = i + 8
            if kind == "VP8X":
                size = (1 + int.from_bytes(b[d + 4:d + 7], "little"), 1 + int.from_bytes(b[d + 7:d + 10], "little"))
            elif kind == "VP8 " and size is None:
                size = (int.from_bytes(b[d + 6:d + 8], "little") & 0x3FFF, int.from_bytes(b[d + 8:d + 10], "little") & 0x3FFF)
            elif kind == "VP8L" and size is None:
                v = int.from_bytes(b[d + 1:d + 5], "little")
                size = ((v & 0x3FFF) + 1, ((v >> 14) & 0x3FFF) + 1)
            if kind in ("EXIF", "XMP ", "ICCP"):
                meta.append(kind.strip())
            i += 8 + ln + (ln & 1)
        return "webp", size, meta
    return None, None, []


# --- Chrome -------------------------------------------------------------------------------------

BROWSER_HARNESS = r"""
const { spawn } = require('child_process');
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const chrome = spawn(input.chrome, ['--headless=new', '--disable-gpu', '--hide-scrollbars', '--no-first-run',
    '--allow-file-access-from-files', `--user-data-dir=${input.profile}`, `--remote-debugging-port=${input.port}`,
    'about:blank'], { stdio: 'ignore' });
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
      if (m.method === 'Log.entryAdded' && m.params.entry.level === 'error' && !/ERR_BLOCKED_BY_CLIENT/.test(m.params.entry.text)) errors.push('log: ' + m.params.entry.text + ' ' + (m.params.entry.url || ''));
    });
    const out = [];
    for (const c of input.cases) {
      await send('Emulation.setScriptExecutionDisabled', { value: !!c.noJs });
      try { await send('Emulation.setTimezoneOverride', { timezoneId: '' }); } catch {}
      await send('Emulation.setTimezoneOverride', { timezoneId: c.tz || 'America/Regina' });
      await send('Emulation.setDeviceMetricsOverride', { width: c.width, height: 844, deviceScaleFactor: 1, mobile: c.width < 768 });
      await send('Page.navigate', { url: 'about:blank' }); await sleep(250);
      errors = []; requests = [];
      const loaded = new Promise(r => events.push(function f(m) {
        if (m.method === 'Page.loadEventFired') { events.splice(events.indexOf(f), 1); r(); } }));
      await send('Page.navigate', { url: c.url }); await loaded;
      await sleep(700);
      let value = null;
      if (c.noJs) {
        const doc = await send('DOM.getDocument', { depth: -1 });
        value = (await send('DOM.getOuterHTML', { nodeId: doc.root.nodeId })).outerHTML;
      } else {
        await send('Runtime.evaluate', { expression: 'document.fonts.ready.then(() => 1)', awaitPromise: true });
        value = (await send('Runtime.evaluate', { returnByValue: true, expression: c.expr })).result.value;
      }
      out.push({ name: c.name, value, errors: [...errors], requests: [...requests] });
    }
    console.log(JSON.stringify(out)); ws.close();
  } finally { chrome.kill(); }
})().catch(e => { console.error(e.message); process.exit(1); });
"""

LAYOUT_EXPR = """(() => { const d = document.documentElement;
  return { over: d.scrollWidth - d.clientWidth,
    upcoming: document.querySelectorAll('.feed-up li').length,
    photos: [...document.querySelectorAll('.feed-photos img')].map(i => [i.getAttribute('width'), i.getAttribute('height'), i.getAttribute('loading')]) }; })()"""
LOCAL_EXPR = """[...document.querySelectorAll('.feed-up li')].map(li => { const l = li.querySelector('.feed-local');
  return { title: li.querySelector('.feed-title').textContent, when: li.querySelector('.feed-when').textContent,
           local: l ? { hidden: l.hidden, shown: getComputedStyle(l).display !== 'none', text: l.textContent } : null }; })"""


def browser(cases):
    if not os.path.exists(q06.CHROME):
        die(f"Chrome not found at {q06.CHROME} (set CHROME)")
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    profile = tempfile.mkdtemp(prefix="check-events-feed-")
    try:
        r = subprocess.run(["node", "-e", BROWSER_HARNESS], capture_output=True, text=True, timeout=600,
                           input=json.dumps({"chrome": q06.CHROME, "port": port, "profile": profile, "cases": cases}))
    finally:
        time.sleep(0.5)
        shutil.rmtree(profile, ignore_errors=True)
    if r.returncode != 0:
        die(f"browser check failed to run: {r.stderr.strip()[:300]}")
    return {x["name"]: x for x in json.loads(r.stdout)}


def prechange_requests(requests):
    return [u for u in requests if re.match(r"^https?://([^/]*\.)?prechangeway\.com(/|$)", u)]


# --- Part 1: the script on fixtures (EF-01 to EF-06) -----------------------------------------------

def check_script():
    valid = json.load(open(FEED, encoding="utf-8"))
    work = tempfile.mkdtemp(prefix="events-feed-feeds-")
    site = new_site()
    r = run_script(site, FEED)
    report(r.returncode == 0, "EF-01", "Script builds the page from a valid feed", (r.stdout or r.stderr).strip()[:80])
    html = open(os.path.join(site, "index.html"), encoding="utf-8").read()
    root = parse(html)
    orig = open(os.path.join(REPO_ROOT, "index.html"), encoding="utf-8").read()
    blank = lambda h: re.sub(r"(<!-- events-feed:(\w+) -->).*?(\n[ \t]*<!-- /events-feed:\2 -->)", r"\1\3", h, flags=re.S)  # noqa: E731
    report(blank(html) == blank(orig), "EF-01", "Only the two marked spots change")
    inner = "".join(re.findall(r"<!-- events-feed:\w+ -->(.*?)<!-- /events-feed:\w+ -->", html, flags=re.S))
    report("<script" not in inner and "style=" not in inner, "EF-01", "Plain HTML: no script or inline style in the spots")
    again = snapshot(site)
    r2 = run_script(site, FEED)
    report(r2.returncode == 0 and snapshot(site) == again, "EF-01", "A second run with the same feed changes nothing")
    gen = copy.deepcopy(valid)
    gen["generated"] = "2026-10-17T05:00:00-06:00"
    r3 = run_script(site, write_feed(gen, work))
    report(r3.returncode == 0 and snapshot(site) == again, "EF-01", "A new 'generated' time alone changes nothing")

    # EF-02: the launch gallery.
    launch = next(p for p in valid["past"] if p["id"] == LAUNCH)
    gal = first(root, has_class("feed-gallery"))
    report(gal is not None and any(x.attrs.get("id") == "event" for x in gal.ancestors()), "EF-02",
           "Gallery sits inside the launch section (#event)")
    hl = text(first(gal, has_class("feed-hl"))) if gal else ""
    report(hl == launch["highlights"], "EF-02", "Gallery shows the launch highlights", hl[:60])
    imgs = gal.find_all(lambda n: n.tag == "img") if gal else []
    want = [(f"images/events/{LAUNCH}/{i + 1:02d}.{os.path.splitext(p['src'])[1][1:].replace('jpeg', 'jpg')}",
             str(p["width"]), str(p["height"]), p["alt"]) for i, p in enumerate(launch["photos"])]
    got = [(i.attrs.get("src"), i.attrs.get("width"), i.attrs.get("height"), i.attrs.get("alt")) for i in imgs]
    report(got == want and all(i.attrs.get("loading") == "lazy" for i in imgs), "EF-02",
           "Six photos: copied paths, width, height, alt, lazy", f"{len(imgs)} photos")
    files_ok, meta_left, sizes = True, [], []
    for src, w, h, _ in got:
        p = os.path.join(site, src or "")
        if not os.path.isfile(p):
            files_ok = False
            continue
        kind, size, meta = image_info(open(p, "rb").read())
        sizes.append(size == (int(w), int(h)) and max(size) <= 800)
        meta_left += [f"{os.path.basename(p)}: {m}" for m in meta]
    report(files_ok and all(sizes), "EF-02", "Photos copied into this site, sizes match, at most 800 px")
    src_meta = sum(len(image_info(open(os.path.join(MIRROR, "fixture", f), "rb").read())[2])
                   for f in os.listdir(os.path.join(MIRROR, "fixture")))
    report(src_meta >= 3 and not meta_left, "EF-02", "File details stripped (fixtures carried EXIF, GPS, text)",
           ", ".join(meta_left[:3]) or f"{src_meta} detail parts removed")
    more = first(gal, has_class("feed-more")) if gal else None
    report(more is not None and more.attrs.get("href") == launch["more_photos_url"]
           and text(more) == "More photos on prechangeway.com →", "EF-02", "'More photos on prechangeway.com →' link")
    keep = [a for a in root.find_all(lambda n: n.tag == "a") if text(a) == "Photos from the launch →"]
    report(len(keep) == 1, "EF-02", "The hand-written 'Photos from the launch →' link stays")
    report("must not show on this site" not in html, "EF-02", "Only the launch event shows, no other past event")
    report("prechangeway.com" not in " ".join(i.attrs.get("src", "") for i in root.find_all(lambda n: n.tag == "img")),
           "EF-02", "No photo is hotlinked from prechangeway.com")

    # EF-03: the upcoming list.
    items = upcoming(root)
    got = [(i["href"].replace(EVENTS_URL, ""), i["when"], i["title"], i["city"], i["local"] is not None) for i in items]
    report(got == UPCOMING_AT_NOW, "EF-03", "Next two per series, in date order, ended ones dropped",
           "ok" if got == UPCOMING_AT_NOW else "; ".join(f"{g[1]} {g[2]}" for g in got)[:90])
    report(all(i["attrs"].get("target") == "_blank" and "data-register-click" in i["attrs"] for i in items) and items,
           "EF-03", "Each links to its prechangeway.com page, counted as register_click")
    report("lu.ma" not in html and "fixture-live-online" not in html, "EF-03", "register_url is never shown")
    report(all("Saskatchewan time" not in i["when"] or i["when"].count(" · ") == 1 for i in items), "EF-03",
           "Date line: day · time Saskatchewan time (D44)")
    later = tempfile.mkdtemp(prefix="events-feed-later-")
    shutil.copy(os.path.join(site, "index.html"), later)
    r = run_script(later, FEED, now="2026-11-20T00:00:00-06:00")
    got = [i["when"] for i in upcoming(page_of(later))]
    month = [i for i in upcoming(page_of(later)) if i["when"] == "January 2027"]
    report(r.returncode == 0 and got == UPCOMING_LATER and month and month[0]["local"] is None, "EF-03",
           "Month-only event: 'January 2027', no time, no 'Your time'", "; ".join(got)[:90])
    r = run_script(later, FEED, now="2027-03-01T00:00:00-06:00")
    lhtml = open(os.path.join(later, "index.html"), encoding="utf-8").read()
    spot = re.search(r"<!-- events-feed:upcoming -->(.*?)<!-- /events-feed:upcoming -->", lhtml, re.S)
    report(r.returncode == 0 and spot and not spot.group(1).strip() and "Upcoming Events</a>" in lhtml, "EF-03",
           "No upcoming events: nothing extra, the button stays")
    changed = copy.deepcopy(valid)
    changed["upcoming"][1]["title"] = "FIXTURE · Prechange Live · Online · renamed"
    changed["upcoming"][1]["start"], changed["upcoming"][1]["end"] = "2026-11-18T11:00:00-06:00", "2026-11-18T12:30:00-06:00"
    r = run_script(site, write_feed(changed, work))
    first_item = upcoming(page_of(site))[0]
    data = json.load(open(os.path.join(site, "data", "events.json"), encoding="utf-8"))
    report(r.returncode == 0 and first_item["title"].endswith("renamed") and first_item["when"].startswith("Wednesday 18 November 2026")
           and data["upcoming"][1]["title"].endswith("renamed"), "EF-03", "A feed change shows up on the next run")
    r = run_script(site, FEED)  # back to the valid fixture

    # EF-04 and EF-06: anything wrong keeps the last good copy, unchanged.
    def mutate(fn):
        f = copy.deepcopy(valid)
        fn(f)
        return f

    def launch_of(f):
        return next(p for p in f["past"] if p["id"] == LAUNCH)

    def photo(f, src, width=800, height=533):
        launch_of(f)["photos"][0].update(src=src, width=width, height=height)

    bad = {
        "version 2": mutate(lambda f: f.update(version=2)),
        "not JSON": "{ this is not json",
        "missing title": mutate(lambda f: f["upcoming"][1].pop("title")),
        "time without offset": mutate(lambda f: f["upcoming"][1].update(start="2026-11-17T11:00:00")),
        "impossible date": mutate(lambda f: f["upcoming"][1].update(start="2026-02-30T11:00:00-06:00")),
        "duplicate id": mutate(lambda f: f["upcoming"][2].update(id="live-online-2026-11")),
        "link to another site": mutate(lambda f: f["upcoming"][1].update(url="https://example.com/events#x")),
        "Check link (/start)": mutate(lambda f: f["upcoming"][1].update(venue="https://prechangeway.com/start?src=live-online-2026-11")),
        "Check link (src=live-)": mutate(lambda f: f["upcoming"][2].update(title="Prechange Live · bring src=live-saskatoon")),
        "price with a sign": mutate(lambda f: launch_of(f).update(highlights="Tickets were $25 at the door.")),
        "price with a code": mutate(lambda f: f["upcoming"][1].update(title="Prechange Live · CAD 49")),
        "seven photos": mutate(lambda f: launch_of(f)["photos"].append(dict(launch_of(f)["photos"][0]))),
        "feed says 1200 px": mutate(lambda f: photo(f, "https://prechangeway.com/bad/big.jpg", 1200, 800)),
        "file larger than it says": mutate(lambda f: photo(f, "https://prechangeway.com/bad/big.jpg")),
        "not an image": mutate(lambda f: photo(f, "https://prechangeway.com/bad/not-image.jpg")),
        "photo needs rotating": mutate(lambda f: photo(f, "https://prechangeway.com/bad/rotated.jpg")),
        "photo missing": mutate(lambda f: photo(f, "https://prechangeway.com/bad/none.jpg")),
        "photo off prechangeway.com": mutate(lambda f: photo(f, "https://example.com/01.jpg")),
        "alt names a person": mutate(lambda f: launch_of(f)["photos"][1].update(alt="Sukant Ratnakar at the lectern")),
        "alt names a first name": mutate(lambda f: launch_of(f)["photos"][2].update(alt="Tammy answering a question")),
        "launch event missing": mutate(lambda f: f.update(past=[p for p in f["past"] if p["id"] != LAUNCH])),
        "feed larger than 256 KB": mutate(lambda f: f.update(padding="x" * 300000)),
    }
    good = snapshot(site)
    for label, feed in bad.items():
        r = run_script(site, write_feed(feed, work))
        same = snapshot(site) == good
        report(r.returncode == 1 and same and "nothing changed" in r.stderr, "EF-04",
               f"Rejected, last good copy kept: {label}",
               r.stderr.strip().split("\n")[-1][:60] if r.returncode == 1 else f"exit {r.returncode}")

    class Feed(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            try:
                if self.path == "/slow":
                    time.sleep(3)
                if self.path in ("/slow", "/feed.json"):
                    body = json.dumps(valid).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    self.send_response(404)
                    self.end_headers()
            except OSError:
                pass

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Feed)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    for label, url in (("feed answers 404", "/missing.json"), ("feed too slow (timeout)", "/slow"),
                       ("feed not on prechangeway.com", "/feed.json")):
        r = run_script(site, None, FEED_URL=base + url, FETCH_TIMEOUT_MS="1000")
        report(r.returncode == 1 and snapshot(site) == good, "EF-04", f"Rejected, last good copy kept: {label}",
               r.stderr.strip().split("\n")[-1][:60])
    srv.shutdown()
    nomark = new_site()
    p = os.path.join(nomark, "index.html")
    open(p, "w", encoding="utf-8").write(open(p, encoding="utf-8").read().replace(MARKERS["gallery"][0], ""))
    before = snapshot(nomark)
    r = run_script(nomark, FEED)
    report(r.returncode == 2 and snapshot(nomark) == before, "EF-04", "Missing marker: stops, nothing written")
    src = open(SCRIPT, encoding="utf-8").read()
    report(all(w in src for w in ("AbortSignal.timeout(TIMEOUT)", "FEED_MAX", "PHOTO_MAX", "larger than")),
           "EF-04", "Every fetch has a timeout and a size limit")
    shutil.rmtree(work, ignore_errors=True)
    shutil.rmtree(later, ignore_errors=True)
    shutil.rmtree(nomark, ignore_errors=True)
    shutil.rmtree(site, ignore_errors=True)


def check_workflow():
    if not os.path.exists(WORKFLOW):
        report(False, "EF-05", "Daily workflow exists", "missing")
        return
    y = open(WORKFLOW, encoding="utf-8").read()
    crons = re.findall(r"cron:\s*['\"]([^'\"]+)['\"]", y)
    daily = len(crons) == 1 and re.fullmatch(r"([1-9]|[1-5]\d) ([01]?\d|2[0-3]) \* \* \*", crons[0])
    report(daily, "EF-05", "Runs once a day, off the hour", ", ".join(crons) or "no schedule")
    report("workflow_dispatch:" in y, "EF-05", "'Run workflow' button (workflow_dispatch)")
    triggers = y.split("\npermissions:")[0]
    report(not re.search(r"^\s*(push|pull_request|pull_request_target|repository_dispatch|workflow_run):", triggers, re.M),
           "EF-05", "No other trigger (no push, no ping, Q09-7)")
    perms = re.search(r"^permissions:\n((?:[ \t]+.+\n)+)", y, re.M)
    report(perms and perms.group(1).split() == ["contents:", "write"], "EF-05", "Permissions: contents: write only")
    uses = re.findall(r"uses:\s*(\S+)", y)
    report(uses and all(re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", u) for u in uses), "EF-05",
           "Every action pinned to a full commit SHA", ", ".join(uses))
    report("secrets." not in y and "deploy_hooks" not in y and "api.cloudflare.com" not in y, "EF-05",
           "No secret, token or deploy hook")
    report("node scripts/events-feed.mjs" in y and "git diff --cached --quiet" in y
           and 'commit -m "events: update from prechangeway.com feed"' in y
           and "github-actions[bot]" in y, "EF-05", "Commits only on change, as github-actions[bot]")


def check_local_page():
    """EF-07, the 'Your time' line and GA4 clicks, on a fixture build opened in Chrome."""
    site = new_site(full=True)
    r = run_script(site, FEED)
    if r.returncode != 0:
        report(False, "EF-07", "Fixture build for the browser checks", r.stderr.strip()[:80])
        return
    url = "file://" + os.path.join(site, "index.html")
    cases = [{"name": f"w{w}", "url": url, "width": w, "expr": LAYOUT_EXPR} for w in WIDTHS]
    cases += [{"name": tz, "url": url, "width": 1440, "tz": tz, "expr": LOCAL_EXPR}
              for tz in ("America/Toronto", "America/Regina", "Asia/Tokyo")]
    cases += [{"name": "nojs", "url": url, "width": 1440, "tz": "America/Toronto", "noJs": True}]
    res = browser(cases)
    for w in WIDTHS:
        x = res[f"w{w}"]
        v = x["value"]
        report(v["over"] <= 0 and v["upcoming"] == 4 and len(v["photos"]) == 6, "EF-07",
               f"Fixture page at {w} px: no sideways scroll", f"{v['over']} px sideways")
        report(not x["errors"], "EF-07", f"Fixture page at {w} px: no console errors", "; ".join(x["errors"])[:80])
        report(not prechange_requests(x["requests"]), "EF-01", f"Fixture page at {w} px: no request to prechangeway.com",
               ", ".join(prechange_requests(x["requests"]))[:80])
    v = res["w1440"]["value"]
    report(all(p[0] and p[1] and p[2] == "lazy" for p in v["photos"]), "EF-07", "Photos have width, height, lazy loading")
    toronto = res["America/Toronto"]["value"]
    online = [i for i in toronto if i["local"] is not None]
    report(len(online) == 2 and online[0]["local"]["shown"] and online[0]["local"]["text"] == "Your time: 12:00 pm – 1:30 pm EST",
           "EF-03", "'Your time' shown in Toronto (D45)", online[0]["local"]["text"] if online else "missing")
    report(all(i["local"] is None for i in toronto if "Online" not in i["title"]), "EF-03",
           "No 'Your time' for in-person events")
    regina = res["America/Regina"]["value"]
    report(regina and all(i["local"] is None or (i["local"]["hidden"] and not i["local"]["shown"]) for i in regina),
           "EF-03", "'Your time' hidden in Saskatchewan (UTC−6)")
    tokyo = res["Asia/Tokyo"]["value"]
    tok = [i["local"]["text"] for i in tokyo if i["local"]]
    report(tok and tok[0] == "Your time: Wednesday 18 November, 2:00 am – 3:30 am GMT+9", "EF-03",
           "'Your time' names the day when it differs (Tokyo)", tok[0] if tok else "missing")
    nojs = parse(res["nojs"]["value"] or "")
    locs = nojs.find_all(has_class("feed-local"))
    whens = [text(n) for n in nojs.find_all(has_class("feed-when"))]
    report(locs and all("hidden" in n.attrs and not text(n) for n in locs) and len(whens) == 4
           and "Saskatchewan time" in whens[0], "EF-03", "JavaScript off: Saskatchewan time only")

    # GA4: upcoming links count as register_click; gallery links do not (D22b-9, D25-3).
    html = open(os.path.join(site, "index.html"), encoding="utf-8").read()
    root = parse(html)
    anchors = q06.anchors(root, "https://changeanesthesiology.com/")
    scripts = [s for s in (" ".join(c for c in n.children if isinstance(c, str))
                           for n in root.find_all(lambda n: n.tag == "script" and "src" not in n.attrs))
               if "register_click" in s]

    def content(n):
        return "".join(c if isinstance(c, str) else content(c) for c in n.children)

    feed_in = [{"href": a["href"], "text": content(a["node"]),
                "attrs": {k: (v if v is not None else "") for k, v in a["node"].attrs.items()}} for a in anchors]
    r = subprocess.run(["node", "-e", q06.NODE_HARNESS], capture_output=True, text=True, timeout=30,
                       input=json.dumps({"script": scripts[0] if scripts else "", "anchors": feed_in}))
    fired = []
    if r.returncode == 0:
        res = json.loads(r.stdout)
        fired = [a["href"] for a, evs in zip(anchors, res["events"]) for e in evs if e["name"] == "register_click"]
    want = [a["href"] for a in anchors if a["href"] == EVENTS_URL or "data-register-click" in a["node"].attrs]
    gallery = [a["href"] for a in anchors if any("feed-gallery" in n.classes() for n in a["node"].ancestors())]
    report(sorted(fired) == sorted(want) and len(want) == 8, "EF-03", "GA4: register_click for the button and upcoming events",
           f"{len(fired)} fired, {len(want)} expected")
    report(gallery and not set(gallery) & set(fired) and EVENTS_URL + "#spotlight-change-anesthesiology-2026-08" not in fired,
           "EF-02", "GA4: gallery and photo links are not register_click")
    shutil.rmtree(site, ignore_errors=True)


# --- Part 2: the served site (EF-07, EF-08) -----------------------------------------------------------

def cut_css(lines):
    if CSS_START in lines and CSS_END in lines and lines.index(CSS_START) < lines.index(CSS_END):
        s, e = lines.index(CSS_START), lines.index(CSS_END)
        return lines[:s] + lines[e:], "\n".join(lines[s:e])
    return lines, None


def empty_spots(lines):
    inner = {}
    for name, (o, c) in MARKERS.items():
        a = next((i for i, l in enumerate(lines) if l.strip() == o), None)
        b = next((i for i, l in enumerate(lines) if l.strip() == c), None)
        if a is not None and b is not None and a < b:
            inner[name] = "\n".join(lines[a + 1:b])
            lines = lines[:a + 1] + lines[b:]
    return lines, inner


def spot_problems(inner, has_data):
    problems = []
    if not has_data:
        for name, body in inner.items():
            if body.strip():
                problems.append(f"the {name} spot holds content but data/events.json is absent (D42)")
        return problems
    allowed = {"ul": {"feed-up"}, "li": set(), "a": {"feed-more", ""}, "span": {"feed-when", "feed-local", "feed-title", "feed-city"},
               "div": {"feed-gallery", "reveal", "feed-photos"}, "p": {"tag", "feed-hl"}, "figure": set(), "img": set()}
    for name, body in inner.items():
        for n in parse(body).walk():
            if n.tag == "#root":
                continue
            if n.tag not in allowed or not set(n.classes()) <= (allowed[n.tag] | {""}):
                problems.append(f"the {name} spot holds <{n.tag} class='{' '.join(n.classes())}'>")
            if n.tag == "a" and not (n.attrs.get("href") or "").startswith(EVENTS_URL + "#"):
                problems.append(f"the {name} spot links to {n.attrs.get('href')}")
            if n.tag == "img" and not (n.attrs.get("src") or "").startswith(f"images/events/{LAUNCH}/"):
                problems.append(f"the {name} spot shows {n.attrs.get('src')}")
    return problems


def ef08_problems(old_html, new_html, has_data):
    problems, want = [], old_html
    for before, after in APPROVED_EDITS:
        if want.count(before) != 1:
            problems.append(f"approved edit not found once in {BASE_REF}: {before[:40]!r}")
            continue
        want = want.replace(before, after)
    lines, css = cut_css(new_html.split("\n"))
    lines, inner = empty_spots(lines)
    if set(inner) != set(MARKERS):
        problems.append("a marked spot is missing")
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, want.split("\n"), lines, autojunk=False).get_opcodes():
        if tag != "equal":
            got = lines[j1].strip()[:50] if j1 < len(lines) else "(nothing)"
            problems.append(f"{tag} near line {i1 + 1}: {got!r}")
    if css is None:
        problems.append("the events CSS block is missing")
    else:
        body = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
        sels = [s.strip() for m in re.finditer(r"([^{};]+)\{", body) if not m.group(1).strip().startswith("@")
                for s in m.group(1).split(",")]
        stray = [s for s in sels if not s.startswith(CSS_PREFIXES)]
        if stray:
            problems.append(f"new CSS styles other selectors: {stray[:3]}")
        if re.search(r"@import|url\(|@font-face|font-family:(?!var\(--(?:serif|sans|mono)\))", body):
            problems.append("new CSS loads a file or another font")
    problems += spot_problems(inner, has_data)
    return problems


def _after(pattern, line):
    def plant(html):
        lines = html.split("\n")
        for i, l in enumerate(lines):
            if re.search(pattern, l):
                return "\n".join(lines[:i + 1] + [line] + lines[i + 1:])
        return html
    return plant


PLANTED = {
    "edit outside the marked spots": lambda h: h.replace("surgery was torture", "surgery was agony", 1),
    "invented event in the upcoming spot": _after(re.escape(MARKERS["upcoming"][0]), '<ul class="feed-up"><li>x</li></ul>'),
    "photo in the gallery spot": _after(re.escape(MARKERS["gallery"][0]), '<img src="images/mola-fish.png" alt="">'),
    "GA4 matcher changed": lambda h: h.replace("a.hasAttribute('data-register-click')", "a.hasAttribute('data-x')", 1),
    "'Your time' script changed": lambda h: h.replace("getTimezoneOffset()===360", "getTimezoneOffset()===300", 1),
    "new CSS restyles an existing class": _after(re.escape(CSS_START), ".zone{padding:0}"),
    "new external script": _after(r'<meta name="description"', '<script src="https://example.com/x.js"></script>'),
    "marker removed": lambda h: h.replace(MARKERS["gallery"][1], "", 1),
}


def run_suite(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    except (OSError, subprocess.TimeoutExpired) as e:
        return None, [], str(e)
    return r, [l for l in r.stdout.splitlines() if l.startswith(("PASS", "FAIL"))], r.stderr.strip()


def check_served(base):
    try:
        changed = [f for f in git("diff", "--name-only", BASE_REF, "HEAD").split("\n") if f]
        dirty = git("status", "--porcelain", "--untracked-files=no").strip()
        old_index = git("show", f"{BASE_REF}:index.html")
        old_article = git("show", f"{BASE_REF}:article.html")
        tracked = git("ls-files").split("\n")
    except subprocess.CalledProcessError as e:
        die(f"git failed: {e.stderr.strip()}")
    has_data = "data/events.json" in tracked
    extra = [f for f in changed if not ALLOWED_FILES.match(f)]
    report(not extra, "EF-08", f"Checkout: only Q09's files changed since {BASE_REF}", ", ".join(extra) or f"{len(changed)} files")
    report(not dirty, "EF-08", "Checkout: no uncommitted changes to tracked files", dirty.replace("\n", ", ")[:80] or "clean")
    try:
        index, article = q06.fetch(base + "/"), q06.fetch(base + "/article")
    except Exception as e:  # noqa: BLE001
        die(f"cannot fetch {base}: {e}")
    report(article == old_article, "EF-08", f"article.html is exactly as in {BASE_REF}")
    probs = ef08_problems(old_index, index, has_data)
    report(not probs, "EF-08", f"index.html: {BASE_REF} plus Q09's code and feed content only", "; ".join(probs[:3]) or "ok")
    if probs:
        report(False, "EF-08", "Self-test: planted edits are caught", "needs a page that passes first")
    else:
        missed = [k for k, plant in PLANTED.items() if plant(index) == index or not ef08_problems(old_index, plant(index), has_data)]
        report(not missed, "EF-08", f"Self-test: all {len(PLANTED)} planted edits are caught", ", ".join(missed) or "ok")
    images = [f for f in tracked if f.startswith("images/events/")]
    report(has_data or not images, "EF-08", "Nothing invented: no data/events.json, no event photos (D42)" if not has_data
           else "Real feed: data/events.json and its photos are committed", ", ".join(images[:2]) or ("ok" if not has_data else "data present"))
    for path in ("/scripts/events-feed.mjs", "/data/events.json", "/tests/check_events_feed.py",
                 "/tests/fixtures/events/feed-valid.json", "/.github/workflows/events-feed.yml"):
        code = status(base + path)
        report(code == 404, "EF-08", f"{path} is not served", f"got {code}")

    root = parse(index)
    scripts = [" ".join(c for c in n.children if isinstance(c, str))
               for n in root.find_all(lambda n: n.tag == "script" and "src" not in n.attrs)]
    calls = [w for w in ("fetch(", "XMLHttpRequest", "sendBeacon", "EventSource", "WebSocket", "import(", "localStorage",
                         "sessionStorage", "document.cookie", "indexedDB") if any(w in s for s in scripts)]
    report(not calls, "EF-01", "No script on the page fetches, stores or sets cookies", ", ".join(calls) or "ok")

    cases = [{"name": f"w{w}", "url": base + "/", "width": w, "expr": LAYOUT_EXPR} for w in WIDTHS]
    res = browser(cases)
    for w in WIDTHS:
        x = res[f"w{w}"]
        report(x["value"]["over"] <= 0 and not x["errors"], "EF-07",
               f"Served page at {w} px: no sideways scroll, no console errors",
               "; ".join(x["errors"])[:60] or f"{x['value']['over']} px sideways")
        report(not prechange_requests(x["requests"]), "EF-01", f"Served page at {w} px: zero requests to prechangeway.com",
               ", ".join(prechange_requests(x["requests"]))[:80] or f"{len(x['requests'])} requests, none to prechangeway.com")

    for label, cmd, skip in (
            ("Q04 test: every check passes", ["bash", os.path.join(TESTS, "check_public_files.sh"), base], ()),
            ("Q06 test: every check but PR-04 passes", [sys.executable, os.path.join(TESTS, "check_price_and_events.py"), base], ("PR-04",)),
            ("Q08 test: every check passes (TL-05 replaced)", [sys.executable, os.path.join(TESTS, "check_three_layers.py"), base], ())):
        r, lines, err = run_suite(cmd)
        if r is None or not lines:
            report(False, "EF-08", label, (err or "no output")[:80])
            continue
        fails = [l for l in lines if l.startswith("FAIL") and l.split()[1] not in skip]
        skipped = sum(1 for l in lines if l.split()[1] in skip)
        report(not fails and r.returncode in ((0, 1) if skip else (0,)), "EF-08", label,
               f"{len(lines) - skipped - len(fails)} passed, {len(fails)} failed" + (f", {skipped} PR-04 lines" if skip else "")
               + (f": {fails[0][:50]}" if fails else ""))


def main():
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} <base-url>", file=sys.stderr)
        sys.exit(2)
    base = sys.argv[1].rstrip("/")
    if not os.path.exists(SCRIPT):
        report(False, "EF-01", "scripts/events-feed.mjs exists", "missing")
    else:
        print("Part 1: the feed script on fixtures (no network)\n")
        check_script()
        print()
        check_workflow()
        print()
        check_local_page()
        print()
    print(f"Part 2: the site at {base} (base reference {BASE_REF})\n")
    check_served(base)
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
