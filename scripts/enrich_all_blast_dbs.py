#!/usr/bin/env python3
"""Audit/enrich all BLAST CDS and protein FASTA headers from Genefunc tables.

The script is designed for a staged rebuild:
  audit -> per-DB enriched FASTA + checksum -> backup old DB -> makeblastdb
  into a staging dir -> atomically move the rebuilt DB back under the old name.

Annotation priority:
  1. genome_registry.gene_table (with manual overrides for known mismatches)
  2. fields already present in the old BLAST FASTA header
  3. leave the header unchanged and report it

Only FASTA headers are changed. Sequence checksums are checked before the
old BLAST DB is replaced.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path('/var/www/FastAPI_backend_Port8000')
sys.path.insert(0, str(ROOT))

from app.core.config import settings  # noqa: E402
from app.db.mysql import mysql_cursor  # noqa: E402

DB_DIR = Path('/var/www/html/getfasta/blastdb')
STAGE_DIR = Path('/var/www/html/getfasta/blastdb_rebuild_stage')
BACKUP_DIR = Path('/var/www/html/getfasta/blastdb_backup_20261027')
BLASTDBCMD = '/usr/bin/blastdbcmd'
MAKEBLASTDB = '/usr/bin/makeblastdb'
NULL = {'', 'null', 'none', '-', '.', 'na', 'n/a', 'nan'}

MANUAL_TABLES = {
    'AABBBDD_Chinese_Spring1.1': 'Genefunc_CS_IWGSC03G_table',
    'AABBDD_Chinese_Spring1.1': 'Genefunc_CS_IWGSC03G_table',
    'AABBDD_CS-CAU': 'Genefunc_AABBDD_CS_CNAU_table',
    'AABBDD_Paragon_scaffolds': 'Genefunc_AABBDD_Paragon_scaffolds_table',
    'AABBDD_Robigus_scaffolds': 'Genefunc_AABBDD_Robigus_scaffolds_table',
    'AABBDD_Weebill_scaffolds': 'Genefunc_AABBDD_Weebill_scaffolds_table',
    'StStYYHH_Elymus_nutans_Griseb': 'Genefunc_Elymus_nutans_Griseb_table',
}

GFF_SOURCES = {
    'AABBDD_Kariega': '/var/www/data/tiantian_data/wheat_genome/extra_annotations/Kariega_v1_annotations/Kariega_v1.gff3',
    'DD_tauschii_Luo': '/var/www/data/tiantian_data/wheat_genome/gff/tauschii_Luo.gff3',
    'AA_TA10622': '/var/www/data/tiantian_data/wheat_genome/extra_annotations/TA10622/T_monococcum_TA10622_LC.gff3',
    'HH_Morex': '/var/www/data/tiantian_data/wheat_genome/extra_annotations/Morex_barpg2_all.s.gff.gz',
    'AABBDD_ae.stanley_PGSBv2.2': '/var/www/data/tiantian_data/wheat_genome/gff/Stanley.ensembl.gff3.gz',
}


def clean(v) -> str | None:
    if v is None:
        return None
    text = re.sub(r'\s+', ' ', str(v)).strip()
    return None if text.lower() in NULL else text


def strand(v) -> str:
    v = (str(v or '')).strip()
    return v if v in ('+', '-') else '.'


def norm_id(v: str) -> str:
    v = (v or '').strip().split('|')[-1]
    return re.sub(r'\.\d+$', '', v)


def id_variants(v: str) -> set[str]:
    """Common transcript-ID spellings across old/new annotation tables."""
    v = (v or '').strip().split('|')[-1]
    out = {v, norm_id(v)}
    # T. urartu tables use .1 where the FASTA uses .m1.
    m = re.sub(r'\.m\d+$', '', v)
    out.add(m); out.add(norm_id(m))
    # Some old tables omit the LC suffix before the transcript version.
    lc = re.sub(r'LC(?:\.\d+)?$', '', v)
    out.add(lc); out.add(norm_id(lc))
    # RefSeq CDS FASTA ids embed XP_/NP_ accessions used by GFF protein_id.
    out.update(re.findall(r'(?:XP|NP|XM|XR)_\d+\.\d+', v))
    return {x for x in out if x}


def get_bases() -> list[str]:
    bases: set[str] = set()
    for pattern, suffix in (('*.add_Description.cds', '.add_Description.cds'),
                            ('*.add_Description.pep', '.add_Description.pep'),
                            ('*.add_Description.cds.*', '.add_Description.cds'),
                            ('*.add_Description.pep.*', '.add_Description.pep')):
        for p in DB_DIR.glob(pattern):
            marker = p.name.find(suffix)
            if marker > 0:
                bases.add(p.name[:marker])
    return sorted(bases)


def load_registry() -> dict[str, dict]:
    with mysql_cursor(settings.DB_LITERATURE) as cur:
        cur.execute("SELECT dataset_id,blast_cds_db,blast_pep_db,gene_table,display_name FROM genome_registry")
        rows = cur.fetchall()
    out = {}
    for r in rows:
        for key in ('blast_cds_db', 'blast_pep_db'):
            v = (r.get(key) or '').strip()
            if not v:
                continue
            base = v
            for suffix in ('.add_Description.cds', '.add_Description.pep'):
                if base.endswith(suffix):
                    base = base[:-len(suffix)]
            out.setdefault(base, r)
    return out


def table_columns(table: str) -> list[str]:
    with mysql_cursor(settings.DB_GENEFUNC) as cur:
        cur.execute("SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s",
                    (settings.DB_GENEFUNC, table))
        return [r['COLUMN_NAME'] for r in cur.fetchall()]


def load_annotations(table: str) -> dict[str, dict]:
    cols = table_columns(table)
    gene_cols = [c for c in ('Gene', 'Gene02G', 'Gene03G') if c in cols]
    if not gene_cols:
        return {}
    wanted = [c for c in ('Chrom', 'Start1', 'End1', 'Strand', 'Description', 'Domain', 'ChineseSpring02G') if c in cols]
    select = ','.join(f'`{c}`' for c in gene_cols + wanted)
    out = {}
    with mysql_cursor(settings.DB_GENEFUNC) as cur:
        cur.execute(f'SELECT {select} FROM `{table}`')
        for row in cur.fetchall():
            ann = {c: clean(row.get(c)) for c in wanted}
            ann['_start_offset'] = 1
            if 'Strand' in wanted:
                ann['Strand'] = strand(row.get('Strand'))
            for col in gene_cols:
                gid = clean(row.get(col))
                if gid:
                    for variant in id_variants(gid):
                        out.setdefault(variant, ann)
    return out


def _gff_attrs(text: str) -> dict[str, str]:
    out = {}
    for item in text.strip().split(';'):
        if '=' in item:
            k, v = item.split('=', 1)
            out[k.strip()] = v.strip()
    return out


def _gff_token_variants(text: str) -> set[str]:
    text = text.strip()
    if ':' in text:
        text = text.split(':', 1)[1]
    out = {text}
    for token in re.findall(r'(?:XP|NP|XM|XR)_\d+\.\d+', text):
        out.add(token)
    out.update(id_variants(text))
    return out


def load_gff_annotations(path: Path) -> dict[str, dict]:
    """Load gene/mRNA/CDS coordinates and descriptions from a GFF3."""
    out: dict[str, dict] = {}
    # Aggregate CDS segments per parent feature.
    cds_span: dict[str, list] = {}
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(path, 'rt', encoding='utf-8', errors='ignore') as fh:
        for line in fh:
            if not line or line.startswith('#'):
                continue
            p = line.rstrip('\n').split('\t')
            if len(p) < 9:
                continue
            chrom, feat, start, end, strand, attrs = p[0], p[2], p[3], p[4], p[6], _gff_attrs(p[8])
            try:
                start_i, end_i = int(start), int(end)
            except ValueError:
                continue
            description = clean(attrs.get('product') or attrs.get('description') or attrs.get('Note'))
            cs02g = clean(attrs.get('ChineseSpring02G'))
            keys = set()
            for k in ('ID', 'Name', 'protein_id', 'gene', 'Parent', 'transcript_id', 'gene_id'):
                v = attrs.get(k)
                if v:
                    keys.update(_gff_token_variants(v))
            ann = {'Chrom': chrom, 'Start1': start_i, 'End1': end_i,
                   'Strand': strand, 'Description': description, 'ChineseSpring02G': cs02g,
                   '_start_offset': 0}
            for key in keys:
                out.setdefault(key, ann)
            if feat in ('CDS', 'exon'):
                parent = attrs.get('Parent') or attrs.get('ID')
                if parent:
                    span = cds_span.setdefault(parent, [chrom, start_i, end_i, strand, description, cs02g, set()])
                    span[1] = min(span[1], start_i)
                    span[2] = max(span[2], end_i)
                    span[6].update(keys)
    # Prefer the aggregated CDS span over a single CDS segment.
    for parent, span in cds_span.items():
        chrom, start_i, end_i, strand, description, cs02g, keys = span
        ann = {'Chrom': chrom, 'Start1': start_i, 'End1': end_i, 'Strand': strand,
               'Description': description, 'ChineseSpring02G': cs02g, '_start_offset': 0}
        for key in keys | {parent}:
            out[key] = ann
    return out


def first_ids(db: Path, n=5) -> list[str]:
    p = subprocess.Popen([BLASTDBCMD, '-db', str(db), '-entry', 'all'],
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                         text=True, errors='ignore')
    ids = []
    try:
        for line in p.stdout:
            if line.startswith('>'):
                ids.append(line[1:].split()[0])
                if len(ids) >= n:
                    break
    finally:
        p.terminate()
        try:
            p.wait(timeout=2)
        except Exception:
            p.kill()
    return ids


def parse_old_header(header: str) -> dict:
    """Extract fields present in legacy headers as a fallback."""
    out = {}
    m = re.search(r'(?:loc=|loc:)?([\w.\-]+)\(([+-])\)(\d+)-(\d+)', header)
    if m:
        out['chrom'], out['strand'] = m.group(1), m.group(2)
        out['start'], out['end'] = int(m.group(3)), int(m.group(4))
    else:
        m = re.search(r'(?:loc=)?([\w.\-]+):(\d+)-(\d+)\s+([+-])', header)
        if m:
            out['chrom'], out['start'], out['end'], out['strand'] = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4)
    m = re.search(r'Description=(.*?)(?=\s+[A-Za-z][\w]*=|$)', header)
    if m:
        out['description'] = m.group(1).strip()
    else:
        # Legacy headers: "ID Chr:start-end strand Free-text ChineseSpring02G_ID:..."
        m = re.search(r'\s[+-]\s+(.+?)\s+(?:ChineseSpring02G_ID:|ChineseSpring02G=)', header)
        if m:
            out['description'] = m.group(1).strip()
    m = re.search(r'China(?:Spring|seSpring)02G(?:=|_ID:)(\S+)', header)
    if m:
        out['cs02g'] = m.group(1)
    m = re.search(r'Domain=(.*?)(?=\s+[A-Za-z][\w]*=|$)', header)
    if m:
        out['domain'] = m.group(1).strip()
    return out


def compose_header(gid: str, old: str, ann: dict | None) -> tuple[str, bool]:
    old_fields = parse_old_header(old)
    a = dict(old_fields)
    start_from_table = bool(ann and ann.get('_start_offset'))
    if ann:
        for k_src, k_dst in (('Chrom', 'chrom'), ('Start1', 'start'), ('End1', 'end'),
                             ('Description', 'description'),
                             ('Domain', 'domain'), ('ChineseSpring02G', 'cs02g')):
            v = clean(ann.get(k_src))
            if v:
                a[k_dst] = v
        table_strand = strand(ann.get('Strand'))
        if table_strand != '.':
            a['strand'] = table_strand
    chrom = clean(a.get('chrom'))
    start, end = a.get('start'), a.get('end')
    if not chrom or not start or not end:
        return old, False
    # Genefunc/BED Start1 is 0-based; GFF/BLAST headers are 1-based inclusive.
    if start_from_table:
        start = int(start) + 1
    parts = [gid, f'loc={chrom}:{start}-{end}', f'strand={strand(a.get("strand"))}']
    if a.get('description'):
        parts.append('Description=' + str(a['description']))
    if a.get('domain'):
        parts.append('Domain=' + str(a['domain']))
    if a.get('cs02g'):
        parts.append('ChineseSpring02G=' + str(a['cs02g']))
    return ' '.join(parts), True


def dump_and_enrich(db: Path, ann: dict, out_path: Path) -> dict:
    p = subprocess.Popen([BLASTDBCMD, '-db', str(db), '-entry', 'all'],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, errors='ignore')
    total = matched = 0
    old_hash = hashlib.sha256()
    new_hash = hashlib.sha256()
    header = None
    seq_lines = []
    examples = []

    def flush():
        nonlocal matched
        if header is None:
            return
        old_title = header[1:]
        gid = old_title.split()[0]
        text, ok = compose_header(gid, old_title, next((ann[v] for v in [gid, *id_variants(gid)] if v in ann), None))
        if ok:
            matched += 1
            if len(examples) < 2:
                examples.append({'id': gid, 'new': text})
        out_f.write('>' + text + '\n')
        out_f.writelines(seq_lines)
        old_hash.update(''.join(x.strip() for x in seq_lines).upper().encode())
        new_hash.update(''.join(x.strip() for x in seq_lines).upper().encode())

    with out_path.open('w', encoding='utf-8') as out_f:
        for line in p.stdout:
            if line.startswith('>'):
                flush()
                header = line.rstrip('\n')
                seq_lines = []
                total += 1
            elif header is not None:
                seq_lines.append(line)
        flush()
    err = (p.stderr.read() or '').strip()
    rc = p.wait()
    if rc != 0:
        raise RuntimeError(f'blastdbcmd failed for {db}: {err[:300]}')
    return {'total': total, 'matched': matched, 'old_checksum': f'{total}:{old_hash.hexdigest()}',
            'new_checksum': f'{total}:{new_hash.hexdigest()}', 'examples': examples}


def build_stage(fasta: Path, base: str, dbtype: str, stage: Path) -> list[Path]:
    stage.mkdir(parents=True, exist_ok=True)
    out = stage / base
    cmd = [MAKEBLASTDB, '-in', str(fasta), '-dbtype', dbtype, '-parse_seqids', '-out', str(out)]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f'makeblastdb failed for {base}: {(proc.stderr or proc.stdout)[:500]}')
    return sorted(stage.glob(base + '.*'))


def backup_db(base: str) -> list[tuple[Path, Path]]:
    dest = BACKUP_DIR / base
    if dest.exists():
        dest = BACKUP_DIR / (base + '.rerun-' + time.strftime('%Y%m%d_%H%M%S'))
    dest.mkdir(parents=True, exist_ok=True)
    moved = []
    for src in sorted(DB_DIR.glob(base + '.*')):
        if not src.is_file():
            continue
        target = dest / src.name
        if target.exists():
            target.unlink()
        shutil.move(str(src), str(target))
        moved.append((target, src))
    return moved


def restore(moved):
    for target, src in moved:
        if target.exists() and not src.exists():
            shutil.move(str(target), str(src))


def process_base(base: str, registry: dict, apply: bool) -> dict:
    rec = registry.get(base, {})
    table = MANUAL_TABLES.get(base) or rec.get('gene_table')
    result = {'base': base, 'table': table, 'cds': None, 'pep': None}
    if not table:
        result['error'] = 'no gene_table'
        return result
    try:
        ann = load_annotations(table)
    except Exception as exc:
        result['error'] = f'load table: {exc}'
        return result
    gff_path = GFF_SOURCES.get(base)
    if gff_path and Path(gff_path).exists():
        try:
            gff_ann = load_gff_annotations(Path(gff_path))
            ann.update(gff_ann)
            result['gff'] = gff_path
        except Exception as exc:
            result['gff_error'] = str(exc)
    result['annotations'] = len(ann)
    for kind, suffix, dbtype in (('cds', '.add_Description.cds', 'nucl'), ('pep', '.add_Description.pep', 'prot')):
        db = DB_DIR / (base + suffix)
        # BLAST v5 stores *.psq/*.phr files without the base FASTA name.
        if not db.exists() and not list(DB_DIR.glob(db.name + '.*')):
            continue
        work = STAGE_DIR / base / kind
        work.mkdir(parents=True, exist_ok=True)
        fasta = work / ('enriched' + ('.cds' if kind == 'cds' else '.pep'))
        try:
            rep = dump_and_enrich(db, ann, fasta)
        except Exception as exc:
            result[kind] = {'error': f'enrich: {exc}'}
            continue
        rep['fasta'] = str(fasta)
        rep['dbtype'] = dbtype
        if not apply:
            result[kind] = rep
            continue
        if rep['old_checksum'] != rep['new_checksum']:
            result[kind] = {'error': 'sequence checksum mismatch', **rep}
            continue
        try:
            backup = backup_db(base + suffix)
            files = build_stage(fasta, base + suffix, dbtype, work)
            for f in files:
                shutil.move(str(f), str(DB_DIR / f.name))
            rep['backup'] = str(BACKUP_DIR / (base + suffix))
            result[kind] = rep
        except Exception as exc:
            result[kind] = {'error': f'rebuild: {exc}', **rep}
            # best effort rollback: remove partial new files, restore backup
            try:
                for f in DB_DIR.glob(base + suffix + '.*'):
                    f.unlink()
                restore(backup)
            except Exception:
                pass
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--audit', action='store_true')
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--only', help='comma-separated base names')
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--report', type=Path, default=Path('/tmp/enrich_all_blast_report.json'))
    args = ap.parse_args()
    bases = get_bases()
    if args.only:
        wanted = {x.strip() for x in args.only.split(',') if x.strip()}
        bases = [b for b in bases if b in wanted]
    if args.limit:
        bases = bases[:args.limit]
    registry = load_registry()
    if args.audit:
        rows = []
        for b in bases:
            rec = registry.get(b, {})
            table = rec.get('gene_table') or MANUAL_TABLES.get(b)
            db = DB_DIR / (b + '.add_Description.cds')
            ids = first_ids(db) if db.exists() else []
            rows.append({'base': b, 'table': table, 'first_ids': ids[:2]})
        args.report.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    results = []
    for b in bases:
        print('PROCESS', b, flush=True)
        results.append(process_base(b, registry, args.apply))
        args.report.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
