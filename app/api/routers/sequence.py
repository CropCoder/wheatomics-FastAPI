"""Sequence retrieval and precomputed BLAST routes."""

from __future__ import annotations

import re
import importlib.util
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from app.core.config import settings
from app.core.exceptions import ResourceNotFound, ValidationFailure
from app.core.response import ok
from app.core.security import PREBLAST_TABLES, REGION_PATTERN, ensure_allowed_table, ensure_gene_like, ensure_interval_like
from app.db.mysql import mysql_cursor
from app.schemas.sequence import SequenceBundle, SequenceRecord
from app.services.command_runner import run_command

router = APIRouter(tags=["Sequences"])
blast_extra_router = APIRouter(tags=["BLAST"])


def _blastdbcmd_path() -> str:
    """Locate blastdbcmd binary. Prefer settings.BLAST_BIN_DIR, fall back to
    common system paths. Mirrors _find_blast_prog in blast.py.
    """
    candidates = [
        settings.BLAST_BIN_DIR / "blastdbcmd",
        Path("/usr/bin/blastdbcmd"),
        Path("/usr/local/bin/blastdbcmd"),
        Path("/home/fei/mambaforge/envs/zjw/bin/blastdbcmd"),
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    # Return default; run_command will surface a clear error if missing
    return str(settings.BLAST_BIN_DIR / "blastdbcmd")


def _blastdbcmd(*args: str, stdin_data: str | None = None) -> str:
    """Run blastdbcmd and return trimmed stdout.

    `stdin_data` (if given) is piped to the process — used for `-entry_batch -`.
    """
    result = run_command([_blastdbcmd_path(), *args], stdin=stdin_data)
    return result.stdout.strip()


def _check_db_exists(db_path: Path) -> bool:
    """A BLAST DB is a set of index files (.nsq/.nin/.nhr or .psq/.pin/.phr),
    not necessarily a single path. Return True if any of those exist.

    We don't trust Path.exists() because the user may pass a basename
    (e.g. "all_genomes") and BLAST searches for all_genomes.nsq etc.
    """
    for ext in (".nsq", ".nin", ".nhr", ".nal",   # nucleotide
                ".psq", ".pin", ".phr", ".pal"):   # protein
        if (db_path.parent / (db_path.name + ext)).exists():
            return True
    # Also accept a literal directory containing index files
    if db_path.is_dir():
        for ext in (".nsq", ".psq"):
            if any(db_path.glob("*" + ext)):
                return True
    return False


def _try_interval(database: Path, chrom: str, start: int, end: int) -> str:
    """Try fetching interval with case-tolerant chromosome name matching (chr / Chr prefix)."""

    from app.core.exceptions import ExternalToolFailure

    candidates = [chrom]
    if chrom.startswith("Chr"):
        candidates.append("chr" + chrom[3:])
    elif chrom.startswith("chr"):
        candidates.append("Chr" + chrom[3:])

    last_error: Exception | None = None
    for name in candidates:
        try:
            return _blastdbcmd(
                "-db", str(database),
                "-line_length", "110",
                "-entry", name,
                "-range", f"{start}-{end}",
                "-strand", "plus",
            )
        except ExternalToolFailure as e:
            last_error = e
            continue

    raise ValidationFailure(
        f"Chromosome {chrom!r} not found in database. "
        "Check the naming convention at "
        "https://wheatomics.sdau.edu.cn/doc/getsequence_search.txt"
    )


@router.get("/sequence/by-gene")
def sequence_by_gene(
    gene_id: str = Query(...),
    gene_db: str | None = Query(None, description="CDS / genomic BLAST DB. Omit to skip CDS lookup."),
    protein_db: str | None = Query(None, description="Protein BLAST DB. Omit to skip protein lookup."),
) -> SequenceBundle:
    """根据基因 ID 获取基因和蛋白质序列（FASTA 格式）。

    功能:
        通过 blastdbcmd 工具，根据基因 ID 从本地 BLAST 数据库中提取
        对应的基因序列（CDS）和蛋白质序列。如果基因 ID 不以 .1 结尾，
        将自动追加 .1 后缀进行查找。

    用法:
        GET /api/sequence/by-gene?gene_id=<基因ID>&gene_db=<基因库>&protein_db=<蛋白库>
        - gene_id: 必填，如 TraesCS5A02G391700
        - gene_db: 可选，基因 BLAST 数据库名，默认 all_gene
        - protein_db: 可选，蛋白 BLAST 数据库名，默认 all_protein

    案例:
        请求:
          curl -X GET "http://localhost:8000/api/sequence/by-gene?gene_id=TraesCS5A02G391700"

        响应:
          {
            "gene_id": "TraesCS5A02G391700",
            "gene_sequence": ">TraesCS5A02G391700.1\nATGGCG...",
            "protein_sequence": ">TraesCS5A02G391700.1\nMAGD..."
          }
    """

    gene_id = ensure_gene_like(gene_id)
    # Detect interval-shaped input (chr:start-end) in gene_id and reject with
    # a friendly 400 pointing to /api/sequence/by-interval.
    if REGION_PATTERN.match(gene_id):
        raise ValidationFailure(
            f"'{gene_id[:60]}...' looks like a chromosomal interval, not a gene ID. "
            f"Use /api/sequence/by-interval?region=<chr:start-end> instead."
        )
    gene_entry = gene_id if gene_id.endswith(".1") else f"{gene_id}.1"

    bundle = SequenceBundle(gene_id=gene_id)
    if gene_db:
        try:
            bundle.gene_sequence = _blastdbcmd("-db", str(settings.BLAST_DB_PATH / gene_db), "-entry", gene_entry)
        except Exception:
            bundle.gene_sequence = None
    else:
        bundle.gene_sequence = None
    if protein_db:
        try:
            bundle.protein_sequence = _blastdbcmd("-db", str(settings.BLAST_DB_PATH / protein_db), "-entry", gene_entry)
        except Exception:
            bundle.protein_sequence = None
    else:
        bundle.protein_sequence = None

    if not bundle.gene_sequence and not bundle.protein_sequence:
        raise ResourceNotFound(f"No sequence found for {gene_id}")
    return bundle


@router.get("/sequence/by-interval")
def sequence_by_interval(
    region: str = Query(...,
        description="Genomic interval, e.g. Chr1A_Abo:200-500. "
                    "See https://wheatomics.sdau.edu.cn/doc/getsequence_search.txt for the full list of genome-specific chromosome naming conventions."),
    database: str = Query(...,
        description="BLAST database name. For genome-wide queries use the aggregated databases:\n"
                    "  - all_genomes   (genomic sequences, recommended for interval queries)\n"
                    "  - all_gene      (gene CDS)\n"
                    "  - all_protein   (protein)\n"
                    "See GET /api/blast/databases?program=blastn for the full list.")
) -> dict:
    """Get genomic FASTA sequence by chromosome interval.

    Chromosome naming follows genome-specific conventions.
    See the full reference at:
    https://wheatomics.sdau.edu.cn/doc/getsequence_search.txt

    Examples:
      - Hexaploid wheat (Abbondanza):     Chr1A_Abo:200-500
      - Hexaploid wheat (Chinese Spring): chr1A:200-500
      - Barley v3:                         chr1H_Barley3:200-500
      - Aegilops tauschii TA1675:          chr1D_Aegilops_tauschii_TA1675:200-500
      - Wild emmer:                        chr1A_Wild_emmer:200-500
    """

    ensure_interval_like(region)

    chrom = region.split(":")[0]
    interval = region.split(":")[1].replace("..", "-")
    start_text, end_text = interval.split("-")
    start, end = int(start_text), int(end_text)
    if end <= start or end - start > 5_000_000:
        raise ValidationFailure("Region length must be > 0 and <= 5,000,000 bp")

    fasta = _try_interval(settings.BLAST_DB_PATH / database, chrom, start, end)
    return ok({"region": region, "database": database, "fasta": fasta})


@router.get("/sequence/batch")
def batch_sequence(
    database: str = Query(...),
    ids: str = Query(..., alias="ID"),
) -> dict:
    """批量获取多个基因/区间的 FASTA 序列。

    功能:
        一次性查询多个基因 ID 或基因组区间。ID 用空格分隔
        （URL 中可用 %20 或 + 编码空格）。基因 ID 自动补充转录本版本号 .1。
        区间格式：chr:start-end（如 Chr1A_Chinese_Spring1.0:200-500）。

    用法:
        GET /api/sequence/batch?ID=<id1 id2>&database=<数据库名>

    案例:
        curl -X GET "http://localhost:8000/api/sequence/batch?ID=TraesCS5A02G391700%20TraesCS5A02G391701&database=all_gene"
        curl -X GET "http://localhost:8000/api/sequence/batch?ID=Chr1A:200-500%20Chr5B:1000-2000&database=all_genomes"

    响应:
        {
          "success": true,
          "data": {
            "database": "...",
            "records": [
              {"sequence_id": "Chr1A:200-500", "fasta": ">Chr1A:200-500\n..."},
              ...
            ]
          }
        }
    """

    import re
    from concurrent.futures import ThreadPoolExecutor

    from app.core.exceptions import ExternalToolFailure

    raw_tokens = [t.strip() for t in ids.split() if t.strip()]
    if not raw_tokens:
        raise HTTPException(status_code=400, detail="ID parameter is empty")

    db_path = settings.BLAST_DB_PATH / database
    # BLAST databases are a set of index files (.nsq/.nin/.nhr for nucleotide,
    # .psq/.pin/.phr for protein), not a single path. Check via blastdbcmd.
    if not _check_db_exists(db_path):
        raise HTTPException(status_code=404, detail=f"Database not found: {database}")

    interval_re = re.compile(r"^([^:]+):(\d+)-(\d+)$")

    # Partition into two buckets:
    #   - gene_ids: tokens without ":" → fetch in ONE blastdbcmd call via -entry_batch stdin
    #   - ranges:   tokens matching "chr:start-end" → fetched in parallel threads
    #              (blastdbcmd has no native batch mode for -range)
    gene_ids = []
    gene_tokens = []   # original tokens in the same order
    range_jobs = []    # (token, chrom, start, end)
    for token in raw_tokens:
        m = interval_re.match(token)
        if m:
            range_jobs.append((token, m.group(1), int(m.group(2)), int(m.group(3))))
        else:
            entry = token if token.endswith(".1") else f"{token}.1"
            gene_tokens.append(token)
            gene_ids.append(entry)

    records_by_token: dict[str, dict] = {}

    # ---- 1) Genes: single blastdbcmd -entry_batch - call ----
    if gene_ids:
        try:
            stdout = _blastdbcmd("-db", str(db_path), "-entry_batch", "-",
                                  stdin_data="\n".join(gene_ids) + "\n")
            blocks: dict[str, str] = {}
            cur_id = None
            cur_lines: list[str] = []
            for line in stdout.splitlines():
                if line.startswith(">"):
                    if cur_id is not None:
                        blocks[cur_id] = ">" + cur_id + "\n" + "\n".join(cur_lines)
                    cur_id = line[1:].split()[0]
                    cur_lines = []
                else:
                    cur_lines.append(line)
            if cur_id is not None:
                blocks[cur_id] = ">" + cur_id + "\n" + "\n".join(cur_lines)

            for token, entry in zip(gene_tokens, gene_ids):
                if entry in blocks:
                    records_by_token[token] = {"sequence_id": token, "fasta": blocks[entry], "ok": True}
                else:
                    records_by_token[token] = {"sequence_id": token, "fasta": "", "ok": False,
                                                "error": f"Entry not found: {entry}"}
        except ExternalToolFailure as e:
            err = str(e)[:300]
            for token in gene_tokens:
                records_by_token[token] = {"sequence_id": token, "fasta": "", "ok": False, "error": err}
        except Exception as e:  # noqa: BLE001
            err = repr(e)[:300]
            for token in gene_tokens:
                records_by_token[token] = {"sequence_id": token, "fasta": "", "ok": False, "error": err}

    # ---- 2) Ranges: parallel _try_interval calls ----
    def _fetch_range(job: tuple) -> dict:
        token, chrom, start, end = job
        try:
            fasta = _try_interval(db_path, chrom, start, end)
            return {"sequence_id": token, "fasta": fasta, "ok": True}
        except Exception as e:  # noqa: BLE001
            return {"sequence_id": token, "fasta": "", "ok": False, "error": repr(e)[:300]}

    if range_jobs:
        with ThreadPoolExecutor(max_workers=min(8, len(range_jobs))) as pool:
            for r in pool.map(_fetch_range, range_jobs):
                records_by_token[r["sequence_id"]] = r

    # Preserve input order
    records = [records_by_token[t] for t in raw_tokens]
    succeeded = sum(1 for r in records if r.get("ok"))
    return ok({
        "database": database,
        "requested": len(records),
        "succeeded": succeeded,
        "failed": len(records) - succeeded,
        "records": records,
    })


@router.get("/novabrowse")
def novabrowse_run(
    chrom: str = Query(...),
    start: int = Query(..., ge=1),
    end: int = Query(..., ge=1),
) -> dict:
    """启动 NovaBrowse 基因组可视化工作流。

    功能:
        根据染色体和起止位置，动态加载并运行 NovaBrowse 服务模块，
        生成基因组区间可视化结果页面。返回任务 ID 和结果页面的 URL。

    用法:
        GET /api/novabrowse?chrom=<染色体>&start=<起始>&end=<结束>
        - chrom: 必填，染色体名称
        - start: 必填，起始位置（>=1）
        - end: 必填，结束位置（>=1，必须大于 start）

    案例:
        请求:
          curl -X GET "http://localhost:8000/api/novabrowse?chrom=chr5A&start=587000000&end=588000000"

        响应:
          {
            "success": true,
            "data": {
              "run_id": "abc123",
              "url": "http://wheatomics.sdau.edu.cn/novabrowse/abc123/output.html"
            }
          }
    """

    if end <= start:
        raise ValidationFailure("end must be greater than start")

    module_path = settings.NOVABROWSE_SERVICE_DIR / "run_novabrowse.py"
    if not module_path.exists():
        raise ResourceNotFound(f"NovaBrowse service module not found: {module_path}")

    spec = importlib.util.spec_from_file_location("run_novabrowse", module_path)
    if spec is None or spec.loader is None:
        raise ResourceNotFound("Unable to load NovaBrowse service module")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("run_novabrowse", module)
    spec.loader.exec_module(module)
    run_id = module.run(chrom, start, end)
    return ok({"run_id": run_id, "url": f"{settings.NOVABROWSE_RESULT_BASE_URL}/{run_id}/output.html"})


@blast_extra_router.get("/blastp")
def search_blastp(
    gene_id: str = Query(..., alias="gene"),
    limit: int = Query(5000, ge=1, le=50000),
    offset: int = Query(0, ge=0),
) -> dict:
    """Search Blastp or find Homologs in Triticeae

    功能:
        可以用来搜索 query 基因在小麦族里的目标基因，
        可以用来做同源基因搜索或不同基因组版本/不同材料之间的基因 ID 转换。
        根据基因 ID 在 all_protein_blastp 表中搜索，同时匹配 query_id 和 subject_id。
        自动处理多种基因 ID 格式（带 .1、transcript: 前缀、.cds 后缀等）。
        结果按 bit_score 降序、evalue 升序排列。

    用法:
        GET /api/sequence/blastp?gene=<基因ID>&limit=5000&offset=0
        - gene: 必填，基因 ID
        - limit: 可选，最多返回条数，默认 5000
        - offset: 可选，偏移量，默认 0

    案例:
        请求:
          curl -X GET "http://localhost:8000/api/sequence/blastp?gene=TraesCS5A02G391700"

        响应:
          {
            "success": true,
            "data": {
              "gene": "TraesCS5A02G391700",
              "total": 42,
              "limit": 5000,
              "offset": 0,
              "results": [
                {
                  "query_id": "TraesCS5A02G391700.1",
                  "subject_id": "TraesCS5B02G391700.1",
                  "identity_val": 85.32,
                  "align_length": 245,
                  "mismatch": 12,
                  "gap_open": 0,
                  "q_start": 1,
                  "q_end": 245,
                  "s_start": 1,
                  "s_end": 245,
                  "evalue": 0.0,
                  "bit_score": 456.7,
                  "query_length": 300,
                  "subject_length": 290
                }
              ]
            }
          }
    """

    if not gene_id or len(gene_id) > 150:
        raise ValidationFailure("Invalid gene ID")
    if not re.match(r'^[A-Za-z0-9_.:\-]+$', gene_id):
        raise ValidationFailure("Gene ID contains invalid characters")

    # 生成搜索变体（同 PHP search_variants）
    def _search_variants(gene: str) -> list[str]:
        # 去掉 transcript: 前缀和 .cds 后缀
        base = re.sub(r'^transcript:', '', gene, flags=re.IGNORECASE)
        base = re.sub(r'\.cds$', '', base, flags=re.IGNORECASE)

        bases = {gene, base}
        if base and not re.search(r'\.\d+$', base):
            bases.add(base + '.1')

        vars_set: set[str] = set()
        for b in bases:
            if not b:
                continue
            clean = re.sub(r'^transcript:', '', b, flags=re.IGNORECASE)
            clean = re.sub(r'\.cds$', '', clean, flags=re.IGNORECASE)
            vars_set.add(b)
            vars_set.add(clean)
            vars_set.add('transcript:' + clean)
            vars_set.add(clean + '.cds')
            vars_set.add('transcript:' + clean + '.cds')

        return sorted(vars_set - {''})

    variants = _search_variants(gene_id)
    placeholders = ','.join(['%s'] * len(variants))

    # 两次查询：先查 count，再查结果
    with mysql_cursor(settings.DB_BLASTP) as cursor:
        # COUNT
        count_sql = (
            f"SELECT COUNT(*) FROM `all_protein_blastp` "
            f"WHERE `query_id` IN ({placeholders}) OR `subject_id` IN ({placeholders})"
        )
        cursor.execute(count_sql, variants + variants)
        total = cursor.fetchone()['COUNT(*)']

        # 结果查询
        select_sql = (
            f"SELECT `query_id`, `subject_id`, `identity_val`, `align_length`, "
            f"`mismatch`, `gap_open`, `q_start`, `q_end`, `s_start`, `s_end`, "
            f"`evalue`, `bit_score`, `query_length`, `subject_length` "
            f"FROM `all_protein_blastp` "
            f"WHERE `query_id` IN ({placeholders}) OR `subject_id` IN ({placeholders}) "
            f"ORDER BY `bit_score` DESC, `evalue` ASC "
            f"LIMIT %s OFFSET %s"
        )
        cursor.execute(select_sql, variants + variants + [limit, offset])
        rows = cursor.fetchall()

    results = []
    for row in rows:
        results.append({
            "query_id": row["query_id"],
            "subject_id": row["subject_id"],
            "identity_val": row["identity_val"],
            "align_length": row["align_length"],
            "mismatch": row["mismatch"],
            "gap_open": row["gap_open"],
            "q_start": row["q_start"],
            "q_end": row["q_end"],
            "s_start": row["s_start"],
            "s_end": row["s_end"],
            "evalue": row["evalue"],
            "bit_score": row["bit_score"],
            "query_length": row["query_length"],
            "subject_length": row["subject_length"],
        })

    return ok({
        "gene": gene_id,
        "total": total,
        "limit": limit,
        "offset": offset,
        "results": results,
    })
