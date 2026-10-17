#!/usr/bin/env python3
"""Checks the price, end of the launch offer and event links (PR-01 to PR-06).

Q06, 16 Oct 2026. Decisions D22a and D22b-3 to D22b-9, and Sukant's answers
to the Q06 report (paperback label, launch record in past tense, "Online and in
person", "Upcoming Events" kept on one line).

Usage:  python3 tests/check_price_and_events.py <base-url>
  e.g.  python3 tests/check_price_and_events.py https://changeanesthesiology.com

Fetches / and /article from the base URL and prints one PASS/FAIL line per
check. Exits 1 if any check fails, 2 if the test itself can't run.
Fetches pages with urllib only (no browser), so it does not trigger Google
Analytics. PR-06 runs the page's own click-tracking script in Node with a
stub gtag, and the PR-03 layout checks measure the pages in headless Chrome
(analytics requests blocked), so Node and Chrome must be installed. Set CHROME
to Chrome's path if it isn't in the usual macOS place.
PR-04 compares the served pages with MAIN_REF (default f5ad564, main before
this change) from the git checkout this script lives in.
"""

import difflib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

NEW_STRIPE_URL = "https://buy.stripe.com/fZueVd06q7Wb7fDcjagw005"
OLD_STRIPE_URLS = [
    "https://buy.stripe.com/bJe00j3iC3FV1Vjerigw001",  # CA$79, replaced
    "https://buy.stripe.com/dRmaEXaL4foDeI56YQgw002",  # CA$39 launch offer
]
EVENTS_URL = "https://prechangeway.com/events"
PHOTOS_URL = EVENTS_URL + "#spotlight-change-anesthesiology-2026-08"
PRICE_LINE = "USD 79 · paperback edition · shipping included"
TAX_LINE = "Taxes and import duties extra, where they apply."
EVENT_TEXT = "Upcoming Events"
BUY_TEXT = "Buy — USD 79"
PHOTOS_TEXT = "Photos from the launch →"
BOX_LABEL = "Paperback · posted anywhere in the world"
ONLINE_LINE = "Online and in person · on prechangeway.com"
ARTICLE_SESSIONS = "Free sessions online and in person, listed on prechangeway.com."
# Q08 (TL-02) adds one link to the Prechange home page, not to events; PR-03 skips it.
PRECHANGE_HOME = ("https://prechangeway.com", "Read about Prechange at prechangeway.com →")
# Q09 (D43): links written from prechangeway.com's feed inside the event band. Upcoming events
# (.feed-up) count as register_click like the button; the gallery's links (.feed-gallery) do not.
FEED_LISTS = ("feed-up", "feed-gallery")


def feed_link(a):
    """A link the Q09 feed wrote: to /events#… inside the upcoming list or the gallery."""
    return (a["href"].startswith(EVENTS_URL + "#")
            and any(c in FEED_LISTS for n in a["node"].ancestors() for c in n.classes()))


def upcoming_link(a):
    return feed_link(a) and any("feed-up" in n.classes() for n in a["node"].ancestors())
# The launch record, in past tense, with no book signing (Sukant, 16 Oct 2026).
LAUNCH_RECORD = [
    "Guests arrived and connected over evening snacks",
    "Sukant Ratnakar presented Change Anesthesiology",
    "Conversations and networking",
    "Event ended",
    "Featured Guest Authors",
    "Brought together leaders",
]
BASE_URL = ""  # set from the command line
CHROME = os.environ.get("CHROME", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")

MAIN_REF = os.environ.get("MAIN_REF", "f5ad564")
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = "check_price_and_events.py (changeanesthesiology repo test)"

# Lines of MAIN_REF that this change may touch (PR-04). Anything else that
# differs between MAIN_REF and the served page fails.
def _lines(*parts):
    out = set()
    for p in parts:
        if isinstance(p, tuple):
            out.update(range(p[0], p[1] + 1))
        else:
            out.add(p)
    return out

ALLOWED = {
    "index.html": _lines(
        15, 19, 26,            # meta descriptions
        68,                    # menu gap, so "Upcoming Events" stays on one line
        280,                   # buy grid: 3 columns -> 2
        381, 397, 404,         # menu button, hero button, hero label
        (439, 446),            # hidden note above the buy section
        450, 453, (455, 457),  # heading, lead, price box
        466, 467, 470, 472,    # option one: price, text, tax item, button
        479, 488,              # Amazon text, India link
        (491, 504),            # option three (signed copy) removed
        507, 512, 516,         # note, shipping, tax
        689, (709, 713),       # event band
        700, 701, 704, 705,    # launch programme: past tense, no book signing
        745, 782,              # "Featured Guest Authors", partner line
        800, 840,              # publisher note, footer link
        864,                   # GA4 register_click match
    ),
    "article.html": _lines(
        67,                    # top-bar button: no wrapping
        144, 154, (210, 212),
    ),
}
FILES_ALLOWED_TO_CHANGE = {"index.html", "article.html"}

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
        "meta", "source", "track", "wbr"}


