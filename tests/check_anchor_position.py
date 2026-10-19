#!/usr/bin/env python3
"""Checks that links to a section land on it, below the fixed menu (Q13, D61, 17 Oct 2026).

Usage:  python3 tests/check_anchor_position.py <base-url>
  e.g.  python3 tests/check_anchor_position.py https://fix-anchor-position-changeanesthesiology.sukantratnakar.workers.dev

Opening /#where-this-fits (prechangeway.com links there) landed above the section. The page glides
to a section (scroll-behavior: smooth) towards a spot fixed when the glide starts; the images above
it, with no space kept for them while they load, and the fonts then moved the section mid-glide.
#model and #po-terms, with no top padding of their own, ended up under the fixed menu.

For every in-page target (TARGETS), at 390 and 1280 px, in headless Chrome with an empty cache
each time (analytics blocked):
  AP-01  where the target is meant to land (scrolled to once the page has loaded): its heading
         sits just below the menu, 8 to 120 px under the menu's bottom edge
  AP-02  arriving fresh at /#id, three times: the heading is never under the menu and is within
         64 px of AP-01's spot. Only the fonts can still move the page mid-glide; they move a
         section by at most 57 px (measured 17 Oct 2026, fallback against final fonts).
  AP-03  a jump from the top of the loaded page (location.hash, as a menu link does) lands on
         AP-01's spot, within 4 px
         (AP-02 and AP-03 allow 26 px more for a target that fades in itself: #po-terms)
  AP-04  nothing looks different: once loaded, every element of the home page has the same
         position, size, font and colour as on BASE_REF's page (served from this checkout)
  AP-05  nothing else changed against BASE_REF (default 90d9c26, main): only index.html and
         tests/ (and the weekly check's two files, OPS_FILES, which are never served), the
         article untouched, index.html is BASE_REF plus the Q13 CSS block
  AP-06  the Q12 and Q10/Q11 tests pass (between them they run Q04, Q06 apart from its known
         PR-04 lines, and Q08)
Prints one PASS/FAIL line per check and where each heading landed (px from the top of the
window). Exits 1 if any check fails, 2 if the test can't run. Node and Chrome must be installed.
"""

import functools
import http.server
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_price_and_events as q06  # noqa: E402  (shared fetch and Chrome path)

q06.UA = "check_anchor_position.py (changeanesthesiology repo test)"
TESTS = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TESTS)
BASE_REF = os.environ.get("BASE_REF", "90d9c26")
WIDTHS = (390, 1280)
TARGETS = ["premise", "preorder", "po-terms", "author", "model", "morphosis", "where-this-fits", "inside", "event"]
ARRIVALS = 3
GAP = (8, 120)       # AP-01: px between the menu's bottom edge and the heading
FONT_SLACK = 64      # AP-02: px an arrival may differ from AP-01 (fonts move a section by 57 px at most)
JUMP_SLACK = 4       # AP-03
# A target that fades in itself (.reveal, now only #po-terms) slides up 26 px (translateY(26px)
# in index.html) after the browser has scrolled to it, so it lands up to 26 px higher; AP-02 and
# AP-03 allow that on top of their own slack. It did the same before Q13.
REVEAL_SHIFT = 26

# Q13's one edit to BASE_REF's index.html, as (before, after), word for word.
Q13_CSS = r'''/* Q13 (D61): links to a section land on it, below the fixed menu. The browser keeps the menu's
   height clear at the top (4rem; 3.5rem on phones), the two targets with no top padding of their
   own get 2rem more, and each image above the sections keeps its space while it loads, so nothing
   moves while the page glides to a section. Nothing looks different once the page has loaded. */
html{scroll-padding-top:4rem}
@media(max-width:680px){html{scroll-padding-top:3.5rem}}
#model,#po-terms{scroll-margin-top:2rem}
.hero-series img{aspect-ratio:auto 268/300}
.hero-cover,.band img{aspect-ratio:auto 1000/1569}
.series-img img{aspect-ratio:auto 1600/900}
.author-photo img{aspect-ratio:auto 707/760}
.analogy-fig img{aspect-ratio:auto 1071/583}
'''
APPROVED_EDITS = [("html{scroll-behavior:smooth}\n", "html{scroll-behavior:smooth}\n" + Q13_CSS)]

