#!/usr/bin/env node
// Builds the events parts of index.html from prechangeway.com's public feed (Q09, EF-01 to EF-06).
//
// Reads https://prechangeway.com/events.json, checks every rule, copies the launch photos into
// images/events/<event-id>/ with their file details stripped, and rewrites the two marked spots
// in index.html plus data/events.json, the last good copy. If any check fails, nothing is
// written and the script exits 1, so the last good copy stays live.
//
// Settings (environment):
//   FEED_URL          the feed (default https://prechangeway.com/events.json)
//   FEED_FILE         read the feed from this file instead (tests)
//   PRECHANGE_MIRROR  read https://prechangeway.com/<path> from this folder instead (tests)
//   NOW               a fixed clock in ISO 8601 (tests)
//   REPO_ROOT         the site folder (default: the folder above scripts/)
//   FETCH_TIMEOUT_MS  per request (default 20000)
//
// Exit codes: 0 done (changed or not), 1 feed rejected (nothing written), 2 the page or setup is wrong.

import { existsSync, mkdirSync, readFileSync, readdirSync, renameSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { dirname, join, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(process.env.REPO_ROOT || join(dirname(fileURLToPath(import.meta.url)), '..'));
const FEED_URL = process.env.FEED_URL || 'https://prechangeway.com/events.json';
const TIMEOUT = Number(process.env.FETCH_TIMEOUT_MS || 20000);
const NOW = process.env.NOW ? new Date(process.env.NOW) : new Date();
const FEED_MAX = 256 * 1024;
const PHOTO_MAX = 1536 * 1024;
const SITE = 'https://prechangeway.com/';
const LAUNCH = 'spotlight-change-anesthesiology-2026-08';
const TZ = 'America/Regina';
const PHOTO_DIR = join('images', 'events');
const MARKERS = {
  upcoming: ['<!-- events-feed:upcoming -->', '<!-- /events-feed:upcoming -->'],
  gallery: ['<!-- events-feed:gallery -->', '<!-- /events-feed:gallery -->'],
};

class Rejected extends Error {}

// --- reading -------------------------------------------------------------------------------

async function download(url, max, accept) {
  const mirror = process.env.PRECHANGE_MIRROR;
  if (mirror && url.startsWith(SITE)) {
    const base = resolve(mirror);
    const file = resolve(base, decodeURIComponent(new URL(url).pathname.slice(1)));
    if (!file.startsWith(base + sep) || !existsSync(file)) throw new Rejected(`${url}: not found`);
    if (statSync(file).size > max) throw new Rejected(`${url}: larger than ${max} bytes`);
    return readFileSync(file);
  }
  let res;
  try {
    res = await fetch(url, {
      signal: AbortSignal.timeout(TIMEOUT),
      headers: { Accept: accept, 'User-Agent': 'changeanesthesiology.com events build' },
    });
  } catch (e) {
    throw new Rejected(`${url}: ${e.name === 'TimeoutError' ? `no answer within ${TIMEOUT} ms` : e.message}`);
  }
  if (!res.ok) throw new Rejected(`${url}: HTTP ${res.status}`);
  if (!res.url.startsWith(SITE)) throw new Rejected(`${url}: redirected away from prechangeway.com`);
  if (Number(res.headers.get('content-length') || 0) > max) throw new Rejected(`${url}: larger than ${max} bytes`);
  const parts = [];
  let size = 0;
  try {
    for await (const chunk of res.body) {
      size += chunk.length;
      if (size > max) throw new Rejected(`${url}: larger than ${max} bytes`);
      parts.push(chunk);
    }
  } catch (e) {
    if (e instanceof Rejected) throw e;
    throw new Rejected(`${url}: ${e.name === 'TimeoutError' ? `no answer within ${TIMEOUT} ms` : e.message}`);
  }
  return Buffer.concat(parts);
}

async function readFeed() {
  let raw;
  if (process.env.FEED_FILE) {
    const file = resolve(process.env.FEED_FILE);
    if (!existsSync(file)) throw new Rejected(`${file}: not found`);
    if (statSync(file).size > FEED_MAX) throw new Rejected(`${file}: larger than ${FEED_MAX} bytes`);
    raw = readFileSync(file);
  } else {
    raw = await download(FEED_URL, FEED_MAX, 'application/json');
  }
  try {
    return JSON.parse(raw.toString('utf8'));
  } catch (e) {
    throw new Rejected(`the feed is not valid JSON: ${e.message}`);
  }
}

// --- checks (EF-04, EF-06) ---------------------------------------------------------------------

const ISO = /^(\d{4}-\d{2}-\d{2})T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,3})?)?(?:Z|[+-]\d{2}:\d{2})$/;
const SLUG = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const EVENT_LINK = /^https:\/\/prechangeway\.com\/events#[A-Za-z0-9-]+$/;
const PHOTO_SRC = /^https:\/\/prechangeway\.com\/[A-Za-z0-9._~/-]+$/;
const CHECK_LINK = /\/start(?![a-z0-9])|src=live-/i;
const PRICE = /[$€£¥₹]\s?\d|\b(?:USD|CAD|EUR|GBP|US\$|CA\$|C\$)\s?\d|\d\s?(?:USD|CAD|EUR|GBP|dollars?)\b/i;
// Capitalised word groups that are titles or places, not people.
const NOT_PEOPLE = new Set(['Change Anesthesiology', 'Sunfish Paradox', 'Mola Series', 'Elite Leadership',
  'Leadership Club', 'Elite Leadership Club']);