class Node:
    def __init__(self, tag, attrs, parent):
        self.tag, self.attrs, self.parent, self.children = tag, attrs, parent, []

    def classes(self):
        return (self.attrs.get("class") or "").split()

    def walk(self):
        yield self
        for c in self.children:
            if isinstance(c, Node):
                yield from c.walk()

    def find_all(self, pred):
        return [n for n in self.walk() if pred(n)]

    def ancestors(self):
        n = self.parent
        while n is not None:
            yield n
            n = n.parent


class TreeBuilder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("#root", {}, None)
        self.cur = self.root

    def handle_starttag(self, tag, attrs):
        n = Node(tag, dict(attrs), self.cur)
        self.cur.children.append(n)
        if tag not in VOID:
            self.cur = n

    def handle_startendtag(self, tag, attrs):
        self.cur.children.append(Node(tag, dict(attrs), self.cur))

    def handle_endtag(self, tag):
        n = self.cur
        while n is not self.root and n.tag != tag:
            n = n.parent
        if n is not self.root:
            self.cur = n.parent

    def handle_data(self, data):
        self.cur.children.append(data)


def parse(html):
    b = TreeBuilder()
    b.feed(html)
    b.close()
    return b.root


def text(node, skip=lambda n: False):
    """Visible text: no scripts, styles or comments; elements separated by spaces."""
    if isinstance(node, str):
        return node
    if node.tag in ("script", "style") or skip(node):
        return ""
    return norm(" ".join(text(c, skip) for c in node.children))


def norm(s):
    return re.sub(r"\s+", " ", s).strip()


def wording(root, skip=lambda n: False):
    """Everything a visitor or a link preview can read: text, titles, alt and meta text."""
    parts = [text(root, skip)]
    for n in root.walk():
        if skip(n) or any(skip(a) for a in n.ancestors()):
            continue
        for k in ("alt", "title", "aria-label", "placeholder"):
            if n.attrs.get(k):
                parts.append(n.attrs[k])
        if n.tag == "meta" and n.attrs.get("content") and (
                n.attrs.get("name") or n.attrs.get("property")):
            parts.append(n.attrs["content"])
    return norm(" ".join(parts))


def fetch(url):
    # "Accept: */*" as curl sends: Cloudflare injects its Web Analytics script
    # into pages for browser-style requests, which would hide the site's own file.
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8")


def git(*args):
    return subprocess.run(["git", "-C", REPO_ROOT, *args], check=True,
                          capture_output=True, text=True).stdout


# --- reporting ---------------------------------------------------------------

RESULTS = []


