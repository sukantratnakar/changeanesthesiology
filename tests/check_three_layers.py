#!/usr/bin/env python3
"""Checks Prechange, Change Anesthesiology and Morphosis on the home page (TL-01 to TL-09).

Q08 v2, 16 Oct 2026. Decisions D28 and D29-1 to D29-9.

Usage:  python3 tests/check_three_layers.py <base-url>
  e.g.  python3 tests/check_three_layers.py https://content-where-this-fits-changeanesthesiology.sukantratnakar.workers.dev

Fetches / and /article from the base URL and prints one PASS/FAIL line per
check. Exits 1 if any check fails, 2 if the test itself can't run.
Fetches pages with urllib only (no browser), so it does not trigger Google
Analytics; the TL-06 layout checks use headless Chrome with analytics blocked.
TL-05 compares the served pages with BASE_REF (default 4deca4e, main before
this change) plus exactly the approved edits from the git checkout this script lives in, and runs the Q04 and
Q06 tests against the same base URL: all of their checks must pass except
Q06's PR-04, which TL-05 replaces. Node and Chrome must be installed.
"""

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from collections import Counter
from difflib import SequenceMatcher

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_price_and_events as q06  # noqa: E402  (shared parser, fetch and browser harness)

from check_price_and_events import norm, parse, text, wording  # noqa: E402

q06.UA = "check_three_layers.py (changeanesthesiology repo test)"
TESTS = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TESTS)
BASE_REF = os.environ.get("BASE_REF", "4deca4e")

# --- the wording Sukant approved (Q08 v2), word for word --------------------

HERO = ("The profession has spent decades trying to overcome resistance to change. "
        "What if it has been fighting the wrong war?")
PREMISE_START = ("What if instead of building ever more sophisticated strategies to overcome resistance, "
                 "we could dissolve the conditions that create it — so resistance never forms in the "
                 "first place? Not by persuading people or training them or pressuring them.")
PREMISE_END = ("By addressing the upstream conditions — energy, headroom, perspective and routines — "
               "that shape whether a human system resists or adapts.")
STATS = [
    ("Energy", "Decides whether people can invest or must conserve."),
    ("Headroom", "Decides whether there is room to think and take on more."),
    ("Perspective", "Shapes whether a change looks like a threat or a problem to solve."),
    ("Routines", "Decide whether a change holds or quietly slips back."),
]
BIO = ("Iknetix proposed that ideas carry kinetic energy — and that sharing between humans increases "
       "that energy exponentially. ZERO argued that organisations can no longer refreeze after each "
       "change; they must learn to stay liquid permanently. White Space Thinking examined how the "
       "cognitive gaps essential for reflection have been structurally eliminated from modern work.")
MORPH_LEAD = ("Five daily practices designed to build the four conditions Prechange measures before "
              "each change: energy, headroom, perspective and routines. Not workshops that happen once "
              "and fade. Embedded, daily, self-administered practices.")
MORPH_CARDS = [
    ("White Space Thinking", "Zone 1 · Broaden · Headroom"),
    ("Perspective Thinking", "Zone 1 · Broaden · Perspective"),
    ("OmniMeta Mindfulness", "Zone 2 · Expand · Headroom"),
    ("Tinergy & Energy", "Zone 2 · Expand · Energy, with OmniMeta's BOSE scan"),
    ("The Habit Machine", "Zone 4 · Increase · Routines"),
]
WST = ("Creates headroom — the pause where reflection becomes possible. Without it, there is no room "
       "for a new perspective to enter. Modern work has squeezed these gaps out of the day.")
HABIT_END = ("Made in Canada. Because about 43% of what people do each day is done out of habit — "
             "and routines decide whether gains hold or slip back.")
SPEAKER = ("Why Resistance Is Never the Problem argues that the profession has been treating the wrong "
           "condition. Resistance is not the obstacle — it is often a signal. The real work happens "
           "before any initiative arrives, building the energy, headroom, perspective and routines "
           "whose absence makes resistance likely.")
ZONE3 = ("No tool. No workshop. No framework. This zone has no intervention. When the upstream "
         "conditions are in place, much of the resistance never forms. Disagreement that remains may "
         "be informed dissent, and worth hearing. The empty zone is not a gap in the methodology. "
         "It is the methodology.")
TOOLKIT3 = ("The philosophy in practice. When the upstream conditions are in place, much of the "
            "resistance never forms.")

BAND_TAG = "Where this fits"
BAND_HEAD = "Three layers. One system."
ONE_SENTENCE = ("Prechange names the stage. Change Anesthesiology explains why it matters. "
                "Morphosis builds the conditions, every day.")