const NOT_FIRST = new Set(['The', 'A', 'An', 'Prechange', 'This', 'That', 'Why', 'How', 'What', 'When', 'With',
  'From', 'For', 'In', 'On', 'At', 'And', 'Or', 'Of', 'To', 'By']);

const isObj = v => v !== null && typeof v === 'object' && !Array.isArray(v);
const realDate = d => !Number.isNaN(Date.parse(`${d}T00:00:00Z`)) && new Date(`${d}T00:00:00Z`).toISOString().slice(0, 10) === d;
const isInstant = s => typeof s === 'string' && ISO.test(s) && realDate(s.slice(0, 10)) && !Number.isNaN(Date.parse(s));
const isText = (s, max) => typeof s === 'string' && s.trim() !== '' && s.length <= max;

function strings(v, path, out) {
  if (typeof v === 'string') out.push([path, v]);
  else if (Array.isArray(v)) v.forEach((x, i) => strings(x, `${path}[${i}]`, out));
  else if (isObj(v)) for (const [k, x] of Object.entries(v)) strings(x, `${path}.${k}`, out);
  return out;
}

function peopleIn(feed) {
  const names = new Set();
  const texts = [...feed.upcoming.map(e => e.title), ...feed.past.flatMap(p => [p.title, p.highlights])];
  for (const t of texts) {
    for (const run of String(t).match(/\b[A-Z][a-zà-ÿ'’-]+(?:\s+[A-Z][a-zà-ÿ'’-]+)+/g) || []) {
      const words = run.split(/\s+/);
      if (words.length > 3 || NOT_FIRST.has(words[0]) || NOT_PEOPLE.has(run)) continue;
      names.add(run);
    }
  }
  return [...names];
}