PLANTED = {
    "word changed": lambda h: h.replace("surgery was torture", "surgery was agony", 1),
    "page colour changed": lambda h: h.replace("--slate:#8792A6", "--slate:#5C7385", 1),
    "menu space changed": lambda h: h.replace("html{scroll-padding-top:4rem}", "html{scroll-padding-top:6rem}", 1),
    "image rule changed": lambda h: h.replace("aspect-ratio:auto 1071/583", "aspect-ratio:auto 16/9", 1),
    "script added": lambda h: h.replace("</head>", "<script>void 0</script>\n</head>", 1),
}

# Files that only run or describe the weekly check (Q14, D64). The website never serves them
# (.assetsignore hides dot-folders and *.md; Q04 checks), so the checkout checks allow them:
# AP-05 here, TV-08 (Q12) and EL-04 (Q10/Q11).
OPS_FILES = {".github/workflows/weekly-check.yml", "OPERATIONS.md"}

RESULTS = []

# Heading of a target, the menu's bottom edge and the window, in px from the top of the window.
MEASURE = r"""(id => { const t = document.getElementById(id), h = t.querySelector('.tag, h1, h2, h3, h4, q') || t,
  n = document.getElementById('nav').getBoundingClientRect(), r = h.getBoundingClientRect();
  return {heading: h.textContent.replace(/\s+/g, ' ').trim().slice(0, 30), top: Math.round(r.top),
          bottom: Math.round(r.bottom), nav: Math.round(n.bottom), vh: innerHeight,
          fades: t.classList.contains('reveal')}; })"""

# Every element of the loaded page (images loaded, fade-ins shown, the drifting fish held still):
# position, size, font, colour.
LAYOUT = r"""(async () => {
  const st = document.createElement('style');
  st.textContent = '.reveal{opacity:1!important;transform:none!important;transition:none!important}*{animation:none!important}';
  document.head.appendChild(st);
  document.querySelectorAll('img').forEach(i => { i.loading = 'eager'; });
  await Promise.all([...document.images].map(i => i.decode().catch(() => {})));
  await document.fonts.ready;
  await new Promise(r => setTimeout(r, 400));
  const skip = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'LINK', 'META', 'TEMPLATE']);
  return [...document.body.querySelectorAll('*')].filter(e => !skip.has(e.tagName)).map(e => {
    const r = e.getBoundingClientRect(), c = getComputedStyle(e);
    return [e.tagName, String(e.className), +r.left.toFixed(1), +(r.top + scrollY).toFixed(1), +r.width.toFixed(1),
            +r.height.toFixed(1), c.font, c.color, c.backgroundColor, c.display, c.visibility];
  });
})()"""

