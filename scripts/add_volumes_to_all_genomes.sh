#!/usr/bin/env bash
#
# Merge per-genome volumes into the getfasta "all_genomes" BLAST DB.
#
# Two ways to run:
#   A) attach an ALREADY-BUILT BLAST volume as-is (recommended when the
#      genome exists elsewhere under blastdb, e.g. AABBDD_Cadenza.scaffold):
#        bash scripts/add_volumes_to_all_genomes.sh \
#             --use-existing-volume AABBDD_Cadenza.scaffold --yes
#
#   B) build a new volume from a FASTA file first:
#        bash scripts/add_volumes_to_all_genomes.sh \
#             --fasta /path/Cadenza.fa --token Cadenza --yes
#
# Handles both on-disk layouts of all_genomes:
#   alias world  (all_genomes.nal present)  -> volume is appended to the list
#   single volume(all_genomes.nsq/...)      -> existing indices are renamed to
#      <NAME>__pre_alias.* and an alias listing [<legacy>, <new volumes...>]
#      is created so every consumer keeps resolving "all_genomes".
#
# Mutations happen ONLY with --yes; without it you get the plan.
#
set -euo pipefail

# A volume counts as present if ANY BLAST v4/v5 index component exists.
# v5 families use .nal/.ndb/.njs/.nos/.not/.ntf/.nto instead of v4's
# .nsq/.nin/.nhr; aliases ship with .nal too.
db_volume_exists() {
    local b="$1" f
    for f in nal nsq nin nhr ndb njs nos not ntf nto pal psq pin phr; do
        [[ -e "${b}.${f}" ]] && return 0
    done
    return 1
}

FASTA=""; TOKEN=""; DB_DIR="/var/www/html/getfasta/blastdb"; NAME="all_genomes"
EXISTING_VOL=""; YES=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --fasta)               FASTA="$2"; shift 2 ;;
        --token)               TOKEN="$2"; shift 2 ;;
        --use-existing-volume) EXISTING_VOL="$2"; shift 2 ;;
        --db-dir)              DB_DIR="$2"; shift 2 ;;
        --name)                NAME="$2"; shift 2 ;;
        --yes)                 YES=1; shift ;;
        *) echo "unknown arg: $1" >&2; exit 2 ;;
    esac
done

cd "$DB_DIR"
BLASTDBCMD="$(command -v blastdbcmd || echo /var/www/html/blast/blast+/bin/blastdbcmd)"
MAKEBLASTDB="$(command -v makeblastdb || echo /var/www/html/blast/blast+/bin/makeblastdb)"
NAL="$NAME.nal"

if [[ -n "$EXISTING_VOL" ]]; then
    VOL="$EXISTING_VOL"
    db_volume_exists "$VOL" \
        || { echo "[ERR] volume indexes not found under $DB_DIR: $VOL.(nal|nsq|nin|...)" >&2; exit 2; }
    TOKEN="${VOL##*_}"          # display helper only
else
    [[ -n "$FASTA" && -n "$TOKEN" ]] \
        || { echo "usage: (--fasta <fa> --token <Token>) | (--use-existing-volume <base>) [--yes]" >&2; exit 2; }
    [[ -f "$FASTA" ]] || { echo "[ERR] fasta not found: $FASTA" >&2; exit 2; }
fi

# ---------------------------------------------------------------- header audit
# (skipped entirely in --use-existing-volume mode)
HEADER_OK=1
if [[ -z "$EXISTING_VOL" ]]; then
    SAMPLE=$(grep -m 5 "^>" "$FASTA")
    echo "--- header sample ---"; echo "$SAMPLE"
    if echo "$SAMPLE" | grep -qE "^>[Cc]hr[0-9]" && echo "$SAMPLE" | grep -qE "_${TOKEN}($|[^A-Za-z0-9])"; then
        :   # headers look right
    else
        HEADER_OK=0
        cat <<WOF
[WARN] $FASTA headers do not match the expected Chr<num><letter>_$TOKEN convention.
Rename before merging, e.g.:
  sed -E "s/^>(chr)?([0-9][A-Z])(_|\$)/Chr\\2_$TOKEN\\3/I" "$FASTA" > renamed_$TOKEN.fa
