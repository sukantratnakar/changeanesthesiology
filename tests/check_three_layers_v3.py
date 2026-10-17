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
  TV-08  nothing else changed against BASE_REF (default 27cf1c4, main); article untouched.
         This replaces Q08's TL-05 on this branch.
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

from check_price_and_events import parse, text  # noqa: E402

q06.UA = "check_three_layers_v3.py (changeanesthesiology repo test)"
TESTS = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TESTS)
BASE_REF = os.environ.get("BASE_REF", "27cf1c4")
WIDTHS = (360, 390, 820, 1280, 1440)
PALETTE = {"--energy": "#7A2E2A", "--slate": "#5C7385", "--sage": "#687B5A", "--routines": "#B07A3B",
           "--ink": "#0C203B", "--navy-deep": "#071426", "--gold": "#D4B15F", "--gold-ln": "#B8995A",
           "--accent": "#2E6B66"}
GONE = ["Broaden · Expand · Reduce · Increase", "Broaden", "Mola Series", "Book Two", "This site",
        "Where the Prechange Way comes from"]
ORDER = [".tl3-why", ".tl3-pc", ".tl3-launch", ".tl3-sf", ".tl3-ribbon", ".tl3-found"]
ORDER_NAMES = ["arch (why)", "Prechange", "launch", "after launch", "ribbon (how)", "foundation"]

# Q12's edits to BASE_REF's index.html, as (before, after), filled in with the change itself.
APPROVED_EDITS = None

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
    """How the served page differs from BASE_REF plus Q12's edits; [] if not at all."""
    if APPROVED_EDITS is None:
        return ["Q12's edits are not recorded in this test yet"]
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
    report(tagged is not None and text(tagged) == "This book"
           and any("tl3-name" in a.classes() for a in tagged.ancestors()), "TV-06", "'This book' beside Change Anesthesiology")
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
    report(not probs, "TV-08", f"index.html: {BASE_REF} plus the v3 figure only", "; ".join(probs) or "ok")
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
