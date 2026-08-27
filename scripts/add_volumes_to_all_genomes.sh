#!/usr/bin/env bash
#
# Merge extra per-genome volumes into the getfasta "all_genomes" BLAST DB.
#
# Supports both on-disk layouts:
#   A) all_genomes.nal EXISTS          -> alias/volume world: just append.
#   B) only all_genomes.nsq/.nin/.nhr  -> single-volume world: existing index
#      set is RENAMED to <legacy>.*, an alias all_genomes.nal is created that
#      lists [<legacy>, <new volumes...>] so every existing consumer keeps
#      working unchanged through the alias.
#
# Mutations happen ONLY with --yes. Without it the script prints the plan.
#
# Usage:
#   export PATH=/var/www/html/blast/blast+/bin:$PATH
#   bash scripts/add_volumes_to_all_genomes.sh \
#        --fasta /path/Cadenza.fa --token Cadenza --yes
#
# Repeat once per genome (each call appends one volume).
#
set -euo pipefail

FASTA=""; TOKEN=""; DB_DIR="/var/www/html/getfasta/blastdb"; NAME="all_genomes"
KEEP_HEADERS=0; YES=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --fasta)        FASTA="$2"; shift 2 ;;
        --token)        TOKEN="$2"; shift 2 ;;
        --db-dir)       DB_DIR="$2"; shift 2 ;;
        --name)         NAME="$2"; shift 2 ;;
        --keep-headers) KEEP_HEADERS=1; shift ;;
        --yes)          YES=1; shift ;;
        *) echo "unknown arg: $1" >&2; exit 2 ;;
    esac
done

[[ -n "$FASTA" && -n "$TOKEN" ]] || { echo "usage: $0 --fasta <fa> --token <Token> [--yes]" >&2; exit 2; }
[[ -f "$FASTA" ]] || { echo "[ERR] fasta not found: $FASTA" >&2; exit 2; }
echo "$TOKEN" | grep -qE '^[A-Za-z0-9._-]+$' || { echo "[ERR] bad token: $TOKEN" >&2; exit 2; }
[[ $(grep -c "^>" "$FASTA") -gt 0 ]] || { echo "[ERR] no FASTA records in $FASTA" >&2; exit 2; }

cd "$DB_DIR"
BLASTDBCMD="$(command -v blastdbcmd || echo /var/www/html/blast/blast+/bin/blastdbcmd)"
MAKEBLASTDB="$(command -v makeblastdb || echo /var/www/html/blast/blast+/bin/makeblastdb)"
VOL="${NAME}_${TOKEN}"           # per-genome volume base name
NAL="$NAME.nal"

# ---------------------------------------------------------------- header audit
# The chips/interval ecosystem expects Chr<num><letter>_<Token>-style seqids.
SAMPLE=$(grep -m 5 "^>" "$FASTA")
if echo "$SAMPLE" | grep -qE '^>[Cc]hr[0-9]' && echo "$SAMPLE" | grep -q "_$TOKEN$|_${TOKEN}"; then
    HEADER_OK=1
else
    HEADER_OK=0
fi
echo "--- header sample ---"; echo "$SAMPLE"
if [[ $HEADER_OK -eq 0 ]]; then
    cat <<EOF
[WARN] $FASTA headers do not match the expected 'Chr<..>_$TOKEN' convention.
The correct convention matters to frontend example derivation:
  head -1 renamed would look like:  >Chr1A_$TOKEN
Fix the FASTA headers before merging, e.g. (adjust the mapping!):
  sed 's/^>\\([0-9][A-Z]\\)/>Chr\\1_$TOKEN/; s/^>chr\\([0-9][A-Z]\\)/>Chr\\1_$TOKEN/' \
      "$FASTA" > "${FASTA%.fa}_renamed.fa"
Then re-run this script against the renamed file.
EOF
    if [[ $YES -eq 1 ]]; then
        echo "[--yes] proceeding despite non-standard headers (their words, your risk)"
    fi
fi

# ---------------------------------------------------------------- volume build
if [[ ! -f "$VOL.nsq" ]]; then
    PLAN="makeblastdb: $FASTA -> volume $VOL (nucl, parse_seqids)"
else
    PLAN="volume $VOL already built - reusing"
fi

# ---------------------------------------------------------------- mode detect
ALIAS_MODE=0
if [[ -f "$NAL" ]]; then
    ALIAS_MODE=1
    PLAN="$PLAN\nappend '$VOL' to existing alias $NAL"
    if grep -qx "$VOL" "$NAL"; then
        echo "[OK] $VOL already listed in $NAL - nothing to do"
        exit 0
    fi
else
    LEGACY="${NAME}__pre_alias"
    PLAN="$PLAN\nSINGLE-VOLUME LAYOUT detected:\n  mv $NAME.* -> $LEGACY.*   (indices retargeted, no data lost)\n  create new alias $NAL = [$LEGACY, $VOL]"
    [[ -f "$LEGACY.nsq" ]] && { echo "[ERR] legacy layout already prepared ($LEGACY.*) but no $NAL - inspect manually" >&2; exit 2; }
fi

echo "--- plan -------------------------------------------"
echo -e "$PLAN"
echo "----------------------------------------------------"
if [[ $YES -ne 1 ]]; then
    echo "(dry run: re-run with --yes to apply)"
    exit 0
fi

# ---------------------------------------------------------------- apply
if [[ ! -f "$VOL.nsq" ]]; then
    "$MAKEBLASTDB" -in "$FASTA" -dbtype nucl -parse_seqids \
                   -title "getfasta $TOKEN" -out "$VOL" >/dev/null
    echo "built volume $VOL"
fi

if [[ $ALIAS_MODE -eq 1 ]]; then
    cp -p "$NAL" "$NAL.bak.$(date +%Y%m%d%H%M%S)"
    COUNT=$(($(head -n 1 "$NAL") + 1))
    { echo "$COUNT"; tail -n +2 "$NAL"; echo "$VOL"; } > "$NAL.tmp"
    mv "$NAL.tmp" "$NAL"
else
    LEGACY="${NAME}__pre_alias"
    for f in "$NAME".*; do
        [[ -e "$f" ]] || continue
        ext="${f#"$NAME".}"
        mv -n "$f" "$LEGACY.$ext"
    done
    { echo "2"; echo "$LEGACY"; echo "$VOL"; } > "$NAL"
    echo "created alias $NAL = [$LEGACY, $VOL]"
fi

# ---------------------------------------------------------------- verify
FIRST_ID=$("$BLASTDBCMD" -db "$VOL" -entry all -outfmt "%a" | head -n 1)
if [[ -z "$FIRST_ID" ]]; then
    echo "[WARN] could not read back any seqid from $VOL - inspect manually"
else
    "$BLASTDBCMD" -db "$NAME" -entry "$FIRST_ID" -range 200-400 >/dev/null \
        && echo "verified: $NAME resolves $FIRST_ID through the alias"
fi
cat <<EOF

done. Next steps:
  1) clear the chromosomes cache so the API sees the new names:
       sudo systemctl restart wheatomics-api
  2) rerun examples backfill (the previously unmatched rows will now derive):
       python3 scripts/backfill_genefunc_examples.py            # dry run
       python3 scripts/backfill_genefunc_examples.py --write
EOF