then re-run this script against renamed_$TOKEN.fa.
WOF
        if [[ $YES -eq 1 ]]; then
            echo "[--yes] proceeding despite non-standard headers (their words, your risk)"
        fi
    fi
fi

if [[ -n "$EXISTING_VOL" ]]; then
    PLAN="attach existing volume $VOL as-is"
elif db_volume_exists "${NAME}_${TOKEN}"; then
    VOL="${NAME}_${TOKEN}"
    PLAN="reuse built volume $VOL"
else
    VOL="${NAME}_${TOKEN}"
    PLAN="makeblastdb: $FASTA -> $VOL (nucl, parse_seqids)"
fi
[[ -n "$EXISTING_VOL" ]] || :   # keep set -u happy for later references

# ---------------------------------------------------------------- mode detect
ALIAS_MODE=0
if [[ -f "$NAL" ]]; then
    ALIAS_MODE=1
    PLAN="$PLAN / append $VOL to existing alias $NAL"
    if grep -qx "$VOL" "$NAL"; then
        echo "[OK] $VOL already listed in $NAL - nothing to do"
        exit 0
    fi
else
    LEGACY="${NAME}__pre_alias"
    PLAN="$PLAN / SINGLE-VOLUME LAYOUT: mv $NAME.* -> $LEGACY.*, create alias $NAL = [$LEGACY, $VOL]"
    [[ -f "$LEGACY.nsq" ]] \
        && { echo "[ERR] legacy prepared ($LEGACY.*) but $NAL missing - inspect manually" >&2; exit 2; }
fi

echo "--- plan ---"; echo "$PLAN"
if [[ $YES -ne 1 ]]; then
    echo "(dry run: re-run with --yes to apply)"; exit 0
fi

# ---------------------------------------------------------------- apply
if [[ -z "$EXISTING_VOL" ]] && ! db_volume_exists "$VOL"; then
    "$MAKEBLASTDB" -in "$FASTA" -dbtype nucl -parse_seqids \
                   -title "getfasta $TOKEN" -out "$VOL" >/dev/null
    echo "built volume $VOL"
fi

if [[ $ALIAS_MODE -eq 1 ]]; then
    cp -p "$NAL" "$NAL.bak.$(date +%Y%m%d%H%M%S)"
    echo "[info] current first line of $NAL: $(head -n 1 "$NAL")"
    # Tolerant parse: if line 1 is the volume-count integer, treat the rest
    # as the list; otherwise assume the WHOLE file lists volumes (some
    # hand-made .nal variants carry other headers).
    FIRST=$(head -n 1 "$NAL")
    if [[ "$FIRST" =~ ^[0-9]+[[:space:]]*$ ]]; then
        LIST=$(tail -n +2 "$NAL")
    else
        LIST=$(cat "$NAL")
        echo "[WARN] non-standard $NAL header replaced (backup kept)."
    fi
    NEWLIST=$(printf '%s\n%s\n' "$LIST" "$VOL" | grep -v '^$' | awk '!seen[$0]++')
    COUNT=$(printf '%s\n' "$NEWLIST" | grep -c .)
    { echo "$COUNT"; echo "$NEWLIST"; } > "$NAL.tmp"
    mv "$NAL.tmp" "$NAL"
    echo "appended $VOL to $NAL (now $COUNT volumes)"
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
    echo "[WARN] no seqid readable from $VOL - inspect manually"
else
    "$BLASTDBCMD" -db "$NAME" -entry "$FIRST_ID" -range 200-400 >/dev/null \
        && echo "verified: $NAME resolves $FIRST_ID through the alias"
fi
cat <<EOF

done. Next steps:
  1) clear the chromosomes cache so the API sees the new names:
       sudo systemctl restart wheatomics-api
  2) rerun examples backfill:
       python3 scripts/backfill_genefunc_examples.py            # dry run
       python3 scripts/backfill_genefunc_examples.py --write
EOF
