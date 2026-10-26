#!/usr/bin/env bash
# Multi-width render check for WheatOmics SPAs — see MAINTENANCE.md §九.
#
# Loads a page in a real browser at eight widths (360…1920), takes screenshots
# and fails on floor problems: horizontal overflow, broken images, load-time JS
# errors, missing <meta viewport>, unreadable text contrast (<3:1), or a
# --wait selector that never appears. Warnings cover contrast 3–4.5:1, images
# without alt text, small touch targets and a missing <html lang>.
#
# No npm installs: this drives the local `ego-browser` CLI (same tool the agent
# uses for acceptance checks). If ego-browser is missing, nothing runs.
#
# Usage:
#   bash scripts/spa_visual_check.sh <url> [options]
#
# Options:
#   --label <name>         report label / screenshot folder prefix (default: from URL)
#   --widths <list>        comma-separated widths (default: 360,390,414,768,1024,1280,1440,1920)
#   --fill <sel=value>     fill an input before checking (repeatable)
#   --click <selector>     click something before checking (repeatable)
#   --wait <selector>      wait for a selector to be visible (repeatable; also a floor check)
#   --scroll-to <sel>      additionally screenshot that section for every width
#   --settle <ms>          settle time after actions (default 900)
#   --out <dir>            output directory (default: $TMPDIR/spa-check/<label>-<timestamp>)
#   -h, --help             show this help
#
# Examples:
#   bash scripts/spa_visual_check.sh http://127.0.0.1:8000/wheatPTM/
#   bash scripts/spa_visual_check.sh https://wheatomics.sdau.edu.cn/wheatPTM/ \
#     --label wheatptm-result \
#     --fill '#protein-input=TraesCS1A02G000100LC.1' --click '#search-btn' --wait '#result-area'
#
# Exit code: 0 = PASS, 1 = floor problems, 2 = usage / missing dependency.

set -uo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MJS="$REPO_DIR/scripts/spa_visual_check.mjs"

usage() {
  awk '/^# Usage:/{f=1} /^# Exit code:/{f=0} f' "$0" | sed 's/^# \{0,1\}//'
}

URL=""
LABEL=""
WIDTHS="360,390,414,768,1024,1280,1440,1920"
OUT_DIR=""
SCROLL_TO=""
SETTLE="900"
ACTIONS=()

json_action() { # type selector [value]
  python3 - "$1" "$2" "${3:-}" <<'PY'
import json, sys
kind, selector, value = sys.argv[1], sys.argv[2], sys.argv[3]
action = {"type": kind, "selector": selector}
if kind == "fill":
    action["value"] = value
print(json.dumps(action))
PY
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --label)       LABEL="${2:?--label needs a value}"; shift 2 ;;
    --widths)      WIDTHS="${2:?--widths needs a value}"; shift 2 ;;
    --out)         OUT_DIR="${2:?--out needs a value}"; shift 2 ;;
    --scroll-to)   SCROLL_TO="${2:?--scroll-to needs a value}"; shift 2 ;;
    --settle)      SETTLE="${2:?--settle needs a value}"; shift 2 ;;
    --fill)
      arg="${2:?--fill needs selector=value}"
      sel="${arg%%=*}"; value="${arg#*=}"
      [[ -z "$sel" || "$sel" == "$value" ]] && { echo "[spa-check] --fill expects selector=value, got: $arg" >&2; exit 2; }
      ACTIONS+=("$(json_action fill "$sel" "$value")"); shift 2 ;;
    --click)       ACTIONS+=("$(json_action click "${2:?--click needs a selector}")"); shift 2 ;;
    --wait)        ACTIONS+=("$(json_action waitFor "${2:?--wait needs a selector}")"); shift 2 ;;
    -h|--help)     usage; exit 0 ;;
    --*)           echo "[spa-check] unknown option: $1" >&2; usage >&2; exit 2 ;;
    *)
      if [[ -z "$URL" ]]; then URL="$1"; shift; else echo "[spa-check] unexpected argument: $1" >&2; exit 2; fi ;;
  esac
done

if [[ -z "$URL" ]]; then usage >&2; exit 2; fi
if ! command -v ego-browser >/dev/null 2>&1; then
  echo "[spa-check] ego-browser not found. It is the browser used for SPA acceptance checks;" >&2
  echo "            install/enable it first, or review the page manually." >&2
  exit 2
fi
if ! command -v python3 >/dev/null 2>&1; then echo "[spa-check] python3 is required" >&2; exit 2; fi

STAMP="$(date +%Y%m%d-%H%M%S)"
if [[ -z "$LABEL" ]]; then
  LABEL="$(printf '%s' "$URL" | sed -E 's#^https?://##; s#[/:?&=]+#_#g; s#_+$##' | cut -c1-60)"
fi
if [[ -z "$OUT_DIR" ]]; then
  OUT_DIR="${TMPDIR:-/tmp}/spa-check/${LABEL}-${STAMP}"
fi

TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/spa-check-entry.XXXXXX")"
ENTRY="$TMP_DIR/entry.mjs"
cleanup() { rm -rf "$TMP_DIR"; }
trap cleanup EXIT

python3 - "$URL" "$LABEL" "$WIDTHS" "$OUT_DIR" "$SCROLL_TO" "$SETTLE" "$MJS" ${ACTIONS[@]+"${ACTIONS[@]}"} > "$ENTRY" <<'PY'
import json, sys
url, label, widths, out_dir, scroll_to, settle, mjs = sys.argv[1:8]
actions = [json.loads(raw) for raw in sys.argv[8:] if raw]
cfg = {
    "url": url,
    "label": label,
    "widths": [int(x) for x in widths.split(",") if x.strip()],
    "outDir": out_dir,
    "scrollTo": scroll_to or None,
    "settleMs": int(settle),
    "actions": actions,
}
sys.stdout.write("globalThis.__SPA_CHECK_CONFIG__ = %s;\n" % json.dumps(cfg, ensure_ascii=False))
sys.stdout.write("await import(%r);\n" % ("file://" + mjs))
PY

echo "[spa-check] $URL"
echo "[spa-check] widths: $WIDTHS | out: $OUT_DIR"
ego-browser nodejs -e "await import('file://${ENTRY}')"
rc=$?
if [[ $rc -eq 0 ]]; then
  echo "[spa-check] PASS — screenshots: $OUT_DIR"
else
  echo "[spa-check] FAIL (exit $rc) — report: $OUT_DIR/report.md" >&2
fi
exit $rc
