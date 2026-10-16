#!/usr/bin/env bash
# Checks that the site hides repo-only files and still serves every visitor file.
# Requirements HG-01 to HG-03 (Q04, 15 Oct 2026).
#
# Usage:  tests/check_public_files.sh <base-url>
#   e.g.  tests/check_public_files.sh https://changeanesthesiology.com
#
# Prints one PASS/FAIL line per check and exits 1 if any check fails.
# Uses curl only (no browser), so it does not trigger Google Analytics.
# The list of images comes from the git checkout this script lives in.

set -u

if [ $# -ne 1 ]; then
  echo "usage: $0 <base-url>" >&2
  exit 2
fi
BASE="${1%/}"

# "/" must stay byte-for-byte the same as index.html on 15 Oct 2026.
EXPECTED_INDEX_BYTES="${EXPECTED_INDEX_BYTES:-61004}"
EXPECTED_INDEX_SHA256="${EXPECTED_INDEX_SHA256:-af166836376af2c4e597cd6c30fee09eb718ca90981f245129a417c6e0ab0263}"

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
UA="check_public_files.sh (changeanesthesiology repo test)"
PASSED=0
FAILED=0

sha256() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | cut -d' ' -f1
  else shasum -a 256 "$1" | cut -d' ' -f1
  fi
}

# Fetch a path without following redirects; prints "<status> <content-type>".
fetch() {
  curl -s -o "${2:-/dev/null}" -A "$UA" --max-time 30 \
    -w '%{http_code} %{content_type}' "$BASE$1"
}

report() { # report <PASS|FAIL> <req-id> <path> <detail>
  printf '%s  %s  %-40s %s\n' "$1" "$2" "$3" "$4"
  if [ "$1" = PASS ]; then PASSED=$((PASSED + 1)); else FAILED=$((FAILED + 1)); fi
}

expect_hidden() { # expect_hidden <req-id> <path>
  local status
  status="$(fetch "$2" | cut -d' ' -f1)"
  if [ "$status" = 404 ]; then
    report PASS "$1" "$2" "404 (not served)"
  else
    report FAIL "$1" "$2" "got $status, expected 404"
  fi
}

expect_served() { # expect_served <req-id> <path> <content-type prefix>
  local out status ctype
  out="$(fetch "$2")"
  status="${out%% *}"
  ctype="${out#* }"
  if [ "$status" = 200 ] && [ "${ctype#"$3"}" != "$ctype" ]; then
    report PASS "$1" "$2" "200 $ctype"
  else
    report FAIL "$1" "$2" "got $status '$ctype', expected 200 $3*"
  fi
}

echo "Checking $BASE"
echo

echo "HG-01  Nothing under /.git/ is served"
for p in /.git/config /.git/HEAD /.git/index /.git/description; do
  expect_hidden HG-01 "$p"
done
echo

echo "HG-02  Repo settings and tests are not served"
for p in /wrangler.jsonc /.assetsignore /.gitignore /tests/check_public_files.sh; do
  expect_hidden HG-02 "$p"
done
echo

echo "HG-03  Every visitor file still loads"
tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
out="$(fetch / "$tmp")"
status="${out%% *}"
bytes="$(wc -c < "$tmp" | tr -d ' ')"
hash="$(sha256 "$tmp")"
if [ "$status" = 200 ] && [ "$bytes" = "$EXPECTED_INDEX_BYTES" ] && [ "$hash" = "$EXPECTED_INDEX_SHA256" ]; then
  report PASS HG-03 / "200, $bytes bytes, sha256 matches"
else
  report FAIL HG-03 / "got $status, $bytes bytes, sha256 $hash; expected 200, $EXPECTED_INDEX_BYTES bytes, $EXPECTED_INDEX_SHA256"
fi
expect_served HG-03 /article text/html

# Top-level images (favicons, og-image, etc.) and everything under images/.
for f in $(git -C "$REPO_ROOT" ls-files | grep -E '^[^/]+\.(png|jpe?g|svg|gif|webp|ico)$|^images/'); do
  expect_served HG-03 "/$f" image/
done
echo

echo "Result: $PASSED passed, $FAILED failed"
[ "$FAILED" -eq 0 ]