# One Chrome; every case in its own new browser context, so each load starts with an empty cache.
BROWSER = r"""
const { spawn } = require('child_process');
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const chrome = spawn(input.chrome, ['--headless=new', '--disable-gpu', '--hide-scrollbars', '--no-first-run',
    `--user-data-dir=${input.profile}`, `--remote-debugging-port=${input.port}`, 'about:blank'], { stdio: 'ignore' });
  try {
    let ver;
    for (let i = 0; i < 75 && !ver; i++) {
      try { ver = await (await fetch(`http://127.0.0.1:${input.port}/json/version`)).json(); } catch { await sleep(200); }
    }
    const ws = new WebSocket(ver.webSocketDebuggerUrl);
    await new Promise((ok, bad) => { ws.addEventListener('open', ok, { once: true }); ws.addEventListener('error', bad, { once: true }); });
    let id = 0; const waiting = new Map(), listeners = [];
    ws.addEventListener('message', e => { const m = JSON.parse(e.data);
      if (m.id && waiting.has(m.id)) { waiting.get(m.id)(m); waiting.delete(m.id); } else listeners.forEach(f => f(m)); });
    const send = (method, params = {}, sessionId) => new Promise((ok, bad) => { const i = ++id;
      waiting.set(i, m => m.error ? bad(new Error(method + ': ' + m.error.message)) : ok(m.result));
      ws.send(JSON.stringify(sessionId ? { id: i, method, params, sessionId } : { id: i, method, params })); });
    const out = [];
    for (const c of input.cases) {
      const { browserContextId } = await send('Target.createBrowserContext', {});
      const { targetId } = await send('Target.createTarget', { url: 'about:blank', browserContextId });
      const { sessionId } = await send('Target.attachToTarget', { targetId, flatten: true });
      const s = (method, params) => send(method, params, sessionId);
      const errors = [];
      const onError = m => { if (m.sessionId === sessionId && m.method === 'Runtime.exceptionThrown')
        errors.push(m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text); };
      listeners.push(onError);
      await s('Page.enable'); await s('Network.enable'); await s('Runtime.enable');
      await s('Network.setBlockedURLs', { urls: ['*googletagmanager.com*', '*google-analytics.com*',
        '*analytics.google.com*', '*cloudflareinsights.com*', '*doubleclick.net*'] });
      await s('Emulation.setDeviceMetricsOverride', { width: c.width, height: c.width < 768 ? 844 : 800,
        deviceScaleFactor: 1, mobile: c.width < 768 });
      const loaded = new Promise(r => listeners.push(function f(m) {
        if (m.sessionId === sessionId && m.method === 'Page.loadEventFired') { listeners.splice(listeners.indexOf(f), 1); r(); } }));
      await s('Page.navigate', { url: c.url });
      await Promise.race([loaded, sleep(30000)]);
      await sleep(c.wait);
      const v = await s('Runtime.evaluate', { expression: c.expr, returnByValue: true, awaitPromise: true });
      out.push({ name: c.name, value: v.result.value ?? null, errors });
      listeners.splice(listeners.indexOf(onError), 1);
      await send('Target.closeTarget', { targetId });
      await send('Target.disposeBrowserContext', { browserContextId }).catch(() => {});
    }
    process.stdout.write(JSON.stringify(out));
  } finally {
    chrome.kill();
  }
})().catch(e => { console.error(e.stack || String(e)); process.exit(1); });
"""


def report(ok, req, what, detail=""):
    RESULTS.append((req, bool(ok)))
    print(f"{'PASS' if ok else 'FAIL'}  {req}  {what:<60} {detail}".rstrip())


def die(msg):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(2)


def git(*args):
    return subprocess.run(["git", "-C", REPO_ROOT, *args], check=True, capture_output=True, text=True).stdout


def free_port():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def browser(cases):
    if not os.path.exists(q06.CHROME):
        die(f"Chrome not found at {q06.CHROME} (set CHROME)")
    profile = tempfile.mkdtemp(prefix="check-anchor-position-")
    try:
        r = subprocess.run(["node", "-e", BROWSER], capture_output=True, text=True, timeout=900,
                           input=json.dumps({"chrome": q06.CHROME, "port": free_port(), "profile": profile, "cases": cases}))
    finally:
        time.sleep(0.5)
        shutil.rmtree(profile, ignore_errors=True)
    if r.returncode != 0:
        die(f"browser check failed to run: {r.stderr.strip()[:300]}")
    return {x["name"]: x for x in json.loads(r.stdout)}


def in_parallel(groups):
    """Runs each list of cases in its own Chrome at the same time; returns all results."""
    out, threads = {}, []
    for cases in groups:
        t = threading.Thread(target=lambda c=cases: out.update(browser(c)))
        t.start()
        threads.append(t)
    for t in threads:
        t.join()
    return out