function check(feed) {
  const bad = [];
  const need = (ok, what) => { if (!ok) bad.push(what); };
  if (!isObj(feed)) return ['the feed is not a JSON object'];
  need(feed.version === 1, `version must be 1 (got ${JSON.stringify(feed.version)})`);
  need(isInstant(feed.generated), 'generated must be an ISO 8601 time with an offset');
  need(Array.isArray(feed.upcoming) && feed.upcoming.length <= 50, 'upcoming must be a list of at most 50');
  need(Array.isArray(feed.past) && feed.past.length <= 50, 'past must be a list of at most 50');
  if (bad.length) return bad;

  const ids = new Set();
  feed.upcoming.forEach((e, i) => {
    const at = `upcoming[${i}]`;
    if (!isObj(e)) return bad.push(`${at} is not an object`);
    need(typeof e.id === 'string' && SLUG.test(e.id) && !ids.has(e.id), `${at}.id must be a new lower-case slug`);
    ids.add(e.id);
    need(typeof e.series === 'string' && SLUG.test(e.series), `${at}.series must be a lower-case slug`);
    need(isText(e.title, 160), `${at}.title must be text`);
    need(isText(e.city, 80), `${at}.city must be text`);
    need(e.venue === null || e.venue === undefined || isText(e.venue, 160), `${at}.venue must be text or null`);
    need(e.date_precision === 'day' || e.date_precision === 'month', `${at}.date_precision must be "day" or "month"`);
    need(isInstant(e.start), `${at}.start must be an ISO 8601 time with an offset`);
    if (e.date_precision === 'day') {
      need(isInstant(e.end) && Date.parse(e.end) > Date.parse(e.start), `${at}.end must be a later ISO 8601 time with an offset`);
    } else {
      need(e.end === null || e.end === undefined || isInstant(e.end), `${at}.end must be null or an ISO 8601 time with an offset`);
    }
    need(typeof e.url === 'string' && EVENT_LINK.test(e.url), `${at}.url must be https://prechangeway.com/events#…`);
    need(e.register_url === null || e.register_url === undefined || typeof e.register_url === 'string', `${at}.register_url must be text or null`);
    need(e.online === undefined || typeof e.online === 'boolean', `${at}.online must be true or false`);
    need(e.format === undefined || e.format === 'online' || e.format === 'in-person', `${at}.format must be "online" or "in-person"`);
  });
  feed.past.forEach((p, i) => {
    const at = `past[${i}]`;
    if (!isObj(p)) return bad.push(`${at} is not an object`);
    need(typeof p.id === 'string' && SLUG.test(p.id) && !ids.has(p.id), `${at}.id must be a new lower-case slug`);
    ids.add(p.id);
    need(isText(p.title, 160), `${at}.title must be text`);
    need(typeof p.date === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(p.date) && realDate(p.date), `${at}.date must be YYYY-MM-DD`);
    need(isText(p.city, 80), `${at}.city must be text`);
    need(typeof p.url === 'string' && EVENT_LINK.test(p.url), `${at}.url must be https://prechangeway.com/events#…`);
    need(typeof p.highlights === 'string' && p.highlights.length <= 2000, `${at}.highlights must be text`);
    need(p.more_photos_url === null || p.more_photos_url === undefined
      || (typeof p.more_photos_url === 'string' && EVENT_LINK.test(p.more_photos_url)), `${at}.more_photos_url must be https://prechangeway.com/events#… or null`);
    if (!Array.isArray(p.photos)) return bad.push(`${at}.photos must be a list`);
    need(p.photos.length <= 6, `${at} has ${p.photos.length} photos; at most 6`);
    p.photos.forEach((ph, j) => {
      const pat = `${at}.photos[${j}]`;
      if (!isObj(ph)) return bad.push(`${pat} is not an object`);
      need(typeof ph.src === 'string' && PHOTO_SRC.test(ph.src), `${pat}.src must be on https://prechangeway.com/`);
      need(Number.isInteger(ph.width) && ph.width > 0 && ph.width <= 800, `${pat}.width must be 1 to 800`);
      need(Number.isInteger(ph.height) && ph.height > 0 && ph.height <= 800, `${pat}.height must be 1 to 800`);
      need(isText(ph.alt, 200), `${pat}.alt must be text`);
    });
  });
  if (bad.length) return bad;

  const launch = feed.past.find(p => p.id === LAUNCH);
  need(launch, `the launch event ${LAUNCH} is missing`);
  if (launch) need(typeof launch.more_photos_url === 'string', `${LAUNCH} has no more_photos_url`);

  for (const [path, s] of strings(feed, 'feed', [])) {
    need(!CHECK_LINK.test(s), `${path} looks like a Check link`);
    need(!PRICE.test(s), `${path} contains a price`);
  }
  const people = peopleIn(feed);
  feed.past.forEach((p, i) => p.photos.forEach((ph, j) => {
    for (const name of people) {
      const words = [name, ...name.split(/\s+/).filter(w => w.length >= 3)];
      const hit = words.find(w => new RegExp(`(^|[^A-Za-z])${w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}([^A-Za-z]|$)`).test(ph.alt));
      need(!hit, `past[${i}].photos[${j}].alt names a person ("${hit}")`);
    }
  }));
  return bad;
}

// --- photos: type, size, and stripping file details ------------------------------------------------

function exifOrientation(tiff) {
  if (tiff.length < 8) return 1;
  const le = tiff.toString('latin1', 0, 2) === 'II';
  const u16 = o => (le ? tiff.readUInt16LE(o) : tiff.readUInt16BE(o));
  const u32 = o => (le ? tiff.readUInt32LE(o) : tiff.readUInt32BE(o));
  const ifd = u32(4);
  if (ifd + 2 > tiff.length) return 1;
  for (let k = 0, n = u16(ifd); k < n; k++) {
    const e = ifd + 2 + k * 12;
    if (e + 12 > tiff.length) break;
    if (u16(e) === 0x0112) return u16(e + 8);
  }
  return 1;
}

