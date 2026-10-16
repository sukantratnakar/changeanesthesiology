#!/usr/bin/env bash
# Checks that the site hides repo-only files and still serves every visitor file.
# Requirements HG-01 to HG-03 (Q04, 15 Oct 2026).
#
# Usage:  tests/check_public_files.sh <base-url>
#   e.g.  tests/check_public_files.sh https://changeanesthesiology.com
#
# Prints one PASS/FAIL line per check and exits 1 if any check fails
# (2 if the repo's file list can't be read).
# Uses curl only (no browser), so it does not trigger Google Analytics.
# File lists come from the git checkout this script lives in.

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
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

die() { echo "error: $*" >&2; exit 2; }

sha256() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | cut -d' ' -f1
  else shasum -a 256 "$1" | cut -d' ' -f1
  fi
}

# Fetch a path without following redirects; prints "<status> <content-type>".
fetch() {
  curl -s -o "${2:-/dev/null}" -A "$UA" --max-time 30 \
    -w '%{http_code} %{content_type}' "$BASE${1// /%20}"
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

expect_same_as_file() { # expect_same_as_file <req-id> <path> <local file>
  local status
  status="$(fetch "$2" "$TMP/body" | cut -d' ' -f1)"
  if [ "$status" = 200 ] && [ "$(sha256 "$TMP/body")" = "$(sha256 "$3")" ]; then
    report PASS "$1" "$2" "200, same bytes as ${3#"$REPO_ROOT"/}"
  else
    report FAIL "$1" "$2" "got $status, bytes differ from ${3#"$REPO_ROOT"/}"
  fi
}

expect_redirect() { # expect_redirect <req-id> <path> <target path>
  local out
  out="$(curl -s -o /dev/null -A "$UA" --max-time 30 -w '%{http_code} %{redirect_url}' "$BASE$2")"
  case "$out" in
    30[1278]\ *"$3") report PASS "$1" "$2" "${out%% *} -> $3" ;;
    *) report FAIL "$1" "$2" "got '$out', expected a redirect to $3" ;;
  esac
}

# --- File lists from the local checkout ------------------------------------

TRACKED="$(git -C "$REPO_ROOT" ls-files)" || die "cannot list files with git in $REPO_ROOT"
[ -n "$TRACKED" ] || die "git lists no files in $REPO_ROOT"

# Visitor files: the two pages, top-level images, everything under images/.
VISITOR="$(printf '%s\n' "$TRACKED" |
  grep -iE '^(index\.html|article\.html|[^/]+\.(png|jpe?g|svg|gif|webp|avif|ico)|images/.+)$')"
printf '%s\n' "$VISITOR" | grep -q '^images/' || die "no files under images/ in $REPO_ROOT"

# Repo-only files: whatever .assetsignore hides. Match in an empty repo so only
# .assetsignore counts (not any .gitignore or .git/info/exclude).
git init -q "$TMP/matcher" || die "git init failed"
HIDDEN="$(printf '%s\n' "$TRACKED" |
  git -C "$TMP/matcher" -c core.excludesFile="$REPO_ROOT/.assetsignore" \
    check-ignore --no-index --stdin)"
[ $? -le 1 ] || die "git check-ignore failed"

echo "Checking $BASE"
echo

echo "HG-02/HG-03  Every repo file is either a visitor file or hidden (local checkout)"
problems=0
while IFS= read -r f; do
  in_visitor=no; in_hidden=no
  printf '%s\n' "$VISITOR" | grep -qxF "$f" && in_visitor=yes
  printf '%s\n' "$HIDDEN" | grep -qxF "$f" && in_hidden=yes
  case "$in_visitor$in_hidden" in
    yesyes) report FAIL HG-03 "/$f" "visitor file is hidden by .assetsignore"; problems=1 ;;
    nono)   report FAIL HG-02 "/$f" "not a visitor file and not in .assetsignore"; problems=1 ;;
  esac
done <<< "$TRACKED"
if [ "$problems" = 0 ]; then
  report PASS HG-02 "(all repo files)" "$(printf '%s\n' "$TRACKED" | wc -l | tr -d ' ') files: $(printf '%s\n' "$VISITOR" | wc -l | tr -d ' ') served, $(printf '%s\n' "$HIDDEN" | grep -c .) hidden"
fi
echo

echo "HG-01  Nothing under /.git/ is served"
for p in /.git/config /.git/HEAD /.git/index /.git/description /.git/packed-refs /.git/logs/HEAD; do
  expect_hidden HG-01 "$p"
done
echo

echo "HG-02  Repo settings and tests are not served"
for p in /wrangler.jsonc /.assetsignore /.gitignore /tests/check_public_files.sh; do
  expect_hidden HG-02 "$p"
done
echo

echo "HG-03  Every visitor file still loads"
out="$(fetch / "$TMP/index")"
status="${out%% *}"
bytes="$(wc -c < "$TMP/index" | tr -d ' ')"
hash="$(sha256 "$TMP/index")"
if [ "$status" = 200 ] && [ "$bytes" = "$EXPECTED_INDEX_BYTES" ] && [ "$hash" = "$EXPECTED_INDEX_SHA256" ]; then
  report PASS HG-03 / "200, $bytes bytes, sha256 matches"
else
  report FAIL HG-03 / "got $status, $bytes bytes, sha256 $hash; expected 200, $EXPECTED_INDEX_BYTES bytes, $EXPECTED_INDEX_SHA256"
fi
expect_same_as_file HG-03 /article "$REPO_ROOT/article.html"
expect_redirect HG-03 /article.html /article

# Images: status and type only, since a CDN may legitimately re-encode them.
while IFS= read -r f; do
  case "$f" in *.html) continue ;; esac
  expect_served HG-03 "/$f" image/
done <<< "$VISITOR"
echo

echo "Result: $PASSED passed, $FAILED failed"
[ "$FAILED" -eq 0 ]