# Design v3 of the figure (Sukant, 17 Oct 2026, D56; screen-reader wording D57): a picture of time
# around one change. Each part's words, in reading order.
V3 = {
    "why": ("Why", "Change Anesthesiology", "This book", "The philosophy and the model · four zones",
            "People adapt when the conditions around them let them. Resistance is often a signal that those "
            "conditions are missing."),
    "when": ("When", "Before each change", "Prechange", "The stage before each change, and its measure, the Check."),
    "bars": ["Energy", "Headroom", "Perspective", "Routines"],
    "note": "The Check finds the weakest condition; a focused boost builds it before launch.",
    "launch": "Change launches",
    "depth": ("Depth", "During and after launch", "The Sunfish Paradox",
              "Carrying out change, and keeping it from slipping back after launch."),
    "legend": ["The change holds", "Without it, it slips back"],
    "how": ("How", "Morphosis", "Every day, before, during and after",
            "Five daily practices designed to build the four conditions."),
    "practices": ["Tinergy", "White Space Thinking", "OmniMeta Mindfulness", "Perspective Thinking", "Habit Machine"],
    "found": ("Foundation", "Iknetix and ZERO", "The author's earlier books. Iknetix also feeds the perspective tools."),
}
THIS_BOOK = "This book"
FIG_TEXT = norm(" ".join(
    [V3["why"][0], V3["why"][1], V3["why"][2], V3["why"][3], V3["why"][4]]
    + list(V3["when"]) + V3["bars"] + [V3["note"], V3["launch"]]
    + list(V3["depth"]) + V3["legend"]
    + list(V3["how"]) + V3["practices"] + list(V3["found"])))
TEMPOS = ("Every day Morphosis / Before each change the Prechange Check, then a boost on the weakest "
          "condition / During and after launch sustaining, through Zone 4 and The Sunfish Paradox")
EVIDENCE = ("The evidence supports each of these mechanisms on its own. Whether building all four "
            "conditions before a change improves adoption still needs independent research.")
PRECHANGE_URL = "https://prechangeway.com"
LINK_TEXT = "Read about Prechange at prechangeway.com →"
FIG_DESC = ("A picture of time around one change. Over everything, the why: Change Anesthesiology, the "
            "philosophy and the model. On the timeline, before the change launches: Prechange, the stage before "
            "each change, where the Check measures energy, headroom, perspective and routines, finds the "
            "weakest, and a focused boost builds it. After the change launches: The Sunfish Paradox, on "
            "carrying out change and keeping it from slipping back. Running underneath the whole timeline, "
            "every day: Morphosis, five daily practices, each designed to build one of the four conditions. "
            "At the base, the foundation: Iknetix and ZERO, the author's earlier books.")
# Everything the band says, in order: nothing more, nothing less (TL-02).
BAND_TEXT = norm(" ".join([BAND_TAG, BAND_HEAD, ONE_SENTENCE, FIG_TEXT, FIG_DESC, TEMPOS, EVIDENCE, LINK_TEXT]))

# TL-04: claims that must not appear anywhere in either page (meta tags included).
BANNED = ["70%", "Seventy percent", "$2.3", "trillion", "12%", "ego depletion", "Lewin",
          "three steps", "boosts executive function", "prehabilitation", "pilot", "45%"]

# TL-03: the four conditions, in their public order.
CONDITIONS = [("energy", r"\benerg(?:y|ies)\b"), ("headroom", r"\bheadroom\b"),
              ("perspective", r"\bperspectives?\b"), ("routines", r"\broutines?\b")]
HABIT_OK = [r"\bhabit machine\b", r"\bdone out of habit\b", r"\bdaily habit tracker\b"]
NOT_ALWAYS = r"\balways a signal\b|\bis the signal\b|\bresistance is always\b"