function jpeg(buf) {
  if (buf.length < 4 || buf[0] !== 0xff || buf[1] !== 0xd8) return null;
  const out = [buf.subarray(0, 2)];
  let i = 2, width, height, orientation = 1;
  while (i + 4 <= buf.length) {
    if (buf[i] !== 0xff) throw new Rejected('a JPEG photo is damaged');
    const m = buf[i + 1];
    if (m === 0xff) { i++; continue; }
    if (m === 0xda) {
      const end = buf.lastIndexOf(Buffer.from([0xff, 0xd9]));
      if (end < i) throw new Rejected('a JPEG photo has no end marker');
      out.push(buf.subarray(i, end + 2));
      return { type: 'jpg', width, height, orientation, bytes: Buffer.concat(out) };
    }
    if ((m >= 0xd0 && m <= 0xd7) || m === 0x01) { out.push(buf.subarray(i, i + 2)); i += 2; continue; }
    const len = buf.readUInt16BE(i + 2);
    const seg = buf.subarray(i, i + 2 + len);
    if (m >= 0xc0 && m <= 0xcf && m !== 0xc4 && m !== 0xc8 && m !== 0xcc) {
      height = buf.readUInt16BE(i + 5);
      width = buf.readUInt16BE(i + 7);
    }
    if (m === 0xe1 && seg.toString('latin1', 4, 10) === 'Exif\0\0') orientation = exifOrientation(seg.subarray(10));
    if (!(m >= 0xe0 && m <= 0xef) && m !== 0xfe) out.push(seg);  // drop APP0–APP15 and comments
    i += 2 + len;
  }
  throw new Rejected('a JPEG photo has no image data');
}

function png(buf) {
  const SIG = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);
  if (buf.length < 8 || !buf.subarray(0, 8).equals(SIG)) return null;
  const keep = new Set(['IHDR', 'PLTE', 'tRNS', 'IDAT', 'IEND', 'sRGB', 'gAMA', 'cHRM']);
  const out = [SIG];
  let i = 8, width, height, ended = false;
  while (i + 12 <= buf.length) {
    const len = buf.readUInt32BE(i);
    const type = buf.toString('latin1', i + 4, i + 8);
    if (type === 'IHDR') { width = buf.readUInt32BE(i + 8); height = buf.readUInt32BE(i + 12); }
    if (keep.has(type)) out.push(buf.subarray(i, i + 12 + len));
    i += 12 + len;
    if (type === 'IEND') { ended = true; break; }
  }
  if (!ended) throw new Rejected('a PNG photo is damaged');
  return { type: 'png', width, height, orientation: 1, bytes: Buffer.concat(out) };
}

function webp(buf) {
  if (buf.length < 16 || buf.toString('latin1', 0, 4) !== 'RIFF' || buf.toString('latin1', 8, 12) !== 'WEBP') return null;
  const parts = [];
  let i = 12, width, height, vp8x = null;
  while (i + 8 <= buf.length) {
    const type = buf.toString('latin1', i, i + 4);
    const len = buf.readUInt32LE(i + 4);
    const chunk = Buffer.from(buf.subarray(i, i + 8 + len + (len & 1)));
    const d = i + 8;
    if (type === 'VP8X') { vp8x = chunk; width = 1 + chunk.readUIntLE(12, 3); height = 1 + chunk.readUIntLE(15, 3); }
    else if (type === 'VP8 ' && width === undefined) { width = buf.readUInt16LE(d + 6) & 0x3fff; height = buf.readUInt16LE(d + 8) & 0x3fff; }
    else if (type === 'VP8L' && width === undefined) { const b = buf.readUInt32LE(d + 1); width = (b & 0x3fff) + 1; height = ((b >>> 14) & 0x3fff) + 1; }
    if (!['EXIF', 'XMP ', 'ICCP'].includes(type)) parts.push(chunk);
    i += 8 + len + (len & 1);
  }
  if (vp8x) vp8x[8] &= ~(0x20 | 0x08 | 0x04);  // no ICC, EXIF or XMP any more
  const body = Buffer.concat(parts);
  const head = Buffer.alloc(12);
  head.write('RIFF', 0, 'latin1');
  head.writeUInt32LE(4 + body.length, 4);
  head.write('WEBP', 8, 'latin1');
  return { type: 'webp', width, height, orientation: 1, bytes: Buffer.concat([head, body]) };
}

