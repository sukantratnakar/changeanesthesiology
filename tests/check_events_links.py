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
         from Q09 is in the checkout. This replaces Q08's TL-05, as Q09 did.
  EL-05  no request to prechangeway.com when either page loads (headless Chrome, analytics blocked)
  EL-06  the Q04, Q06 (apart from its known PR-04 lines) and Q08 tests pass
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
import check_price_and_events as q06  # noqa: E402  (shared parser, fetch, click harness, Chrome path)

from check_price_and_events import parse, text  # noqa: E402

q06.UA = "check_events_links.py (changeanesthesiology repo test)"
TESTS = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TESTS)
BASE_REF = os.environ.get("BASE_REF", "27cf1c4")
EVENTS_URL = "https://prechangeway.com/events"
PHOTOS_URL = EVENTS_URL + "#spotlight-change-anesthesiology-2026-08"
LABEL = "Upcoming Events"
PHOTOS_TEXT = "Photos from the launch →"
# Q10's edits to BASE_REF, as (file, before, after). None were needed: the three links and the
# photos address were already in place on main.
APPROVED_EDITS = []
Q09_FILES = ("scripts/events-feed.mjs", ".github/workflows/events-feed.yml", "data/events.json", "images/events/")
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
      await send('Page.navigate', { url: c.url }); await loaded;
      await sleep(1500);
      const over = (await send('Runtime.evaluate', { returnByValue: true,
        expression: 'document.documentElement.scrollWidth - document.documentElement.clientWidth' })).result.value;
      out.push({ name: c.name, over, errors: [...errors], requests: [...requests] });
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
    extra = [f for f in changed if not any(f == a or (a.endswith("/") and f.startswith(a)) for a in allowed)]
    report(not extra, "EL-04", f"Checkout: only tests/ changed since {BASE_REF}", ", ".join(extra) or f"{len(changed)} files")
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
        calls = re.findall(r"(?:fetch|open|sendBeacon|EventSource|WebSocket)\(\s*['\"][^'\"]*prechangeway[^'\"]*['\"]", scripts)
        report(not src and not calls, "EL-05", f"{name}: no script, image or call to prechangeway.com",
               ", ".join(src + calls)[:80] or "ok")
    cases = [{"name": f"{p} {w}px", "url": base + p, "width": w} for p in ("/", "/article") for w in WIDTHS]
    for x in browser(cases):
        pre = [u for u in x["requests"] if re.match(r"^https?://([^/]*\.)?prechangeway\.com(/|$)", u)]
        report(not pre and not x["errors"] and x["over"] <= 0, "EL-05",
               f"{x['name']}: zero requests to prechangeway.com, no errors",
               ", ".join(pre + x["errors"])[:70] or f"{len(x['requests'])} requests, {x['over']} px sideways")
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