# TL-05: the only edits this change may make to BASE_REF's index.html, as
# (source before, source after). Apart from these, the page must be the same,
# plus two blocks this change adds whole: the new CSS (just before "reveal")
# and the band itself (right after #morphosis), whose text must be BAND_TEXT.
APPROVED_EDITS = [
    ('Seventy percent of change initiatives fail. The number has not moved in twenty years. '
     'What if the profession has been fighting the wrong war?', HERO),                       # item 1
    ("perspective, energy, capacity, habit — that determine whether",
     "energy, headroom, perspective and routines — that shape whether"),                    # item 2
    ('<div class="stats reveal" style="margin-top:4rem">\n'
     '      <div class="stat"><b>70%</b><span>Change initiatives fail</span></div>\n'
     '      <div class="stat"><b>20+</b><span>Years unchanged</span></div>\n'
     '      <div class="stat"><b>$2.3T</b><span>Annual cost of failure</span></div>\n'
     '      <div class="stat"><b>12%</b><span>Sustain beyond 3 years</span></div>',
     '<div class="stats words reveal" style="margin-top:4rem">\n'
     + "\n".join(f'      <div class="stat"><b>{a}</b><span>{b}</span></div>' for a, b in STATS)),  # item 3
    ("<em>Iknetix</em> demonstrated that", "<em>Iknetix</em> proposed that"),               # item 4
    ("<em>ZERO</em> argued that Lewin's refreeze is dead and organisations must learn to stay liquid permanently.",
     "<em>ZERO</em> argued that organisations can no longer refreeze after each change; "
     "they must learn to stay liquid permanently."),
    ("<em>White Space Thinking</em> revealed how", "<em>White Space Thinking</em> examined how"),
    ("Five capabilities that, when practiced daily, expand the human system's capacity to absorb continuous "
     "change without resistance. Not workshops that happen once and fade. Embedded, daily, self-administered "
     "practices.", MORPH_LEAD),                                                                # item 5
] + [(f'<p class="dim-z">{zone}</p><h3>{name}</h3>',
      f'<p class="dim-z">{zone} <span class="cond">· {label.split(" · ", 2)[2]}</span></p><h3>{name}</h3>')
     for (name, label), zone in zip([(n.replace("&", "&amp;"), l) for n, l in MORPH_CARDS],
                                    ["Zone 1 · Broaden", "Zone 1 · Broaden", "Zone 2 · Expand",
                                     "Zone 2 · Expand", "Zone 4 · Increase"])] + [               # item 6
    ("Creates the cognitive gap — the pause where reflection becomes possible. Without the gap, there is no "
     "room for a new perspective to enter. Modern work has not just eliminated these gaps. It has "
     "structurally damaged the brain's ability to think.", WST),                               # item 7
    ("Made in Canada. Because 45% of daily behaviour is habitual — and habits determine whether gains "
     "persist or decay.", HABIT_END),                                                          # item 8
    ("Resistance is not the obstacle &mdash; it is the signal. The real work happens before any initiative "
     "arrives, dissolving the depleted energy, narrowed perspectives, and cognitive overload that make "
     "resistance inevitable.", SPEAKER.split("condition. ", 1)[1].replace(" — ", " &mdash; ")),  # item 9
    ("Resistance dissolves when the upstream conditions are addressed.",
     "When the upstream conditions are in place, much of the resistance never forms. Disagreement that "
     "remains may be informed dissent, and worth hearing."),                                   # item 10
    ("<p>The philosophy in practice. Resistance dissolves when upstream conditions are addressed.</p>",
     f"<p>{TOOLKIT3}</p>"),
]
CSS_START, CSS_END = "/* ── three layers ── */", "/* ── reveal ── */"
BAND_START = "<!-- ═══ WHERE THIS FITS ═══ -->"
# Selectors the new CSS may style; nothing that already exists on the page.
CSS_PREFIXES = (".fit", "#where-this-fits", ".sr-only", ".stats.words", ".dim-z .cond")
BAND_FORBIDDEN = [r"<style", r"\sstyle=", r"<script", r"<link", r"<iframe", r"<img", r"<svg", r"<canvas",
                  r"<picture", r"<object", r"<embed", r"\son[a-z]+="]
FILES_ALLOWED_TO_CHANGE = {"index.html", "images/sp-cover-flat.jpg"}
REMOVED_IMAGE = "images/sp-cover-flat.jpg"
WIDTHS = (360, 390, 820, 1440)

# --- helpers ------------------------------------------------------------------

RESULTS = []


def report(ok, req, what, detail=""):
    RESULTS.append((req, bool(ok)))
    print(f"{'PASS' if ok else 'FAIL'}  {req}  {what:<56} {detail}".rstrip())


def die(msg):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(2)


def git(*args):
    return subprocess.run(["git", "-C", REPO_ROOT, *args], check=True,
                          capture_output=True, text=True).stdout