def report(ok, req, what, detail=""):
    RESULTS.append((req, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {req}  {what:<52} {detail}".rstrip())


def die(msg):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(2)


# --- checks ------------------------------------------------------------------

def anchors(root, page_url):
    out = []
    for a in root.find_all(lambda n: n.tag == "a" and "href" in n.attrs):
        out.append({"node": a, "raw": a.attrs["href"] or "",
                    "href": urljoin(page_url, a.attrs["href"] or ""),
                    "text": text(a)})
    return out


def check_pr01(pages):
    idx = pages["index"]["root"]
    amts = idx.find_all(lambda n: "po-amt" in n.classes() and PRICE_LINE in text(n))
    report(len(amts) == 1, "PR-01", "Price line said once, beside the buy option",
           f"found {len(amts)}x '{PRICE_LINE}'")
    if amts:
        t = text(amts[0])
        report(t == f"{PRICE_LINE} {TAX_LINE}", "PR-01", "Tax and duty line right under the price",
               f"got '{t}'")
    boxes = idx.find_all(lambda n: "po-price" in n.classes())
    box = text(boxes[0]) if boxes else ""
    ok = bool(re.search(r"\bUSD 79\b", box)) and "shipping included" in box.lower() and TAX_LINE in box
    report(ok, "PR-01", "Price box: USD 79, shipping included, tax line", f"got '{box}'")
    labels = [text(n) for n in idx.find_all(lambda n: "po-was" in n.classes())]
    report(labels == [BOX_LABEL], "PR-01", "Price box label is the quiet 'Paperback' label",
           f"got {labels}")

    # "Paperback" is never a headline: only the price box label and the price line say it.
    every = " ".join(p["wording"] for p in pages.values())
    n = len(re.findall(r"paperback", every, re.I))
    where = sorted(" ".join([x.tag] + x.classes()) for p in pages.values() for x in p["root"].walk()
                   if any(isinstance(c, str) and re.search(r"paperback", c, re.I) for c in x.children))
    report(n == 2 and where == ["p po-amt", "p po-was"], "PR-01",
           "'paperback' only in the price box label and price line",
           f"found {n}: {', '.join(where) or 'none'}")

    bad = []
    for name, p in pages.items():
        for m in re.finditer(r"(?:US\$|CA\$|C\$|\bCAD\b|\bUSD\b|\$)\s?\d[\d.,]*[A-Za-z]?", p["wording"]):
            amount = norm(m.group(0))
            if amount not in ("USD 79", "$2.3T"):  # $2.3T is the cost-of-failure statistic
                bad.append(f"{name}: '{amount}'")
    report(not bad, "PR-01", "Every price on the site is USD 79", ", ".join(bad) or "ok")

    gone = [r"\bCAD\b", r"\bGST\b", r"\bPST\b", r"\bHST\b", r"\bVAT\b", r"\btax(?:es)? included",
            r"\bincl\.? tax", r"nothing added at checkout", r"includes GST", r"\$\s?39\b", r"\$\s?79\b"]
    bad = [f"{name}: /{g}/" for name, p in pages.items() for g in gone
           if re.search(g, p["wording"], re.I)]
    report(not bad, "PR-01", "No CAD, $39, $79 without USD, or GST-included wording",
           ", ".join(bad) or "ok")

    head = idx.find_all(lambda n: n.tag == "meta" and (
        n.attrs.get("name") in ("description", "twitter:description")
        or n.attrs.get("property") == "og:description"))
    bad = [m.attrs.get("name") or m.attrs.get("property") for m in head
           if not (m.attrs.get("content") or "").endswith(" Out now.")]
    report(len(head) == 3 and not bad, "PR-01", "Page and share descriptions end 'Out now.'",
           ", ".join(bad) or f"{len(head)} checked")
    label = [text(n) for n in idx.find_all(lambda n: "hero-date" in n.classes())]
    report(label == ["Out now"], "PR-01", "Hero label reads 'Out now'", f"got {label}")


def in_event_band(n):
    return n.tag == "section" and n.attrs.get("id") == "event"


def check_pr02(pages):
    gone = {
        "launching / launches": r"\blaunch(?:ing|es)\b",
        "launch offer": r"launch offer",
        "pre-order": r"\bpre-?order",
        "reserve": r"\breserv",
        "signed / signing / autograph": r"\bsign(?:ed|ing)\b|\bautograph",
        "inscribed / inscription": r"\binscri",
        "until midnight": r"until midnight",
        "on the night": r"on the night",
        "collect / pickup": r"\bcollect(?:ed)? (?:a|at|in)\b|\bpick-?up\b",
        "seats are limited": r"seats are limited",
        "free registration": r"free registration",
    }
    for name, p in pages.items():
        found = [label for label, rx in gone.items() if re.search(rx, p["wording"], re.I)]
        report(not found, "PR-02", f"{name}: no offer, pre-order or signed-copy wording",
               ", ".join(found) or "ok")
    for name, p in pages.items():
        outside = wording(p["root"], skip=in_event_band)
        n = len(re.findall(r"13 August", outside, re.I))
        report(n == 0, "PR-02", f"{name}: '13 August' only in the past-event record",
               f"{n} outside the event band")
    band = pages["index"]["root"].find_all(in_event_band)
    band_text = wording(band[0]) if band else ""
    missing = [t for t in LAUNCH_RECORD if t not in band_text]
    report(bool(band) and not missing, "PR-02", "Launch record reads in past tense",
           ", ".join(f"missing '{t}'" for t in missing) or "ok")
    present = [rx for rx in (r"\bpresents\b", r"Event ends", r"\bFeaturing\b", r"\bBringing together\b",
                             r"Arrive, connect") if re.search(rx, band_text)]
    report(bool(band) and not present, "PR-02", "No present-tense lines left in the launch record",
           ", ".join(f"/{rx}/" for rx in present) or "ok")
    cards = pages["index"]["root"].find_all(lambda n: "pickup" in n.classes())
    report(not cards, "PR-02", "Signed-copy card removed", f"{len(cards)} found")
    html = pages["index"]["html"] + pages["article"]["html"]
    report(OLD_STRIPE_URLS[1] not in html, "PR-02", "CA$39 launch-offer link gone from the pages")


def check_pr03(pages):
    for name, p in pages.items():
        evs, bad = [], []
        for a in p["anchors"]:
            u = urlsplit(a["href"])
            host = u.netloc.lower()
            is_event = host in ("luma.com", "lu.ma", "www.luma.com", "prechangeway.com",
                                "www.prechangeway.com") or a["raw"] == "#event"
            if not is_event or (a["href"], a["text"]) == PRECHANGE_HOME or feed_link(a):
                continue
            if a["href"] == PHOTOS_URL:
                if a["text"] != PHOTOS_TEXT:
                    bad.append(f"photos link text '{a['text']}'")
                continue
            evs.append(a)
            if a["href"] != EVENTS_URL or a["text"] != EVENT_TEXT:
                bad.append(f"'{a['text']}' -> {a['raw']}")
        want = {"index": 4, "article": 2}[name]
        report(not bad and len(evs) == want, "PR-03",
               f"{name}: every event link is '{EVENT_TEXT}' -> /events",
               "; ".join(bad) or f"{len(evs)} of {want}")
        reg = re.findall(r"\bRegister\b[^.]{0,30}", p["wording"])
        report(not reg, "PR-03", f"{name}: no 'Register...' button text left",
               ", ".join(reg) or "ok")

    idx, art = pages["index"]["root"], pages["article"]["root"]

    def first(root, pred):
        found = root.find_all(pred)
        return found[0] if found else None

    def link_ok(a):
        return a is not None and a.attrs.get("href") == EVENTS_URL and text(a) == EVENT_TEXT

    spots = {
        "menu button (index 381)": first(idx, lambda n: n.tag == "a" and "nav-cta" in n.classes()),
        "hero button (index 397)": first(idx, lambda n: n.tag == "a" and any(
            "hero-btns" in x.classes() for x in n.ancestors())),
        "event band button (index 710)": first(idx, lambda n: n.tag == "a" and "btn-gold" in n.classes()
                                               and any(in_event_band(x) for x in n.ancestors())),
        "footer link (index 840)": first(idx, lambda n: n.tag == "a" and text(n) in ("Events", EVENT_TEXT)
                                         and any(x.tag == "footer" for x in n.ancestors())),
        "article top bar (article 154)": first(art, lambda n: n.tag == "a" and "cta" in n.classes()),
        "article end (article 212)": first(art, lambda n: n.tag == "a" and any(
            "a-cta" in x.classes() for x in n.ancestors())),
    }
    for where, a in spots.items():
        got = "missing" if a is None else f"'{text(a)}' -> {a.attrs.get('href')}"
        report(link_ok(a), "PR-03", where, got)
    photos = [a for a in pages["index"]["anchors"] if a["href"] == PHOTOS_URL and a["text"] == PHOTOS_TEXT]
    report(len(photos) == 1, "PR-03", "'Photos from the launch' -> /events#spotlight-...",
           f"found {len(photos)}")

    band = idx.find_all(in_event_band)
    report(bool(band) and ONLINE_LINE in text(band[0]), "PR-03", f"Event band says '{ONLINE_LINE}'")
    cta = art.find_all(lambda n: "a-cta" in n.classes())
    report(bool(cta) and ARTICLE_SESSIONS in text(cta[0]), "PR-03", "Article end says 'online and in person'",
           text(cta[0])[:80] if cta else "missing")
    stale = [name for name, p in pages.items() if re.search(r"online and in Saskatoon", p["wording"], re.I)]
    report(not stale, "PR-03", "No 'online and in Saskatoon' left", ", ".join(stale) or "ok")
    check_layout(BASE_URL)


LAYOUT_HARNESS = r"""
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
    await send('Page.enable'); await send('Network.enable');
    await send('Network.setBlockedURLs', { urls: ['*googletagmanager.com*', '*google-analytics.com*',
      '*analytics.google.com*', '*cloudflareinsights.com*', '*doubleclick.net*'] });
    const out = [];
    for (const c of input.cases) {
      await send('Emulation.setDeviceMetricsOverride', { width: c.width, height: 844, deviceScaleFactor: 1, mobile: c.width < 768 });
      const loaded = new Promise(r => events.push(function f(m) {
        if (m.method === 'Page.loadEventFired') { events.splice(events.indexOf(f), 1); r(); } }));
      await send('Page.navigate', { url: input.base + c.path }); await loaded;
      await send('Runtime.evaluate', { expression: 'document.fonts.ready.then(() => 1)', awaitPromise: true });
      await sleep(300);
      const v = (await send('Runtime.evaluate', { returnByValue: true, expression: `(() => {
        const e = document.querySelector(${JSON.stringify(c.selector)});
        const d = document.documentElement, over = d.scrollWidth - d.clientWidth;
        if (!e) return { lines: 0, text: null, over };
        const r = document.createRange(); r.selectNodeContents(e);
        const tops = new Set([...r.getClientRects()].filter(x => x.width > 0).map(x => Math.round(x.top)));
        return { lines: tops.size, text: e.textContent.trim(), over }; })()` })).result.value;
      out.push(Object.assign({}, c, v));
    }
    console.log(JSON.stringify(out)); ws.close();
  } finally { chrome.kill(); }
})().catch(e => { console.error(e.message); process.exit(1); });
"""


def check_layout(base):
    """'Upcoming Events' stays on one line, and no page scrolls sideways (real browser)."""
    if not os.path.exists(CHROME):
        die(f"Chrome not found at {CHROME} (set CHROME) for the PR-03 layout checks")
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    profile = tempfile.mkdtemp(prefix="check-layout-")
    cases = ([{"path": "/article", "width": w, "selector": ".top .cta"} for w in (360, 375, 390, 393, 400, 430)]
             + [{"path": "/", "width": w, "selector": "#nav .nav-cta"} for w in (1000, 1010, 1024, 1100, 1280, 1440)]
             + [{"path": "/", "width": w, "selector": "#nav .nav-cta", "scroll_only": True} for w in (360, 390, 700, 800)])
    try:
        r = subprocess.run(["node", "-e", LAYOUT_HARNESS], capture_output=True, text=True, timeout=300,
                           input=json.dumps({"chrome": CHROME, "port": port, "profile": profile,
                                             "base": base, "cases": cases}))
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    if r.returncode != 0:
        die(f"layout check failed to run: {r.stderr.strip()[:300]}")
    res = json.loads(r.stdout)
    for path, label in (("/article", "Article top bar"), ("/", "Menu")):
        rows = [x for x in res if x["path"] == path and not x.get("scroll_only")]
        bad = [f"{x['width']}px: {x['lines']} lines" for x in rows if x["lines"] != 1 or x["text"] != EVENT_TEXT]
        report(not bad, "PR-03", f"{label}: '{EVENT_TEXT}' on one line at {rows[0]['width']}-{rows[-1]['width']} px",
               ", ".join(bad) or "ok")
    over = [f"{x['path']} {x['width']}px: {x['over']}px" for x in res if x["over"] > 0]
    report(not over, "PR-03", "No sideways scroll (360-1440 px)",
           ", ".join(over) or f"{len(res)} page widths checked")


EXTRA_HREFS = {EVENTS_URL, PHOTOS_URL, NEW_STRIPE_URL}  # link targets this change adds
REMOVED_HREFS = {"index.html": ["https://www.amazon.in/dp/1998440575", OLD_STRIPE_URLS[1]],
                 "article.html": []}
# The only CSS edits allowed: the buy grid, and keeping "Upcoming Events" on one line.
CSS_CHANGES = {
    "index.html": [
        (".po-opts{display:grid;grid-template-columns:repeat(3,1fr);",
         ".po-opts{display:grid;grid-template-columns:repeat(2,1fr);"),
        (".nav-links{display:flex;gap:2rem;align-items:center}",
         ".nav-links{display:flex;gap:clamp(1.2rem,2.2vw,2rem);align-items:center}"),
    ],
    "article.html": [
        ("padding:.5rem 1.1rem;text-decoration:none}",
         "padding:.5rem 1.1rem;text-decoration:none;white-space:nowrap}"),
    ],
}
JS_CHANGE = ("a.href&&a.href.indexOf('luma.com/ygmx2yww')>-1",
             "a.href==='https://prechangeway.com/events'")
DESCRIPTIONS = {"description", "og:description", "twitter:description"}
FORM_TAGS = {"form", "input", "button", "textarea", "select", "iframe", "object", "embed",
             "video", "audio", "source"}


def _fixed_parts(html):
    """Parts of a page that this change may not touch, apart from the approved edits."""
    root = parse(html)

    def raw(n):
        return "".join(c for c in n.children if isinstance(c, str))

    def meta_key(n):
        named = n.attrs.get("name") or n.attrs.get("property")
        return tuple(sorted((k, v) for k, v in n.attrs.items()
                            if not (k == "content" and named in DESCRIPTIONS)))

    return {
        "CSS": [raw(n) for n in root.find_all(lambda n: n.tag == "style")],
        "inline scripts": [raw(n) for n in root.find_all(
            lambda n: n.tag == "script" and "src" not in n.attrs)],
        "external scripts": [n.attrs["src"] for n in root.find_all(
            lambda n: n.tag == "script" and "src" in n.attrs)],
        "images": [(n.attrs.get("src"), n.attrs.get("alt")) for n in root.find_all(lambda n: n.tag == "img")],
        "head links": [tuple(sorted(n.attrs.items())) for n in root.find_all(lambda n: n.tag == "link")],
        "meta tags": [meta_key(n) for n in root.find_all(lambda n: n.tag == "meta")],
        "forms and embeds": [(n.tag, tuple(sorted(n.attrs.items())))
                             for n in root.find_all(lambda n: n.tag in FORM_TAGS)],
        "hrefs": [n.attrs.get("href") for n in root.find_all(lambda n: n.tag == "a" and "href" in n.attrs)],
    }


def pr04_problems(path, old_html, new_html):
    """Every way new_html differs from main beyond the approved change; [] if none."""
    problems = []
    old, new = old_html.splitlines(), new_html.splitlines()
    sm = difflib.SequenceMatcher(None, old, new, autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        if op == "insert":  # this change only rewrites or removes lines, never adds them
            problems.append(f"line added after main line {i1}: {new[j1].strip()[:50]!r}")
            continue
        if op == "replace" and j2 - j1 > i2 - i1:
            problems.append(f"main lines {i1 + 1}-{i2} grew from {i2 - i1} to {j2 - j1} lines")
        if op == "delete":
            # A removed block next to identical lines (e.g. "</div>") can be
            # placed several ways with the same result; accept any placement
            # that falls on approved lines, as git's diff slider would.
            spots, a, b = [(i1, i2)], i1, i2
            while a > 0 and old[a - 1] == old[b - 1]:
                a, b = a - 1, b - 1
                spots.append((a, b))
            a, b = i1, i2
            while b < len(old) and old[a] == old[b]:
                a, b = a + 1, b + 1
                spots.append((a, b))
            if any(all(ln in ALLOWED[path] for ln in range(s + 1, e + 1)) for s, e in spots):
                continue
        for ln in range(i1 + 1, i2 + 1):
            if ln not in ALLOWED[path]:
                problems.append(f"main line {ln} changed: {old[ln - 1].strip()[:50]!r}")

    o, n = _fixed_parts(old_html), _fixed_parts(new_html)
    want_css, want_js = list(o["CSS"]), o["inline scripts"]
    for old_rule, new_rule in CSS_CHANGES[path]:
        if sum(c.count(old_rule) for c in want_css) != 1:
            problems.append(f"main's CSS rule not found once: {old_rule[:40]!r}")
        want_css = [c.replace(old_rule, new_rule) for c in want_css]
    if path == "index.html":
        want_js = [s.replace(*JS_CHANGE) for s in o["inline scripts"]]
        if want_js == o["inline scripts"]:
            problems.append("main's register_click match not found")
    if n["CSS"] != want_css:
        problems.append("CSS differs from main beyond the approved edits")
    if n["inline scripts"] != want_js:
        problems.append("inline scripts differ from main beyond the register_click match")
    for k in ("external scripts", "images", "head links", "meta tags", "forms and embeds"):
        if n[k] != o[k]:
            problems.append(f"{k} differ from main")
    extra = [h for h in n["hrefs"] if h not in set(o["hrefs"]) | EXTRA_HREFS]
    if extra:
        problems.append(f"new link targets: {extra[:3]}")
    want = len(o["hrefs"]) - sum(1 for h in REMOVED_HREFS[path] if h in o["hrefs"])
    if len(n["hrefs"]) != want:
        problems.append(f"{len(n['hrefs'])} links, expected {want}")
    return problems


def _after_line(pattern, line):
    def plant(html):
        lines = html.split("\n")
        for i, l in enumerate(lines):
            if re.search(pattern, l):
                return "\n".join(lines[:i + 1] + [line] + lines[i + 1:])
        return html
    return plant


# Edits that must never get past PR-04; the self-test plants each one.
PLANTED = {
    "script after the meta description": _after_line(
        r'<meta name="description"', '<script src="https://example.com/x.js"></script>'),
    "second CSS rule after the grid": _after_line(r"^\.po-opts\{", ".po-opt{padding:0}"),
    "different menu gap on an approved line": lambda h: h.replace(
        "gap:clamp(1.2rem,2.2vw,2rem)", "gap:1rem", 1),
    "extra gtag event after register_click": _after_line(
        r"gtag\('event','register_click'", "    gtag('event','purchase',{});"),
    "new link after a footer link": _after_line(
        r'href="#po-terms"', '      <a href="https://example.com/">Example</a>'),
    "image added on an approved line": lambda h: re.sub(
        r'(<p class="hero-date">[^<]*</p>)', r'\1<img src="https://example.com/p.gif" alt="">', h, count=1),
    "extra link on an approved line": lambda h: h.replace(
        "Upcoming Events</a>", 'Upcoming Events</a> <a href="#preorder">Buy</a>', 1),
    "edit on an unapproved line": lambda h: h.replace("Annual cost of failure", "Annual cost of failures", 1),
    "#preorder anchor renamed": lambda h: h.replace('id="preorder"', 'id="buy"', 1),
}


def check_pr04(pages):
    try:
        changed = set(git("diff", "--name-only", MAIN_REF, "HEAD").split())
        dirty = git("status", "--porcelain", "--untracked-files=no").strip()
    except subprocess.CalledProcessError as e:
        die(f"git failed: {e.stderr.strip()}")
    extra = sorted(f for f in changed if not f.startswith("tests/") and f not in FILES_ALLOWED_TO_CHANGE)
    report(not extra, "PR-04", f"Checkout: only index.html, article.html, tests/ changed since {MAIN_REF}",
           ", ".join(extra) or f"{len(changed)} files changed")
    report(not dirty, "PR-04", "Checkout: no uncommitted changes to tracked files",
           dirty.replace("\n", ", ")[:80] or "clean")

    mains = {}
    for name, path in (("index", "index.html"), ("article", "article.html")):
        mains[path] = git("show", f"{MAIN_REF}:{path}")
        probs = pr04_problems(path, mains[path], pages[name]["html"])
        report(not probs, "PR-04", f"{path}: nothing differs from main but approved edits",
               "; ".join(probs[:4]) or "ok")

    old_css = mains["index.html"].splitlines()[279]
    want = old_css.replace("repeat(3,1fr)", "repeat(2,1fr)")
    served = [l for l in pages["index"]["html"].splitlines() if l.startswith(".po-opts{")]
    report(want != old_css and served == [want], "PR-04", "Buy grid is 2 columns",
           served[0][:70] if served else "rule missing")

    html = pages["index"]["html"]
    if pr04_problems("index.html", mains["index.html"], html):
        report(False, "PR-04", "Self-test: planted edits are caught", "needs a page that passes first")
        return
    missed = []
    for label, plant in PLANTED.items():
        planted = plant(html)
        if planted == html:
            missed.append(f"{label} (could not plant)")
        elif not pr04_problems("index.html", mains["index.html"], planted):
            missed.append(label)
    report(not missed, "PR-04", f"Self-test: all {len(PLANTED)} planted edits are caught",
           ", ".join(missed) or "ok")


def check_pr05(pages):
    idx = pages["index"]
    buys = [a for a in idx["anchors"] if "data-buy" in a["node"].attrs]
    ok = len(buys) == 1 and buys[0]["href"] == NEW_STRIPE_URL and buys[0]["text"] == BUY_TEXT
    report(ok, "PR-05", f"One buy button: '{BUY_TEXT}' -> new Stripe link",
           "; ".join(f"'{a['text']}' -> {a['raw']}" for a in buys) or "none")
    html = idx["html"] + pages["article"]["html"]
    links = sorted(set(re.findall(r"https://buy\.stripe\.com/\w+", html)))
    report(links == [NEW_STRIPE_URL], "PR-05", "No other Stripe link on the pages", ", ".join(links))
    hrefs = [a["href"] for a in idx["anchors"]]
    report(not any("amazon.in" in h for h in hrefs), "PR-05", "Amazon India link removed")
    keep = ["https://www.amazon.ca/dp/1998440575", "https://www.amazon.com/dp/1998440575",
            "https://www.amazon.co.uk/dp/1998440575"]
    missing = [k for k in keep if hrefs.count(k) != 1]
    report(not missing, "PR-05", "Amazon .ca, .com and .co.uk links kept", ", ".join(missing) or "ok")


NODE_HARNESS = r"""
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));
let onClick = null; const calls = [];
const noop = () => {};
const el = { classList: { toggle: noop, add: noop, remove: noop } };
const sandbox = {
  document: { addEventListener: (t, f) => { if (t === 'click') onClick = f; },
              querySelectorAll: () => [], getElementById: () => el },
  addEventListener: noop, scrollY: 0,
  IntersectionObserver: class { observe() {} unobserve() {} },
  console: { log: noop, warn: noop, error: noop },
  gtag: (...a) => calls.push(a),
};
sandbox.window = sandbox;
require('vm').runInNewContext(input.script, sandbox);
const out = input.anchors.map(a => {
  const before = calls.length;
  const node = { href: a.href, textContent: a.text,
                 hasAttribute: n => Object.prototype.hasOwnProperty.call(a.attrs, n),
                 getAttribute: n => (n in a.attrs ? a.attrs[n] : null) };
  if (onClick) onClick({ target: { closest: () => node } });
  return calls.slice(before).filter(c => c[0] === 'event').map(c => ({ name: c[1], params: c[2] || {} }));
});
console.log(JSON.stringify({ handler: !!onClick, events: out }));
"""


def check_pr06(pages):
    idx = pages["index"]
    scripts = [text_raw for text_raw in
               (" ".join(c for c in s.children if isinstance(c, str))
                for s in idx["root"].find_all(lambda n: n.tag == "script" and "src" not in n.attrs))
               if "register_click" in text_raw]
    if len(scripts) != 1:
        report(False, "PR-06", "Click-tracking script found", f"{len(scripts)} scripts mention register_click")
        return
    def text_content(n):  # what the browser's a.textContent returns
        return "".join(c if isinstance(c, str) else text_content(c) for c in n.children)

    anchors_in = [{"href": a["href"], "text": text_content(a["node"]),
                   "attrs": {k: (v if v is not None else "") for k, v in a["node"].attrs.items()}}
                  for a in idx["anchors"]]
    try:
        r = subprocess.run(["node", "-e", NODE_HARNESS], input=json.dumps(
            {"script": scripts[0], "anchors": anchors_in}), capture_output=True, text=True, timeout=30)
    except FileNotFoundError:
        die("node is needed for the PR-06 checks")
    if r.returncode != 0:
        die(f"node harness failed: {r.stderr.strip()[:300]}")
    res = json.loads(r.stdout)
    fired = [(a["href"], e) for a, evs in zip(idx["anchors"], res["events"]) for e in evs
             if e["name"] == "register_click"]
    want = [a["href"] for a in idx["anchors"] if a["href"] == EVENTS_URL or upcoming_link(a)]
    report(res["handler"] and len(want) >= 1 and sorted(h for h, _ in fired) == sorted(want),
           "PR-06", "register_click fires for every /events link and upcoming event, only those",
           f"{len(fired)} fired, {len(want)} /events links; fired for: "
           + (", ".join(sorted(set(h for h, _ in fired))) or "none"))
    report(all(e["params"].get("link_url") == h for h, e in fired) and fired, "PR-06",
           "register_click sends the link address", "ok" if fired else "nothing fired")
    buys = [e for a, evs in zip(idx["anchors"], res["events"]) for e in evs if e["name"] == "begin_checkout"]
    report(len(buys) == 1 and buys[0]["params"].get("option") == BUY_TEXT
           and buys[0]["params"].get("link_url") == NEW_STRIPE_URL, "PR-06",
           "begin_checkout still fires for the buy button",
           json.dumps(buys[0]["params"], ensure_ascii=False) if buys else "none")


def main():
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} <base-url>", file=sys.stderr)
        sys.exit(2)
    global BASE_URL
    base = BASE_URL = sys.argv[1].rstrip("/")
    pages = {}
    for name, path in (("index", "/"), ("article", "/article")):
        url = base + path
        try:
            html = fetch(url)
        except Exception as e:  # noqa: BLE001 - any fetch problem means the test can't run
            die(f"cannot fetch {url}: {e}")
        root = parse(html)
        pages[name] = {"html": html, "root": root, "wording": wording(root),
                       "anchors": anchors(root, url)}

    print(f"Checking {base} (main reference {MAIN_REF})\n")
    for fn in (check_pr01, check_pr02, check_pr03, check_pr04, check_pr05, check_pr06):
        fn(pages)
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