async function copyPhotos(event) {
  const out = [];
  for (const [j, ph] of event.photos.entries()) {
    const raw = await download(ph.src, PHOTO_MAX, 'image/jpeg,image/png,image/webp');
    const img = jpeg(raw) || png(raw) || webp(raw);
    const at = `${event.id} photo ${j + 1} (${ph.src})`;
    if (!img) throw new Rejected(`${at} is not a JPEG, PNG or WebP image`);
    if (img.orientation !== 1) throw new Rejected(`${at} relies on a rotation flag; send it upright`);
    if (img.width !== ph.width || img.height !== ph.height) {
      throw new Rejected(`${at} is ${img.width} × ${img.height}, but the feed says ${ph.width} × ${ph.height}`);
    }
    if (img.width > 800 || img.height > 800) throw new Rejected(`${at} is larger than 800 px`);
    out.push({ name: `${String(j + 1).padStart(2, '0')}.${img.type}`, bytes: img.bytes, width: img.width, height: img.height, alt: ph.alt });
  }
  return out;
}

// --- writing the page -------------------------------------------------------------------------------

const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const parts = (d, opts, locale = 'en-GB') => Object.fromEntries(
  new Intl.DateTimeFormat(locale, { timeZone: TZ, ...opts }).formatToParts(d).map(p => [p.type, p.value]));
const longDay = d => { const p = parts(d, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }); return `${p.weekday} ${p.day} ${p.month} ${p.year}`; };
const monthOnly = d => { const p = parts(d, { month: 'long', year: 'numeric' }); return `${p.month} ${p.year}`; };
const clock = d => { const p = parts(d, { hour: 'numeric', minute: '2-digit', hour12: true }, 'en-US'); return `${p.hour}:${p.minute} ${p.dayPeriod.toLowerCase()}`; };

function dateLine(e) {
  const s = new Date(e.start);
  if (e.date_precision === 'month') return monthOnly(s);
  const t = new Date(e.end);
  const end = longDay(t) === longDay(s) ? clock(t) : `${longDay(t)}, ${clock(t)}`;
  return `${longDay(s)} · ${clock(s)} – ${end} Saskatchewan time`;
}

function isOnline(e) {
  if (typeof e.online === 'boolean') return e.online;
  if (e.format) return e.format === 'online';
  return e.city.trim().toLowerCase() === 'online';
}

function hasEnded(e) {
  if (e.date_precision === 'day') return Date.parse(e.end) <= NOW.getTime();
  if (e.end) return Date.parse(e.end) <= NOW.getTime();
  const p = parts(new Date(e.start), { year: 'numeric', month: 'numeric' }, 'en-CA');
  const y = Number(p.year), m = Number(p.month);
  return Date.parse(`${m === 12 ? y + 1 : y}-${String(m === 12 ? 1 : m + 1).padStart(2, '0')}-01T00:00:00-06:00`) <= NOW.getTime();
}

function upcomingHtml(feed) {
  const bySeries = new Map();
  for (const e of [...feed.upcoming].sort((a, b) => Date.parse(a.start) - Date.parse(b.start))) {
    if (hasEnded(e)) continue;
    if (!bySeries.has(e.series)) bySeries.set(e.series, []);
    bySeries.get(e.series).push(e);
  }
  const shown = [...bySeries.values()].flatMap(list => list.slice(0, 2))
    .sort((a, b) => Date.parse(a.start) - Date.parse(b.start));
  if (!shown.length) return { html: '', count: 0 };
  const items = shown.map(e => {
    const local = e.date_precision === 'day' && isOnline(e)
      ? `<span class="feed-local" data-local-start="${esc(e.start)}" data-local-end="${esc(e.end)}" hidden></span>` : '';
    return `          <li><a href="${esc(e.url)}" target="_blank" rel="noopener" data-register-click>`
      + `<span class="feed-when">${esc(dateLine(e))}</span>${local}`
      + `<span class="feed-title">${esc(e.title)}</span><span class="feed-city">${esc(e.city)} &rarr;</span></a></li>`;
  });
  return {
    html: `        <ul class="feed-up" aria-label="Upcoming events on prechangeway.com">\n${items.join('\n')}\n        </ul>`,
    count: shown.length,
  };
}