def landing_cases(base, width):
    cases = []
    for t in TARGETS:
        for i in range(ARRIVALS):
            cases.append({"name": f"{width}|{t}|arrive{i}", "url": f"{base}/#{t}", "width": width, "wait": 4000,
                          "expr": f"{MEASURE}('{t}')"})
        # A jump from the top once loaded (as a menu link does), then where the target is meant to
        # land: scrolled to directly, which honours the menu space and the targets' own margins.
        cases.append({"name": f"{width}|{t}|jump", "url": f"{base}/", "width": width, "wait": 2000, "expr": (
            "new Promise(ok => { location.hash = '#" + t + "'; setTimeout(() => { const jump = " + MEASURE + "('" + t + "');"
            " document.getElementById('" + t + "').scrollIntoView({behavior: 'instant'});"
            " setTimeout(() => ok({jump, meant: " + MEASURE + "('" + t + "')}), 1500); }, 3000); })")})
    return cases


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def serve_base(index_html):
    """Serves BASE_REF's index.html with this checkout's other files (AP-05 checks they are unchanged)."""
    root = tempfile.mkdtemp(prefix="check-anchor-position-base-")
    with open(os.path.join(root, "index.html"), "w") as f:
        f.write(index_html)
    for name in os.listdir(REPO_ROOT):
        if name not in ("index.html", ".git"):
            os.symlink(os.path.join(REPO_ROOT, name), os.path.join(root, name))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=root))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, root, f"http://127.0.0.1:{srv.server_address[1]}"


def changes(old, new):
    """How the served page differs from BASE_REF plus Q13's edit; [] if not at all."""
    want = old
    for before, after in APPROVED_EDITS:
        if want.count(before) != 1:
            return [f"approved edit not found once in {BASE_REF}: {before[:40]!r}"]
        want = want.replace(before, after)
    if new == want:
        return []
    w, n = want.split("\n"), new.split("\n")
    k = next((i for i, (a, b) in enumerate(zip(w, n)) if a != b), min(len(w), len(n)))
    return [f"line {k + 1} differs: {(n[k] if k < len(n) else '(end of file)').strip()[:60]!r}"]