def status(url):
    req = urllib.request.Request(url, headers={"User-Agent": q06.UA, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def has_class(*names):
    return lambda n: all(c in n.classes() for c in names)


def first(root, pred):
    found = root.find_all(pred)
    return found[0] if found else None


def section(root, sid):
    return first(root, lambda n: n.tag == "section" and n.attrs.get("id") == sid)


def texts(root, pred):
    return [text(n) for n in root.find_all(pred)]


def own_text(n):
    """Text of one block, without the blocks nested inside it."""
    blocks = {"p", "div", "section", "figure", "figcaption", "ul", "ol", "li", "h1", "h2", "h3",
              "h4", "h5", "h6", "nav", "footer", "header", "article", "blockquote", "form"}
    parts = []
    for c in n.children:
        if isinstance(c, str):
            parts.append(c)
        elif c.tag in blocks or c.tag in ("script", "style"):
            parts.append(" ")
        else:
            parts.append(own_text(c))
    return norm(" ".join(parts))


def tx(n):
    return text(n) if n is not None else ""


def direct(n):
    """Only the words written straight inside n, not inside its child elements."""
    return norm(" ".join(c for c in n.children if isinstance(c, str))) if n is not None else ""


def same(got, want):
    return "ok" if got == want else f"got '{got[:90]}'"


# --- TL-01: Morphosis -----------------------------------------------------------

def check_tl01(pages):
    m = section(pages["index"]["root"], "morphosis")
    if m is None:
        report(False, "TL-01", "#morphosis section found", "missing")
        return
    lead = first(m, has_class("lead"))
    got = text(lead) if lead else ""
    report(got == MORPH_LEAD, "TL-01", "Lead: five practices 'designed to build' the four", same(got, MORPH_LEAD))
    dims = m.find_all(has_class("dim"))
    names = [text(first(d, lambda n: n.tag == "h3") or d) for d in dims]
    labels = [text(first(d, has_class("dim-z")) or d) for d in dims]
    want_names = [n for n, _ in MORPH_CARDS]
    report(names == want_names, "TL-01", "Names the five practices", ", ".join(names))
    bad = [f"{n}: '{l}'" for (n, w), l in zip(MORPH_CARDS, labels) if l != w]
    report(len(labels) == 5 and not bad, "TL-01", "Card labels: book zone, then the condition",
           "; ".join(bad) or " | ".join(labels))
    body = [texts(d, lambda n: n.tag == "p" and not n.classes()) for d in dims]
    got = body[0][-1] if body and body[0] else ""
    report(got == WST, "TL-01", "White Space Thinking card text (item 7)", same(got, WST))
    got = body[-1][-1] if body and body[-1] else ""
    report(len(dims) == 5 and got.endswith(" " + HABIT_END), "TL-01",
           "Habit Machine card ends with the 43% line (item 8)", "ok" if got.endswith(HABIT_END) else f"got '...{got[-90:]}'")


# --- TL-02: the "Where this fits" band ----------------------------------------------

def band(pages):
    return section(pages["index"]["root"], "where-this-fits")


def v3_parts(fig):
    """Each part of the design v3 figure as its words, in the shape of V3."""
    def part(cls):
        return first(fig, has_class(cls)) if fig is not None else None

    def word(node, cls):
        return tx(first(node, has_class(cls))) if node is not None else ""

    why, pc, sf, how, fd, la = (part(c) for c in ("tl3-why", "tl3-pc", "tl3-sf", "tl3-how", "tl3-found", "tl3-launch"))
    spans = lambda node, cls: [tx(n) for n in node.find_all(lambda n: n.tag == "span" and any(  # noqa: E731
        cls in a.classes() for a in n.ancestors()))] if node is not None else []
    return {
        "why": (word(why, "tl3-q"), direct(first(why, has_class("tl3-name"))) if why else "", word(why, "tl3-tag"),
                word(why, "tl3-cap"), word(why, "tl3-txt")),
        "when": (word(pc, "tl3-q"), word(pc, "tl3-cap"), word(pc, "tl3-name"), word(pc, "tl3-txt")),
        "bars": spans(pc, "tl3-barlab"),
        "note": word(pc, "tl3-note"),
        "launch": word(la, "tl3-cap"),
        "depth": (word(sf, "tl3-q"), word(sf, "tl3-cap"), word(sf, "tl3-name"), word(sf, "tl3-txt")),
        "legend": [s for s in spans(sf, "tl3-legend") if s],
        "how": (word(how, "tl3-q"), word(how, "tl3-name"), word(how, "tl3-cap"), word(how, "tl3-txt")),
        "practices": [tx(n) for n in how.find_all(lambda n: n.tag == "li")] if how is not None else [],
        "found": (word(fd, "tl3-cap"), word(fd, "tl3-name"), word(fd, "tl3-txt")),
    }


def check_tl02(pages):
    root = pages["index"]["root"]
    b = band(pages)
    secs = [n.attrs.get("id") or "(no id)" for n in root.find_all(lambda n: n.tag == "section")]
    i = secs.index("morphosis") if "morphosis" in secs else -1
    nxt = secs[i + 1] if 0 <= i < len(secs) - 1 else "nothing"
    report(b is not None and nxt == "where-this-fits", "TL-02", "id=\"where-this-fits\" right after #morphosis",
           f"next section after #morphosis: {nxt}")
    if b is None:
        return
    line = first(b, has_class("fit-line"))
    got = text(line) if line else ""
    report(got == ONE_SENTENCE, "TL-02", "The one sentence, word for word", same(got, ONE_SENTENCE))
    fig = first(b, lambda n: n.tag == "figure")
    parts = v3_parts(fig)
    names = (parts["why"][1], parts["when"][2], parts["how"][1])
    report(names == ("Change Anesthesiology", "Prechange", "Morphosis"), "TL-02",
           "Three layers: Change Anesthesiology (why), Prechange (when), Morphosis (how)", ", ".join(names))
    report(parts["depth"][2] == "The Sunfish Paradox", "TL-02", "The Sunfish Paradox (depth) after the launch",
           parts["depth"][2] or "missing")
    report(parts["found"][1] == "Iknetix and ZERO", "TL-02", "Foundation: Iknetix and ZERO", parts["found"][1] or "missing")
    tempo = first(b, has_class("fit-tempo"))
    got = text(tempo) if tempo else ""
    report(got == TEMPOS, "TL-02", "Tempos line", same(got, TEMPOS))
    note = first(b, has_class("fit-note"))
    got = text(note) if note else ""
    report(got == EVIDENCE, "TL-02", "Evidence line exactly as in item 11", same(got, EVIDENCE))
    links = [(a.attrs.get("href"), text(a)) for a in b.find_all(lambda n: n.tag == "a")]
    report(links == [(PRECHANGE_URL, LINK_TEXT)], "TL-02", "One link: 'Read about Prechange…' -> prechangeway.com",
           "; ".join(f"'{t}' -> {h}" for h, t in links) or "none")
    figs = b.find_all(lambda n: n.tag == "figure")
    report(len(figs) == 1 and not b.find_all(has_class("tempo")), "TL-02", "No tempo diagram (one figure only)",
           f"{len(figs)} figures")
    got = text(b)
    report(got == BAND_TEXT, "TL-02", "The band says exactly the approved text, nothing more",
           "ok" if got == BAND_TEXT else f"{len(got)} characters, expected {len(BAND_TEXT)}")


# --- TL-03: the four conditions, in order; "habit" is never a condition ----------

def check_tl03(pages):
    root = pages["index"]["root"]
    names = [c for c, _ in CONDITIONS]
    bad = []
    for n in root.walk():
        if n.tag in ("script", "style", "#root") or any(a.tag in ("script", "style") for a in n.ancestors()):
            continue
        for sentence in re.split(r"(?<=[.?!])\s+", own_text(n)):
            seen = []
            for m in sorted((m.start(), c) for c, rx in CONDITIONS for m in re.finditer(rx, sentence, re.I)):
                if m[1] not in seen:
                    seen.append(m[1])
            if len(seen) >= 2 and seen != sorted(seen, key=names.index):
                bad.append(f"'{sentence[:70]}'")
    report(not bad, "TL-03", "Every list of the conditions: energy, headroom, perspective, routines",
           "; ".join(bad[:3]) or "ok")
    got = [text(n) for n in root.find_all(lambda n: n.tag == "b" and any(
        "stat" in a.classes() for a in n.ancestors()))]
    report(got == [s for s, _ in STATS], "TL-03", "Stats band shows the four in order", ", ".join(got))
    for what, el, want in (
            ("Premise: the four conditions, in order (item 2)",
             first(root, lambda n: n.tag == "p" and any("premise" in a.classes() for a in n.ancestors())),
             f"{PREMISE_START} {PREMISE_END}"),
            ("Event band author paragraph (item 9)",
             first(root, lambda n: n.tag == "p" and text(n).startswith("Why Resistance Is Never the Problem argues")),
             SPEAKER)):
        got = text(el) if el else ""
        report(got == want, "TL-03", what, same(got, want))
    words = wording(root)
    allowed = [m.span() for ok in HABIT_OK for m in re.finditer(ok, words, re.I)]
    stray = []
    for m in re.finditer(r"\bhabit\w*", words, re.I):
        if not any(a <= m.start() and m.end() <= b for a, b in allowed):
            stray.append(f"'…{words[max(0, m.start() - 25):m.end() + 25]}…'")
    report(not stray, "TL-03", "'habit' only in Habit Machine, 'done out of habit', habit tracker",
           "; ".join(stray[:3]) or "ok")
    report(not re.search(r"cognitive space", words, re.I), "TL-03", "No 'cognitive space'")
    found = re.findall(NOT_ALWAYS, words, re.I)
    report(not found, "TL-03", "Resistance is 'often a signal', never 'always'", ", ".join(found) or "ok")


# --- TL-04: no banned claim ---------------------------------------------------------

def check_tl04(pages):
    for name in ("index", "article"):
        html = pages[name]["html"]
        found = [b for b in BANNED if b.lower() in html.lower()]
        report(not found, "TL-04", f"{name}.html (text, meta tags, source): no banned claim",
               ", ".join(found) or "ok")
    both = pages["index"]["html"] + pages["article"]["html"]
    n = len(re.findall(r"re-?freez", both, re.I))
    bio = first(pages["index"]["root"], lambda x: x.tag == "p" and tx(x).startswith("Iknetix"))
    report(n == 1 and "can no longer refreeze after each change" in tx(bio), "TL-04",
           "'refreeze' only in the ZERO line", f"{n} found")
    hook = first(pages["index"]["root"], has_class("hero-hook"))
    got = text(hook) if hook else ""
    report(got == HERO, "TL-04", "Hero line (item 1)", same(got, HERO))


# --- TL-05: nothing else changed -------------------------------------------------------

def without_new_blocks(lines):
    """The page with the two blocks this change adds removed, plus where each was."""
    out, where = list(lines), {}
    if CSS_START in out and CSS_END in out:
        s, e = out.index(CSS_START), out.index(CSS_END)
        if s < e:
            where["css"] = out[s:e]
            del out[s:e]
    if BAND_START in out:
        s = out.index(BAND_START)
        e = next((k for k in range(s, len(out)) if out[k] == "</section>"), None)
        if e is not None:
            e += 1
            if e < len(out) and out[e].strip() == "":
                e += 1
            where["band"] = out[s:e]
            del out[s:e]
    return out, where


def css_selectors(css):
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    sels = []
    for m in re.finditer(r"([^{};]+)\{", css):
        head = m.group(1).strip()
        if not head.startswith("@"):
            sels += [s.strip() for s in head.split(",")]
    return sels


def fixed_parts(html):
    root = parse(html)
    raw = lambda n: "".join(c for c in n.children if isinstance(c, str))  # noqa: E731
    return {
        "inline scripts": [raw(n) for n in root.find_all(lambda n: n.tag == "script" and "src" not in n.attrs)],
        "external scripts": [n.attrs["src"] for n in root.find_all(lambda n: n.tag == "script" and "src" in n.attrs)],
        "images": [(n.attrs.get("src"), n.attrs.get("alt")) for n in root.find_all(lambda n: n.tag == "img")],
        "head links": [tuple(sorted(n.attrs.items())) for n in root.find_all(lambda n: n.tag == "link")],
        "meta tags": [tuple(sorted(n.attrs.items())) for n in root.find_all(lambda n: n.tag == "meta")],
        "forms, media and embeds": [n.tag for n in root.find_all(lambda n: n.tag in (
            "form", "input", "button", "textarea", "select", "iframe", "object", "embed", "video",
            "audio", "source", "svg", "canvas", "picture"))],
    }


def tl05_problems(old_html, new_html):
    """Every way new_html differs from BASE_REF beyond the approved change; [] if none."""
    problems = []
    want = old_html
    for before, after in APPROVED_EDITS:
        if want.count(before) != 1:
            problems.append(f"approved edit not found once in {BASE_REF}: {before[:40]!r}")
            continue
        want = want.replace(before, after)
    want = want.split("\n")
    rest, blocks = without_new_blocks(new_html.split("\n"))
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, want, rest, autojunk=False).get_opcodes():
        if tag != "equal":
            got = rest[j1].strip()[:50] if j1 < len(rest) else "(nothing)"
            problems.append(f"{tag} near approved line {i1 + 1}: {got!r}")
    if "band" in blocks:
        src = "\n".join(blocks["band"])
        bad = [rx.replace("\\s", " ") for rx in BAND_FORBIDDEN if re.search(rx, src, re.I)]
        if bad:
            problems.append(f"band contains {', '.join(bad)}")
        got = text(parse(src))
        if got != BAND_TEXT:
            k = next((i for i, (a, b) in enumerate(zip(got, BAND_TEXT)) if a != b), min(len(got), len(BAND_TEXT)))
            problems.append(f"band text differs at '{got[max(0, k - 20):k + 40]}'")
    if "css" in blocks:
        stray = [s for s in css_selectors("\n".join(blocks["css"])) if not s.startswith(CSS_PREFIXES)]
        if stray:
            problems.append(f"new CSS styles existing selectors: {stray[:3]}")
        css = "\n".join(blocks["css"])
        fonts = set(re.findall(r"font-family:([^;}]+)", css))
        if fonts - {"var(--serif)", "var(--sans)", "var(--mono)"}:
            problems.append(f"new CSS uses another font: {sorted(fonts)}")
        if re.search(r"@import|url\(|@font-face|(?<![-\w])font:", css, re.I):
            problems.append("new CSS loads a file or uses the font shorthand")
    o, n = fixed_parts(old_html), fixed_parts(new_html)
    for k in o:
        if o[k] != n[k]:
            problems.append(f"{k} differ from main")
    oh = Counter(a.attrs.get("href") for a in parse(old_html).find_all(lambda x: x.tag == "a" and "href" in x.attrs))
    nh = Counter(a.attrs.get("href") for a in parse(new_html).find_all(lambda x: x.tag == "a" and "href" in x.attrs))
    if nh - oh not in (Counter(), Counter({PRECHANGE_URL: 1})) or oh - nh:
        problems.append(f"links differ from main beyond the prechangeway.com link: +{dict(nh - oh)} -{dict(oh - nh)}")
    return problems


def _after(pattern, line):
    def plant(html):
        lines = html.split("\n")
        for i, l in enumerate(lines):
            if re.search(pattern, l):
                return "\n".join(lines[:i + 1] + [line] + lines[i + 1:])
        return html
    return plant


# Edits that must never get past TL-05; the self-test plants each one.
PLANTED = {
    "edit on a line this change may not touch": lambda h: h.replace("surgery was torture", "surgery was agony", 1),
    "line added outside the new band": _after(r'id="author"', "    <p>Extra</p>"),
    "script added in the band": _after(r'class="fit-line', '<script src="https://example.com/x.js"></script>'),
    "extra link in the band": _after(r'class="fit-line', '<a href="https://example.com/">More</a>'),
    "image added in the band": _after(r'class="fit-line', '<img src="images/mola-fish.png" alt="">'),
    "new CSS restyles an existing class": _after(re.escape(CSS_START), ".zone{padding:0}"),
    "new CSS loads another font": _after(re.escape(CSS_START), ".fit-x{font-family:Arial}"),
    "page description changed": lambda h: h.replace("Why Resistance Is Never the Problem. Book One",
                                                    "Why Resistance Is Rarely the Problem. Book One", 1),
    "price added on an approved line": lambda h: h.replace(
        "with intention rather than reaction.</p>", "with intention rather than reaction. From USD 49.</p>", 1),
    "card text reworded on an approved line": lambda h: h.replace(
        "Passive perspective exposure at organisational scale.", "Passive perspective exposure at scale.", 1),
    "chapter line changed on an approved line": lambda h: h.replace(
        "Chapter 7 — Seeing What You Haven't Seen", "Chapter 7 — Seeing More", 1),
    "'always a signal' added in the band": _after(r'class="fit-note', "    <p>Resistance is always a signal.</p>"),
    "style element in the band": _after(r'class="fit-line', "<style>.zone{display:none}</style>"),
    "style attribute in the band": lambda h: h.replace('<p class="fit-note reveal">',
                                                       '<p class="fit-note reveal" style="display:none">', 1),
    "band label reworded": lambda h: h.replace("<small>The practice</small>", "<small>The method</small>", 1),
    "new CSS loads a file": _after(re.escape(CSS_START), "@import url(https://example.com/f.css);"),
}


def run_suite(label, cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    except (OSError, subprocess.TimeoutExpired) as e:
        return None, f"{label} did not run: {e}"
    lines = [l for l in r.stdout.splitlines() if l.startswith(("PASS", "FAIL"))]
    return (r, lines), None


def check_tl05(pages, base):
    try:
        changed = set(git("diff", "--name-only", BASE_REF, "HEAD").split())
        dirty = git("status", "--porcelain", "--untracked-files=no").strip()
        old_index = git("show", f"{BASE_REF}:index.html")
        old_article = git("show", f"{BASE_REF}:article.html")
    except subprocess.CalledProcessError as e:
        die(f"git failed: {e.stderr.strip()}")
    extra = sorted(f for f in changed if not f.startswith("tests/") and f not in FILES_ALLOWED_TO_CHANGE)
    report(not extra, "TL-05", f"Checkout: only index.html, the image, tests/ changed since {BASE_REF}",
           ", ".join(extra) or f"{len(changed)} files changed")
    report(not dirty, "TL-05", "Checkout: no uncommitted changes to tracked files",
           dirty.replace("\n", ", ")[:80] or "clean")
    report(pages["article"]["html"] == old_article, "TL-05", f"article.html is exactly as in {BASE_REF}")
    probs = tl05_problems(old_index, pages["index"]["html"])
    report(not probs, "TL-05", f"index.html: nothing differs from {BASE_REF} but approved edits",
           "; ".join(probs[:4]) or "ok")

    html = pages["index"]["html"]
    if probs or BAND_START not in html:
        report(False, "TL-05", "Self-test: planted edits are caught", "needs a page that passes first")
    else:
        missed = []
        for label, plant in PLANTED.items():
            planted = plant(html)
            if planted == html:
                missed.append(f"{label} (could not plant)")
            elif not tl05_problems(old_index, planted):
                missed.append(label)
        report(not missed, "TL-05", f"Self-test: all {len(PLANTED)} planted edits are caught",
               ", ".join(missed) or "ok")

    res, err = run_suite("Q04", ["bash", os.path.join(TESTS, "check_public_files.sh"), base])
    if err:
        report(False, "TL-05", "Q04 test: every check passes", err)
    else:
        r, lines = res
        fails = [l for l in lines if l.startswith("FAIL")]
        report(r.returncode == 0 and lines and not fails, "TL-05", "Q04 test: every check passes",
               f"{len(lines) - len(fails)} passed, {len(fails)} failed" + (f": {fails[0][:60]}" if fails else ""))
    res, err = run_suite("Q06", [sys.executable, os.path.join(TESTS, "check_price_and_events.py"), base])
    if err:
        report(False, "TL-05", "Q06 test: every check but PR-04 passes", err)
    else:
        r, lines = res
        fails = [l for l in lines if l.startswith("FAIL") and l.split()[1] != "PR-04"]
        pr04 = sum(1 for l in lines if l.split()[1] == "PR-04")
        ran = r.returncode in (0, 1) and lines
        report(ran and not fails, "TL-05", "Q06 test: every check but PR-04 passes",
               (f"{len(lines) - pr04 - len(fails)} passed, {len(fails)} failed, {pr04} PR-04 lines replaced by TL-05"
                + (f": {fails[0][:60]}" if fails else "")) if ran else r.stderr.strip()[:80])


# --- TL-06: the diagram ----------------------------------------------------------------

def check_tl06(pages, base):
    b = band(pages)
    fig = first(b, lambda n: n.tag == "figure") if b else None
    desc = first(fig, lambda n: n.attrs.get("id") == "tl3-desc") if fig else None
    capt = text(desc) if desc else ""
    named = all(x in capt for x in ("Prechange", "Change Anesthesiology", "Morphosis",
                                     "The Sunfish Paradox", "Iknetix", "ZERO"))
    report(fig is not None and fig.attrs.get("aria-describedby") == "tl3-desc" and "tl3-sr" in (desc.classes() if desc else [])
           and named, "TL-06", "Diagram is a <figure> with a screen-reader description", capt[:60] or "missing")
    # A drawn line (aria-hidden SVG) is allowed; pictures and embeds are not.
    media = [n.tag for n in fig.walk() if n.tag in ("img", "canvas", "picture", "iframe", "object")
             or (n.tag == "svg" and not any(a.attrs.get("aria-hidden") == "true" for a in [n, *n.ancestors()]))] if fig else []
    words = text(fig) if fig else ""
    real = fig is not None and all(w in words for w in ("Prechange", "Change Anesthesiology", "Morphosis",
                                                        V3["when"][3], V3["why"][4], V3["how"][3]))
    report(real and not media, "TL-06", "Real text, no image or embedded picture", ", ".join(media) or ("ok" if real else "text missing"))
    rule = re.search(r"\.tl3-sr\{[^}]*clip:rect\(0[ ,]+0[ ,]+0[ ,]+0\)", pages["index"]["html"])
    report(bool(rule), "TL-06", "The description is hidden visually, not from screen readers")

    if not os.path.exists(q06.CHROME):
        die(f"Chrome not found at {q06.CHROME} (set CHROME) for the TL-06 layout checks")
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    profile = tempfile.mkdtemp(prefix="check-three-layers-")
    cases = [{"path": "/", "width": w, "selector": "#where-this-fits figure"} for w in WIDTHS]
    try:
        r = subprocess.run(["node", "-e", q06.LAYOUT_HARNESS], capture_output=True, text=True, timeout=300,
                           input=json.dumps({"chrome": q06.CHROME, "port": port, "profile": profile,
                                             "base": base, "cases": cases}))
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    if r.returncode != 0:
        die(f"layout check failed to run: {r.stderr.strip()[:300]}")
    for x in json.loads(r.stdout):
        ok = x["text"] is not None and x["over"] <= 0
        report(ok, "TL-06", f"{x['width']} px: diagram shown, no sideways scroll",
               "diagram missing" if x["text"] is None else f"{x['over']} px sideways")


# --- TL-07: the unused back-cover image is gone ------------------------------------------

def check_tl07(base):
    tracked = git("ls-files", REMOVED_IMAGE).strip()
    report(not tracked, "TL-07", f"{REMOVED_IMAGE} removed from the repo", tracked or "gone")
    code = status(f"{base}/{REMOVED_IMAGE}")
    report(code == 404, "TL-07", f"/{REMOVED_IMAGE} returns 404", f"got {code}")


# --- TL-08: no "honest", no price in new text -------------------------------------------------

def check_tl08(pages):
    every = " ".join(p["wording"] for p in pages.values())
    found = re.findall(r"\bhonest(?:ly)?\b", every, re.I)
    report(not found, "TL-08", "No 'honest' or 'honestly' on either page", ", ".join(found) or "ok")
    new_words = " ".join([BAND_TEXT] + [after for _, after in APPROVED_EDITS])
    found = re.findall(r"\bhonest\w*", new_words, re.I)
    report(not found, "TL-08", "No 'honest…' word in any new text", ", ".join(found) or "ok")
    b = band(pages)
    new = [wording(b) if b else "", BAND_TEXT] + [after for _, after in APPROVED_EDITS]
    money = re.findall(r"(?:US\$|CA\$|C\$|\bCAD\b|\bUSD\b|\$|€|£)\s?\d|\b\d+(?:\.\d\d)?\s?(?:dollars|USD|CAD)\b",
                       " ".join(new), re.I)
    report(b is not None and not money, "TL-08", "No price in the new text", ", ".join(money) or ("ok" if b else "band missing"))


# --- TL-09: items 3, 4, 10 and 11 word for word --------------------------------------------------

def check_tl09(pages):
    root = pages["index"]["root"]
    got = [(text(first(s, lambda n: n.tag == "b") or s), text(first(s, lambda n: n.tag == "span") or s))
           for s in root.find_all(has_class("stat"))]
    report(got == STATS, "TL-09", "Item 3: stats band labels and lines",
           "ok" if got == STATS else "; ".join(f"{a}: {b}" for a, b in got)[:90])
    bio = first(root, lambda n: n.tag == "p" and any("author-content" in a.classes() for a in n.ancestors())
                and text(n).startswith("Iknetix"))
    got = text(bio) if bio else ""
    report(got == BIO, "TL-09", "Item 4: author bio (proposed, refreeze, examined)", same(got, BIO))
    z3 = first(root, has_class("zone", "z3"))
    got = next((text(p) for p in (z3.find_all(lambda n: n.tag == "p" and not n.classes()) if z3 else [])), "")
    report(got == ZONE3, "TL-09", "Item 10: Model, Zone 3 card", same(got, ZONE3))
    tk = first(root, has_class("card", "no-tool"))
    got = next((text(p) for p in (tk.find_all(lambda n: n.tag == "p" and not n.classes()) if tk else [])), "")
    report(got == TOOLKIT3, "TL-09", "Item 10: Toolkit, Zone 3 card", same(got, TOOLKIT3))

    b = band(pages)
    if b is None:
        report(False, "TL-09", "Item 11: the band", "missing")
        return
    tag, head = first(b, has_class("tag")), first(b, lambda n: n.tag == "h2")
    got = (text(tag) if tag else "", text(head) if head else "")
    report(got == (BAND_TAG, BAND_HEAD), "TL-09", "Item 11: tag and heading", " / ".join(got))
    got = v3_parts(first(b, lambda n: n.tag == "figure"))
    for key, want in V3.items():
        report(got[key] == want, "TL-09", f"Item 11 (design v3): {key}",
               "ok" if got[key] == want else str(got[key])[:90])


def main():
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} <base-url>", file=sys.stderr)
        sys.exit(2)
    base = sys.argv[1].rstrip("/")
    pages = {}
    for name, path in (("index", "/"), ("article", "/article")):
        try:
            html = q06.fetch(base + path)
        except Exception as e:  # noqa: BLE001 - any fetch problem means the test can't run
            die(f"cannot fetch {base + path}: {e}")
        root = parse(html)
        pages[name] = {"html": html, "root": root, "wording": wording(root)}

    print(f"Checking {base} (base reference {BASE_REF})\n")
    for fn in (check_tl01, check_tl02, check_tl03, check_tl04):
        fn(pages)
        print()
    # TL-05 ("nothing else changed" against 4deca4e, plus the Q04 and Q06 runs) is replaced by
    # TV-08 and TV-09 in tests/check_three_layers_v3.py from Q12 on (D56, 17 Oct 2026).
    print("TL-05 is replaced by TV-08 and TV-09 in tests/check_three_layers_v3.py (Q12).\n")
    check_tl06(pages, base)
    print()
    check_tl07(base)
    print()
    check_tl08(pages)
    print()
    check_tl09(pages)
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