function galleryHtml(event, photos) {
  const figures = photos.map(p => `        <figure><img src="images/events/${event.id}/${p.name}" width="${p.width}" height="${p.height}" alt="${esc(p.alt)}" loading="lazy" decoding="async"></figure>`);
  return [
    '    <div class="feed-gallery reveal">',
    '      <p class="tag">From the evening</p>',
    `      <p class="feed-hl">${esc(event.highlights)}</p>`,
    ...(figures.length ? ['      <div class="feed-photos">', ...figures, '      </div>'] : []),
    `      <a class="feed-more" href="${esc(event.more_photos_url)}" target="_blank" rel="noopener">More photos on prechangeway.com &rarr;</a>`,
    '    </div>',
  ].join('\n');
}

function fill(html, [open, close], inner) {
  const a = html.indexOf(open), b = html.indexOf(close);
  if (a < 0 || b < a || html.indexOf(open, a + 1) >= 0 || html.indexOf(close, b + 1) >= 0) {
    throw new Error(`index.html must hold ${open} … ${close} exactly once`);
  }
  const indent = html.slice(html.lastIndexOf('\n', b) + 1, b);
  return html.slice(0, a + open.length) + (inner ? `\n${inner}\n${indent}` : `\n${indent}`) + html.slice(b);
}

// --- main ------------------------------------------------------------------------------------------

async function main() {
  if (Number(process.versions.node.split('.')[0]) < 20) throw new Error('Node 20 or later is needed');
  if (Number.isNaN(NOW.getTime())) throw new Error('NOW is not a valid time');
  const pagePath = join(ROOT, 'index.html');
  const before = readFileSync(pagePath, 'utf8');
  fill(fill(before, MARKERS.upcoming, ''), MARKERS.gallery, '');  // markers present?

  const feed = await readFeed();
  const problems = check(feed);
  if (problems.length) throw new Rejected(problems.join('\n  '));
  const launch = feed.past.find(p => p.id === LAUNCH);
  const photos = await copyPhotos(launch);

  const up = upcomingHtml(feed);
  const after = fill(fill(before, MARKERS.upcoming, up.html), MARKERS.gallery, galleryHtml(launch, photos));
  const blank = h => fill(fill(h, MARKERS.upcoming, ''), MARKERS.gallery, '');
  if (blank(after) !== blank(before)) throw new Error('only the marked spots may change');

  // Everything is checked; write the photos, then the page, then the last good copy.
  const eventsDir = join(ROOT, PHOTO_DIR);
  const target = join(eventsDir, launch.id);
  const staging = join(eventsDir, `.incoming-${process.pid}`);
  rmSync(staging, { recursive: true, force: true });
  mkdirSync(staging, { recursive: true });
  for (const p of photos) writeFileSync(join(staging, p.name), p.bytes);
  for (const name of existsSync(eventsDir) ? readdirSync(eventsDir) : []) {
    if (name !== relative(eventsDir, staging)) rmSync(join(eventsDir, name), { recursive: true, force: true });
  }
  renameSync(staging, target);
  if (after !== before) writeFileSync(pagePath, after);
  // The last good copy. A new "generated" time alone is not a change worth a commit.
  const dataPath = join(ROOT, 'data', 'events.json');
  const sameAs = old => JSON.stringify({ ...old, generated: null }) === JSON.stringify({ ...feed, generated: null });
  let keep = false;
  try { keep = existsSync(dataPath) && sameAs(JSON.parse(readFileSync(dataPath, 'utf8'))); } catch { keep = false; }
  if (!keep) {
    mkdirSync(join(ROOT, 'data'), { recursive: true });
    writeFileSync(dataPath, `${JSON.stringify(feed, null, 2)}\n`);
  }
  console.log(`events feed: ${up.count} upcoming shown, ${photos.length} launch photos, page ${after === before ? 'unchanged' : 'updated'}`);
}

main().catch(e => {
  if (e instanceof Rejected) {
    console.error(`events feed rejected; nothing changed. Last good copy stays live.\n  ${e.message}`);
    process.exit(1);
  }
  console.error(`events feed: ${e.message}`);
  process.exit(2);
});
