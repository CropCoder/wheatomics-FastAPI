#!/usr/bin/env bash
# Sync translatome data assets from the local build directory to the server
# data directory (TRANSLATOME_DATA_DIR). The repo only contains registry.json +
# manifests; the gzipped matrices must never be committed.
#
# Usage:
#   bash scripts/heat_translatome/sync_assets.sh <ssh-target> [remote-dir] [options]
#
#   ssh-target   e.g. wheatomics (an ~/.ssh/config alias) or user@host
#   remote-dir   default: /var/www/data/translatome
#   options:
#     --local <dir>   local assets root (default: $TRANSLATOME_DATA_DIR)
#     --dry-run       show what would be transferred
#     --delete        REMOVE remote files not present locally (explicit opt-in)
#
# The remote directory is created if missing and the transferred files are made
# world-readable (the API runs as the web service user). After syncing, ensure
# the server .env has TRANSLATOME_DATA_DIR set and restart the API:
#
#   sudo systemctl restart wheatomics-api
#
# Example:
#   TRANSLATOME_DATA_DIR=~/wheatomics/translatome_data \
#     bash scripts/heat_translatome/sync_assets.sh wheatomics
set -euo pipefail

usage() {
  sed -n '2,26p' "$0" | sed 's/^# \{0,1\}//'
  exit 2
}

TARGET=""
REMOTE_DIR="/var/www/data/translatome"
LOCAL_DIR="${TRANSLATOME_DATA_DIR:-}"
DRY_RUN=()
DELETE=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --local) LOCAL_DIR="${2:?--local needs a value}"; shift 2 ;;
    --dry-run) DRY_RUN=(--dry-run); shift ;;
    --delete) DELETE=(--delete); shift ;;
    -h|--help) usage ;;
    *)
      if [[ -z "$TARGET" ]]; then TARGET="$1"; else REMOTE_DIR="$1"; fi
      shift ;;
  esac
done

if [[ -z "$TARGET" ]]; then
  echo "ERROR: missing <ssh-target>" >&2
  usage
fi
if [[ -z "$LOCAL_DIR" ]]; then
  echo "ERROR: set TRANSLATOME_DATA_DIR or pass --local <assets-root>" >&2
  exit 2
fi
if [[ ! -d "$LOCAL_DIR" ]]; then
  echo "ERROR: local assets root not found: $LOCAL_DIR" >&2
  exit 2
fi
if ! command -v rsync >/dev/null 2>&1; then
  echo "ERROR: rsync is required" >&2
  exit 2
fi

echo "[sync] $LOCAL_DIR/  ->  $TARGET:$REMOTE_DIR/"
ssh "$TARGET" "mkdir -p '$REMOTE_DIR'"
rsync -avz "${DRY_RUN[@]}" "${DELETE[@]}" \
  --chmod=Du=rwx,Dgo=rx,Fu=rw,Fgo=r \
  "$LOCAL_DIR/" "$TARGET:$REMOTE_DIR/"

echo "[sync] done. Next steps on the server:"
echo "  1) ensure .env contains TRANSLATOME_DATA_DIR=$REMOTE_DIR"
echo "  2) sudo systemctl restart wheatomics-api"
echo "  3) curl -s https://<site>/api/translatome/datasets | grep assets_ready"