def run_suite(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
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
        changed = [f for f in git("diff", "--name-only", BASE_REF, "HEAD").split("\n") if f]
        dirty = git("status", "--porcelain", "--untracked-files=no").strip()
        old_index, old_article = git("show", f"{BASE_REF}:index.html"), git("show", f"{BASE_REF}:article.html")
    except subprocess.CalledProcessError as e:
        die(f"git failed: {e.stderr.strip()}")
    except Exception as e:  # noqa: BLE001
        die(f"cannot fetch {base}: {e}")
    print(f"Checking {base} (base reference {BASE_REF})\n")

    srv, root, base_local = serve_base(old_index)
    try:
        res = in_parallel([landing_cases(base, w) for w in WIDTHS] + [
            [{"name": f"layout|{w}|{which}", "url": url + "/", "width": w, "wait": 1500, "expr": LAYOUT}
             for w in WIDTHS for which, url in (("served", base), ("base", base_local))]])
    finally:
        srv.shutdown()
        shutil.rmtree(root, ignore_errors=True)

    # AP-01 to AP-03: where each heading lands.
    table = []
    for w in WIDTHS:
        for t in TARGETS:
            j = res[f"{w}|{t}|jump"]["value"]
            arrivals = [res[f"{w}|{t}|arrive{i}"]["value"] for i in range(ARRIVALS)]
            if not j or not all(arrivals):
                report(False, "AP-01", f"{w} px #{t}: measured", "no result")
                continue
            meant, menu = j["meant"], j["meant"]["nav"]
            gap, fade = meant["top"] - menu, REVEAL_SHIFT if meant["fades"] else 0
            report(GAP[0] <= gap <= GAP[1] and meant["bottom"] <= meant["vh"], "AP-01",
                   f"{w} px #{t}: '{meant['heading'][:22]}' lands just below the menu",
                   f"heading at {meant['top']} px, {gap} px below the menu (allowed {GAP[0]} to {GAP[1]})")
            bad = [a["top"] for a in arrivals if a["top"] < a["nav"] or abs(a["top"] - meant["top"]) > FONT_SLACK + fade]
            report(not bad, "AP-02", f"{w} px #{t}: {ARRIVALS} fresh arrivals land on it",
                   ", ".join(str(a["top"]) for a in arrivals) + f" px (menu ends at {arrivals[0]['nav']} px)")
            report(abs(j["jump"]["top"] - meant["top"]) <= JUMP_SLACK + fade and j["jump"]["top"] >= j["jump"]["nav"], "AP-03",
                   f"{w} px #{t}: a jump from the top lands on it", f"{j['jump']['top']} px" + (" (fades in itself)" if fade else ""))
            table.append((w, t, menu, meant["top"], j["jump"]["top"], [a["top"] for a in arrivals]))
    print()
    print("Where each heading lands, in px from the top of the window:")
    for w, t, menu, meant, jump, arr in table:
        print(f"  {w:>4} px  #{t:<16} menu ends {menu:>3}  meant {meant:>4}  jump {jump:>4}  arrivals {', '.join(f'{a:>4}' for a in arr)}")
    print()

    # AP-04: nothing looks different once loaded.
    for w in WIDTHS:
        a, b = res[f"layout|{w}|served"]["value"], res[f"layout|{w}|base"]["value"]
        diff = next((f"{x[0]}.{x[1][:20]} {x[2:6]} vs {y[2:6]}" for x, y in zip(a or [], b or []) if x != y), "")
        same = bool(a) and bool(b) and len(a) == len(b) and not diff
        report(same, "AP-04", f"{w} px: every element as on {BASE_REF} once loaded",
               diff[:80] or f"{len(a or [])} elements, same position, size, font and colour")
    print()

    # AP-05: nothing else changed against main.
    extra = [f for f in changed if f != "index.html" and not f.startswith("tests/") and f not in OPS_FILES]
    report(not extra, "AP-05", f"Checkout: only index.html and tests/ changed since {BASE_REF}", ", ".join(extra) or f"{len(changed)} files")
    report(not dirty, "AP-05", "Checkout: no uncommitted changes to tracked files", dirty.replace("\n", ", ")[:80] or "clean")
    report(article == old_article, "AP-05", f"article.html is exactly as in {BASE_REF}")
    probs = changes(old_index, index)
    report(not probs, "AP-05", f"index.html: {BASE_REF} plus the Q13 CSS block only", "; ".join(probs) or "ok")
    if probs:
        report(False, "AP-05", "Self-test: planted edits are caught", "needs a page that passes first")
    else:
        missed = [k for k, plant in PLANTED.items() if plant(index) == index or not changes(old_index, plant(index))]
        report(not missed, "AP-05", f"Self-test: all {len(PLANTED)} planted edits are caught", ", ".join(missed) or "ok")
    print()

    # AP-06: the earlier suites (Q12 and Q10/Q11 each run Q04, Q06 and Q08 too).
    for label, script in (("Q12 test: every check passes", "check_three_layers_v3.py"),
                          ("Q10/Q11 test: every check passes", "check_events_links.py")):
        r, lines, err = run_suite([sys.executable, os.path.join(TESTS, script), base])
        if r is None or not lines:
            report(False, "AP-06", label, (err or "no output")[:80])
            continue
        fails = [l for l in lines if l.startswith("FAIL")]
        report(not fails and r.returncode == 0, "AP-06", label,
               f"{len(lines) - len(fails)} passed, {len(fails)} failed" + (f": {fails[0][:50]}" if fails else ""))
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
