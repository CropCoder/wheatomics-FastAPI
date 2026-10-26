#!/usr/bin/env python3
"""
WheatOmics BLAST API 端点
========================================
部署到: /var/www/FastAPI_backend_Port8000/routers/api_blast.py

路径和 get_fasta_bedtools.py CGI 脚本一致:
  - blast 程序路径: /usr/bin/blastp, /usr/bin/blastn (和 /usr/bin/blastdbcmd 同目录)
  - 数据库路径:    /var/www/html/getfasta/blastdb/ (和 get sequence 一致)
  - 数据库名:      和前端 <select> 的 value 一致（Fielder_protein, AK58_protein.fasta 等）

用法:
  POST /api/blast/search
    program=blastp
    database=Fielder_protein
    query=>seq\\nMSSSTG...
"""

import asyncio
import os
import re
import subprocess
import time as _time
import uuid
from typing import Optional, List

from fastapi import APIRouter, Form, HTTPException, Query

from app.core.config import settings
from app.db.mysql import mysql_cursor
from app.services.blast_runner import (
    BLASTDBCMD, BLAST_FORMATTER, BLASTN, BLASTP, BLASTX,
    BLAST_PROG_MAP, DB_DIR, TBLASTN, TBLASTX,
    count_active_jobs, read_status, write_params, write_status,
)

router = APIRouter(prefix="/blast", tags=["BLAST"])

# Binary paths, DB dir and the job state files moved to
# app/services/blast_runner.py — shared with the standalone job daemon.

MAX_QUERY_LENGTH = 100_000  # 查询序列最大字符数

#: uuid4 job id — accepted shape for /status/{job_id} (also guards the path
#: join against traversal).
_JOB_ID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

#: BLAST database names — path traversal guard for the `database` form field.
#: Without this, "database=/etc/passwd" makes os.path.join(DB_DIR, name) land
#: outside DB_DIR (an existence oracle + reads of arbitrary BLAST indexes).
_DB_NAME_RE = re.compile(r"^[\w.\-]+$")

#: wait=true poll loop: how often to check the job status file.
_SYNC_POLL_INTERVAL_SECONDS = 0.5
#: Total time a wait=true request may wait for its job. Must stay below
#: gunicorn's worker timeout=1200 (gunicorn.conf.py); jobs queued behind
#: others legitimately take a while, so this is generous.
_SYNC_POLL_TIMEOUT_SECONDS = 1100

#: Aggregated "sequence retrieval" databases. They concatenate whole genome
#: sets (all_genomes / all_other_genomes / all_Allohexaploid), so a BLAST search
#: against them is prohibitively expensive. They are used by the sequence
#: retrieval endpoints (e.g. /api/sequence/chromosomes?database=all_genomes)
#: and must not be offered in the BLAST database picker.
SEQUENCE_ONLY_DBS = frozenset({
    "all_Allohexaploid",
    "all_genomes",
    "all_other_genomes",
})

#: Legacy BLAST alias databases whose DBLIST entries predate the 2026-10 database
#: renaming (ploidy prefix + .add_Description suffix). Every member is dangling,
#: so blastdbcmd fails on them; they are kept on disk for reference only and
#: must not be offered in the picker.
LEGACY_ALIAS_DBS = frozenset({
    "all_Diploid",
    "all_OtherTriticeae",
    "all_tri6",
    "all_Allohexaploid",
    "all_Allotetraploid",
    "all1_genomes", "all2_genomes", "all3_genomes", "all4_genomes",
    "all5_genomes", "all6_genomes", "all7_genomes",
})

#: On-disk databases that are broken (blastdbcmd cannot open them) and must not
#: be offered until they are re-indexed/removed. `Foma.pep` (mdb_env_open
#: failure) was deleted on 2026-10-26; the name stays here as a guard in case an
#: old backup is restored.
BROKEN_DB_BASES = frozenset({"Foma.pep"})

#: Superseded duplicate BLAST builds. `CS21_S1_S2_S3_All_NLR` is the 2024-08
#: multi-volume build; `CS21_S1_S2_S3_All_NLR.fasta` is the 2026-09 rebuild of
#: the very same 105 sequences (identical entry-list md5), so only the newer
#: build is offered.
DUPLICATE_ALIAS_DBS = frozenset({"CS21_S1_S2_S3_All_NLR"})

#: Legacy singular aggregate aliases. `all_gene` / `all_protein` are duplicates
#: of the maintained `all_genes` / `all_proteins` (identical counts, total
#: length and DBLIST members, rebuilt 2026-10-24), so only the plural aliases
#: are offered in the picker.
LEGACY_AGGREGATE_ALIASES = frozenset({"all_gene", "all_protein"})

#: Databases that must never be advertised as BLAST targets.
HIDDEN_BLAST_DBS = (
    SEQUENCE_ONLY_DBS | LEGACY_ALIAS_DBS | BROKEN_DB_BASES
    | DUPLICATE_ALIAS_DBS | LEGACY_AGGREGATE_ALIASES
)

# === BLAST 数据库元数据（类型 / 组装） ===
#: Per-chromosome split databases: `<assembly>.genome_Chr1A`, `<assembly>.genome_chr1H`, ...
_DB_CHROM_RE = re.compile(r"\.genome_[Cc]hr([0-9]{1,2}[A-Za-z]{0,4})$")
#: Legacy per-chromosome aliases without the `.genome_` infix: `all_Allohexaploidchr1A`.
_DB_CHROM_ALT_RE = re.compile(r"[Cc]hr([0-9]{1,2}[A-Za-z]{0,4})$")

#: Annotation-level suffixes and their database kind.
_DB_ANNOTATION_SUFFIXES = (
    (".add_Description.cds", "cds"),
    (".add_Description.pep", "protein"),
)

#: assembly_level values that mean "chromosome-level assembly".
CHROMOSOME_LEVELS = frozenset({
    "Chromosome", "Complete Genome", "Complete genome",
    "Partial chromosome", "draft chromosome level",
})

#: Display normalisation: every chromosome-level flavour is reported as
#: "Chromosome" (the picker does not show the Chromosome badge anyway).
CHROMOSOME_LEVEL_ALIASES = {
    "Complete Genome": "Chromosome",
    "Complete genome": "Chromosome",
    "Partial chromosome": "Chromosome",
    "draft chromosome level": "Chromosome",
}


def _db_base_kind_chromosome(name: str) -> tuple[str, str, str | None]:
    """Split a BLAST database name into (assembly base, kind, chromosome)."""
    m = _DB_CHROM_RE.search(name)
    if m:
        return name[: m.start()], "chromosome", m.group(1)
    m = _DB_CHROM_ALT_RE.search(name)
    if m:
        return name[: m.start()], "chromosome", m.group(1)
    if name.startswith("all_"):
        return name, "aggregate", None
    for suffix, kind in _DB_ANNOTATION_SUFFIXES:
        if name.endswith(suffix):
            return name[: -len(suffix)], kind, None
    if name.endswith(".genome"):
        return name[:-len(".genome")], "genome", None
    if ".scaffold" in name:
        base = re.sub(r"\.scaffold.*$", "", name)
        return base or name, "genome", None
    return name, "other", None


#: Content-derived assembly-level overrides for DBs whose genome_registry row is
#: missing or wrong (Scaffold/Contig/Draft rows that are actually 21/14/7
#: chromosome assemblies etc.). Regenerated by scripts/make_level_overrides.py.
_DB_LEVELS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "services", "data", "blast_db_levels.json",
)
_DB_LEVELS_CACHE: dict[str, object] = {"mtime": None, "map": {}}


def _db_level_overrides() -> dict[str, dict]:
    try:
        mtime = os.path.getmtime(_DB_LEVELS_FILE)
    except OSError:
        return {}
    if _DB_LEVELS_CACHE.get("mtime") != mtime:
        try:
            import json
            with open(_DB_LEVELS_FILE, encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                _DB_LEVELS_CACHE["map"] = data
                _DB_LEVELS_CACHE["mtime"] = mtime
        except (OSError, ValueError):
            return _DB_LEVELS_CACHE.get("map") or {}
    return _DB_LEVELS_CACHE.get("map") or {}


def _assembly_level_map() -> dict[str, dict]:
    """Map blast_* base names to registry info (assembly level, dataset id).

    genome_registry stores base names without file suffix (``AABBDD_AK58``),
    which matches the base derived from BLAST db names. Best effort: when MySQL
    is unavailable the API still works, only quality badges/filtering go away.
    """
    try:
        with mysql_cursor(settings.DB_LITERATURE) as cursor:
            cursor.execute(
                "SELECT dataset_id, blast_genome_db, blast_cds_db, blast_pep_db, "
                "assembly_level, chromosome_count FROM genome_registry"
            )
            rows = cursor.fetchall()
    except Exception:
        return {}
    out: dict[str, dict] = {}
    for row in rows:
        level = (row.get("assembly_level") or "").strip() or None
        entry = {
            "assembly_level": level,
            "chromosome_level": level in CHROMOSOME_LEVELS,
            "chromosome_count": row.get("chromosome_count"),
            "dataset_id": row.get("dataset_id"),
        }
        for key in (row.get("blast_genome_db"), row.get("blast_cds_db"),
                    row.get("blast_pep_db"), row.get("dataset_id")):
            key = (key or "").strip()
            if key:
                out.setdefault(key, entry)
    for base, override in _db_level_overrides().items():
        base = (base or "").strip()
        level = (override or {}).get("assembly_level") or None
        if not base or not level:
            continue
        out[base] = {
            "assembly_level": level,
            "chromosome_level": level in CHROMOSOME_LEVELS,
            "chromosome_count": (override or {}).get("chromosome_count"),
            "dataset_id": (out.get(base) or {}).get("dataset_id"),
        }
    return out


def _db_meta(name: str, level_map: dict[str, dict]) -> dict:
    base, kind, chromosome = _db_base_kind_chromosome(name)
    info = level_map.get(base) or level_map.get(name) or {}
    if kind == "aggregate":
        info = {}
    level = info.get("assembly_level")
    level = CHROMOSOME_LEVEL_ALIASES.get(level, level)
    if not level and ".scaffold" in name.lower():
        level = "Scaffold"
    meta = {
        "kind": kind,
        "chromosome": chromosome,
        "assembly_level": level,
        "chromosome_level": bool(info.get("chromosome_level")) or level in CHROMOSOME_LEVELS,
    }
    if kind == "genome" and info.get("chromosome_count"):
        meta["chromosome_count"] = info["chromosome_count"]
    return meta


# === BLAST 数据库分类体系 ===
# 与 wheatomics.sdau.edu.cn 前端页面一致，按基因组倍性/物种分类
# 通过数据库名关键词匹配自动归类，未匹配的归入 "Other"
DB_CLASSIFICATION = [
    {
        "id": "aggregated",
        "label": "All-in-one databases",
        "description": "Aggregated databases spanning multiple genomes",
        "keywords": [
            "all_gene", "all_protein", "all_genomes", "all_",
        ],
    },
    {
        "id": "hexaploid_wheat",
        "label": "Hexaploid wheat genome",
        "description": "Common wheat (Triticum aestivum)",
        "keywords": [
            # Wheat_IWGSC_RefSeq, Chinese Spring (all versions)
            "iwgsc", "chinese_spring", "cs-iaas", "cs-cau",
            # Common wheat cultivars
            "fielder", "zang1817", "arinagrfor", "jagger", "julius",
            "longreach_lancer", "cdc_landmark", "mace", "norin61",
            "cdc_stanley", "sy_mattis", "renan", "kariega",
            "attraktion", "kn9204", "ak58", "chuanmai",
            "cwi86942", "triticum_spelta",
            # Chinese cultivars (two-letter/short codes)
            "jm22", "jm47", "ym158", "xy6", "xn6028", "s4185",
            "nc4", "mzm", "kf11", "hd6172", "cm42", "bj8",
            "amn", "abo", "zm16", "zm22", "zm366",
            "multiovary", "z8425b", "ym33",
            "jin50", "jm44", "sumai3", "nc99bgtag11",
            "triticum_aestivum_alchemy",
        ],
    },
    {
        "id": "tetraploid_wheat",
        "label": "Tetraploid wheat genome",
        "description": "Durum wheat, wild emmer, domesticated emmer (Triticum turgidum, Triticum dicoccoides)",
        "keywords": [
            "wild_emmer", "durum", "langdon",
            "triticum_timopheevii", "triticum_turgidum",
            "kronos", "chili", "mahmoudi", "pi192051", "pi94760",
        ],
    },
    {
        "id": "diploid_wheat",
        "label": "Diploid wheat genome and wild relatives",
        "description": "Aegilops tauschii, Triticum urartu, Triticum monococcum",
        "keywords": [
            "urartu", "monococcum", "ta299", "ta10622",
            "tauschii",  # catches all Aegilops tauschii accessions
            "other_wheat_progenitor",
        ],
    },
    {
        "id": "triticale",
        "label": "Triticale (AABBRR)",
        "description": "Hexaploid triticale (AABBRR): PT and ZX830",
        "keywords": [
            "aabbrr", "triticale",
        ],
    },
    {
        "id": "thinopyrum_ponticum",
        "label": "Thinopyrum ponticum",
        "description": "Decaploid Thinopyrum ponticum genome (2026, 41.33 Gb / 70 chromosomes)",
        "keywords": [
            "ponticum",  # Thinopyrum_ponticum_decaploid.* 以及旧 Thinopyrum_ponticum
        ],
    },
    {
        "id": "other_triticeae",
        "label": "Other Triticeae genome",
        "description": "Rye (Secale cereale), Thinopyrum, Elymus, non-tauschii Aegilops species, Dasypyrum, Leymus, Roegneria",
        "keywords": [
            "rye_", "thinopyrum_", "elymus_",
            "ae.",  # matches ae.speltoides, ae.longissima, etc. (NOT Ae_tauschii which uses underscore)
            "aegilops_mutica", "aegilops_umbellulata", "aegilops_comosa",
            "aegilops_geniculata", "aegilops_ventricosa",
            "aecomosa", "dasypyrum_", "roegneria_", "leymus_",
            "rm271",
        ],
    },
    {
        "id": "barley",
        "label": "Barley genome",
        "description": "Barley (Hordeum vulgare) - Morex, Golden Promise, Qingke, and wild accessions",
        "keywords": [
            "barley.", "barley_", "hordeum_", "morex", "qingke",
            "golden_promise", "golden_melon", "barke_v2",
            # Barley accession patterns (FT, HID, HOR, WBDC, ZDM series)
            "ft11", "ft67", "ft144", "ft628", "ft262", "ft286", "ft333", "ft880",
            "hid055", "hid101", "hid249", "hid357", "hid380",
            "hor_", "wbdc", "zdm",
            # Named barley cultivars
            "10tj18", "aizu_6", "akashinriki", "bonus", "bowman",
            "chikurin", "foma", "hockett", "igri", "maximus",
            "oun333", "rgt_planet",
        ],
    },
]


def _classify_db(db_name: str) -> str:
    """根据数据库名判断所属分类 ID"""
    name_lower = db_name.lower()
    for cat in DB_CLASSIFICATION:
        if any(kw in name_lower for kw in cat["keywords"]):
            return cat["id"]
    return "other"

# Disk-cached DB directory listing. Without this, list_dbs("blastn") takes
# 90+ seconds on /var/www/html/getfasta/blastdb/ (thousands of multi-volume
# index files across hundreds of genome databases), which starves the
# threadpool and makes every other FastAPI request time out.
#
# Cache TTL: 1 hour. BLAST DB layout changes only when an admin runs
# makeblastdb, so 1h is safe and avoids re-scanning the directory per request.
_DB_LIST_CACHE: dict[str, tuple[float, list[str]]] = {}
_DB_LIST_TTL_SECONDS = 3600.0

# blast 输出格式（outfmt 6 的列）
def _program_db_type(program: str) -> str:
    """返回程序对应的数据库类型: prot（蛋白）或 nuc（核酸）"""
    return "prot" if program in ("blastp", "blastx", "tblastx") else "nuc"


def _strip_volume(name: str) -> str:
    """去掉 BLAST 多卷库的 .00 .01 等后缀，返回基础库名"""
    return re.sub(r"\.\d{2,}$", "", name)


def list_dbs(program: str) -> List[str]:
    """列出可用的 BLAST 数据库（disk-cached，TTL 1h）

    /var/www/html/getfasta/blastdb/ has thousands of multi-volume index
    files across hundreds of genomes; scanning it per request takes 90+
    seconds and starves the worker threadpool. Cache for 1 hour.
    """
    cached = _DB_LIST_CACHE.get(program)
    if cached is not None:
        ts, names = cached
        if (_time.time() - ts) < _DB_LIST_TTL_SECONDS:
            return names

    if not os.path.isdir(DB_DIR):
        return []
    # 蛋白库索引: .pin .phr/.phd .psq/.psd | 核酸库索引: .nin .nhr .nsq
    # 完整 BLAST 索引扩展名:
    #   .pin/.phr/.phd/.psq/.psd = 蛋白核心索引 | .pal = 蛋白别名
    #   .nin/.nsq/.nhr/.ndb/.not/.ntf/.nto = 核酸核心索引 | .nal = 核酸别名
    # An alias file (.nal / .pal) can stand on its own and point at
    # other aliases / volume files anywhere on disk, so we accept any
    # single file that has a BLAST-DB-like extension.
    prot_exts = (".pin", ".phr", ".phd", ".psq", ".psd", ".pal")
    nuc_exts  = (".nin", ".nsq", ".nhr", ".ndb", ".not", ".ntf", ".nto", ".nal")
    exts = prot_exts if _program_db_type(program) == "prot" else nuc_exts
    dbs = {}
    for f in os.listdir(DB_DIR):
        for ext in exts:
            if f.endswith(ext):
                name = f[:-(len(ext))]
                name = _strip_volume(name)
                dbs[name] = dbs.get(name, 0) + 1
    # A real BLAST DB is valid with as few as ONE index file (e.g. a
    # single .nal alias file pointing at a multi-volume .00/.01 split,
    # or a fresh makeblastdb that's only produced .nsq + .nto so far).
    names = sorted(dbs.keys())
    _DB_LIST_CACHE[program] = (_time.time(), names)
    return names


def check_db_exists(db_name: str, program: str) -> bool:
    """检查数据库是否有 BLAST 索引"""
    exts = (".pin", ".phr", ".phd", ".psq", ".psd", ".pal") \
        if _program_db_type(program) == "prot" \
        else (".nin", ".nsq", ".nhr", ".ndb", ".not", ".ntf", ".nto", ".nal")
    full = os.path.join(DB_DIR, db_name)
    return any(os.path.exists(full + ext) for ext in exts)



def _validate_and_normalize_query(program: str, query: str) -> str:
    """Common validation shared by both wait modes."""
    VALID_PROGRAMS = {"blastp", "blastn", "blastx", "tblastn", "tblastx"}
    if program not in VALID_PROGRAMS:
        raise HTTPException(400, f"不支持的 BLAST 程序: {program}，可选: {sorted(VALID_PROGRAMS)}")
    query = query.strip()
    if not query:
        raise HTTPException(400, "查询序列不能为空")
    if len(query) > MAX_QUERY_LENGTH:
        raise HTTPException(400,
            f"查询序列过长（{len(query)} 字符），最大允许 {MAX_QUERY_LENGTH} 字符")
    if not query.startswith(">"):
        query = ">query\n" + query
    return query


async def _wait_for_job(job_id: str, program: str, dbs: list[str],
                        query: str, evalue: float, max_targets: int) -> dict:
    """Poll a job to a terminal state and build the synchronous response.

    The blast daemon executes the job; this just waits (async sleep, no
    thread held). On error/stale the message recorded by the executor is
    re-raised with its recorded status code (timeout=504, failure=500).
    """
    deadline = _time.time() + _SYNC_POLL_TIMEOUT_SECONDS
    while True:
        data = read_status(job_id)  # stale rewrite detects a dead daemon
        if data is not None:
            status = data.get("status")
            if status == "done":
                download_urls = data.get("download_urls") or {}
                return {
                    "success": True,
                    "program": program,
                    "database": dbs,
                    "parameters": {"evalue": evalue, "max_target_seqs": max_targets},
                    "query_header": query.strip().split("\n")[0],
                    "outfmt": list(download_urls.keys()),
                    "download_url": download_urls,
                }
            if status in ("error", "stale"):
                raise HTTPException(data.get("status_code") or 500,
                                    data.get("message") or "BLAST 执行失败")
        if _time.time() >= deadline:
            raise HTTPException(
                504,
                f"BLAST 超时（>{_SYNC_POLL_TIMEOUT_SECONDS // 60}分钟未完成）—— "
                f"job 可能仍在排队，可稍后查询 GET /api/blast/status/{job_id}",
            )
        await asyncio.sleep(_SYNC_POLL_INTERVAL_SECONDS)


@router.post("/search")
async def blast_search(
    program: str = Form(default="blastp",
        description="blastp（蛋白→蛋白库）/ blastn（核酸→核酸库）/ blastx（核酸翻译→蛋白库）/ tblastn（蛋白→核酸库翻译）/ tblastx（核酸翻译→蛋白库翻译）"),
    database: str = Form(default=...,
        description="数据库名，多个用逗号分隔，如 Fielder_protein,AK58_protein.fasta"),
    query: str = Form(default=...,
        description="FASTA 格式的查询序列"),
    evalue: float = Form(default=10.0, ge=0, le=1000,
        description="E-value 阈值 (0-1000)"),
    max_targets: int = Form(default=1000, ge=1, le=50000, alias="max_target_seqs",
        description="最多返回的匹配数 (1-50000)"),
    word_size: Optional[int] = Form(default=None),
    matrix: Optional[str] = Form(default=None),
    outfmt: str = Form(default="tabular",
        description="结果格式: tabular (默认, outfmt 6, 含 ppos/btop 列) / traditional (outfmt 0 逐位比对) / both (两种都生成)"),
    wait: bool = Form(default=True,
        description="true=等待结果完成（默认，兼容现有调用方）；false=立即返回 job_id，轮询 /api/blast/status/{job_id}"),
):
    """执行 BLAST 搜索，结果保存为文件返回下载链接。

    所有 job 都由独立的 blast daemon（wheatomics-blastd.service）执行，
    不受 API worker 回收/重启影响。wait=true（默认）: 提交后轮询到完成，
    返回 download_url（现有 agent/脚本零改动）；wait=false: 立即返回
    job_id，GET /api/blast/status/{job_id} 轮询。

    调用示例:
      curl -X POST "https://wheatomics.sdau.edu.cn/api/blast/search" \\n        -d "program=blastp" \\n        -d "database=Fielder_protein" \\n        --data-urlencode "query=>test\\nMSSSTG..."
    """
    query = _validate_and_normalize_query(program, query)
    if outfmt not in ("tabular", "traditional", "both"):
        raise HTTPException(400,
                            f"不支持的 outfmt: {outfmt}，可选: tabular / traditional / both")

    blast_path = BLAST_PROG_MAP.get(program, BLASTP)
    if not os.path.exists(blast_path):
        raise HTTPException(500, f"BLAST 程序不存在: {blast_path}")

    # ---- 检查数据库 ----
    dbs = [d.strip() for d in database.split(",") if d.strip()]
    if not dbs:
        raise HTTPException(400, "请指定至少一个数据库")
    if len(dbs) > 20:
        raise HTTPException(400, f"一次最多搜索 20 个数据库（收到 {len(dbs)} 个）")
    for d in dbs:
        if not _DB_NAME_RE.fullmatch(d):
            raise HTTPException(
                400,
                f"非法数据库名: {d!r}（仅允许字母/数字/下划线/点/连字符）",
            )

    missing = [d for d in dbs if not check_db_exists(d, program)]
    if missing:
        raise HTTPException(404,
            f"以下数据库在 {DB_DIR} 中找不到索引: {missing}")

    if count_active_jobs() >= settings.BLAST_MAX_QUEUED:
        raise HTTPException(
            429,
            f"BLAST 任务队列已满（排队/运行中 ≥ {settings.BLAST_MAX_QUEUED}），请稍后再试。",
        )

    result_dir = settings.BLAST_RESULT_DIR
    result_dir.mkdir(parents=True, exist_ok=True)
    job_id = str(uuid.uuid4())
    params = {
        "dbs": dbs, "program": program, "query": query,
        "evalue": evalue, "max_targets": max_targets,
        "word_size": word_size, "matrix": matrix,
        "outfmt": outfmt,
    }

    # Single channel: enqueue for the blast daemon in both modes.
    write_params(job_id, **params)
    write_status(job_id, status="pending", created_at=_time.time(),
                 message="Queued for BLAST.")

    if wait:
        # Synchronous contract (default) — poll the daemon to completion,
        # preserving the exact response shape callers already rely on.
        return await _wait_for_job(job_id, program, dbs, query, evalue, max_targets)

    # Async mode — return immediately; the frontend polls /status/{job_id}.
    return {
        "success": True,
        "job_id": job_id,
        "status": "pending",
        "status_url": f"/api/blast/status/{job_id}",
        "message": "BLAST job submitted; poll the status_url for completion.",
    }


@router.get("/status/{job_id}")
async def blast_job_status(job_id: str):
    """轮询 BLAST job 状态（wait=false 提交的 job）。

    返回 {"success", "job_id", "status": pending|running|done|error|stale,
    "message", "download_urls"}。done 时 download_urls 填充；error/stale 看
    message。job_id 必须为 uuid4 格式，否则 404。
    """
    if not _JOB_ID_RE.match(job_id):
        raise HTTPException(404, "Invalid job id")
    data = read_status(job_id)
    if data is None:
        raise HTTPException(404, "Job not found")
    return {
        "success": True,
        "job_id": job_id,
        "status": data.get("status"),
        "message": data.get("message", ""),
        "download_urls": data.get("download_urls"),
    }


@router.get("/databases")
async def list_databases(
    program: Optional[str] = Query(None, description="blastp/blastn/blastx/tblastn/tblastx/留空=全部")
):
    """列出可用 BLAST 数据库（按蛋白/核酸分组）。

    仅用于取序列的超大聚合库（SEQUENCE_ONLY_DBS：all_genomes /
    all_other_genomes / all_Allohexaploid）不在此列表中；它们仍可通过
    /api/sequence/* 使用。
    """
    db_type = _program_db_type(program) if program else None
    prot_dbs = list_dbs("blastp") if db_type in (None, "prot") else []
    nuc_dbs = list_dbs("blastn") if db_type in (None, "nuc") else []
    # Sequence-retrieval-only aggregate DBs are not valid BLAST targets.
    prot_dbs = [d for d in prot_dbs if d not in HIDDEN_BLAST_DBS]
    nuc_dbs = [d for d in nuc_dbs if d not in HIDDEN_BLAST_DBS]
    # ---- 按分类组织（供 AI agent 选择数据库时参考） ----
    all_dbs = prot_dbs + nuc_dbs
    level_map = _assembly_level_map()
    database_meta = {db: _db_meta(db, level_map) for db in all_dbs}
    kind_counts: dict[str, int] = {}
    for meta in database_meta.values():
        kind_counts[meta["kind"]] = kind_counts.get(meta["kind"], 0) + 1
    cat_map: dict[str, dict] = {}
    for cat in DB_CLASSIFICATION:
        cat_dbs = [d for d in all_dbs if _classify_db(d) == cat["id"]]
        cat_kinds: dict[str, int] = {}
        for db in cat_dbs:
            kind = database_meta[db]["kind"]
            cat_kinds[kind] = cat_kinds.get(kind, 0) + 1
        cat_map[cat["id"]] = {
            "label": cat["label"], "description": cat["description"],
            "count": len(cat_dbs), "databases": cat_dbs, "kind_counts": cat_kinds,
        }
    
    # 未匹配的归入 Other
    other_dbs = [d for d in all_dbs if _classify_db(d) == "other"]
    categories = [cat_map[c["id"]] for c in DB_CLASSIFICATION if cat_map[c["id"]]["count"] > 0]
    if other_dbs:
        categories.append({"id": "other", "label": "Other / Unclassified", "description": "Databases that could not be automatically classified", "count": len(other_dbs), "databases": other_dbs})

    return {
        "success": True,
        "db_dir": DB_DIR,
        "program": program or "all",
        "protein": {"count": len(prot_dbs), "databases": prot_dbs},
        "nucleotide": {"count": len(nuc_dbs), "databases": nuc_dbs},
        "total": len(prot_dbs) + len(nuc_dbs),
        "kind_counts": kind_counts,
        "database_meta": database_meta,
        "categories": categories,
    }


@router.get("/database-example")
async def database_example(db: str = Query(...)):
    """返回 blast 数据库的第一个序列名（从 .fai 索引），供前端作为示例。"""
    if not _DB_NAME_RE.fullmatch(db):
        raise HTTPException(status_code=400, detail=f"Invalid database name: {db}")
    fai_path = os.path.join(DB_DIR, f"{db}.fai")
    if not os.path.isfile(fai_path):
        raise HTTPException(status_code=404, detail=f"No .fai index for database {db}")
    try:
        with open(fai_path, encoding="utf-8", errors="ignore") as f:
            line = f.readline()
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Cannot read .fai: {exc}")
    if not line.strip():
        raise HTTPException(status_code=404, detail=f"Empty .fai for {db}")
    parts = line.rstrip("\n").rstrip("\r").split("\t")
    seq_name = parts[0].strip()
    seq_len = 0
    if len(parts) > 1:
        try:
            seq_len = int(parts[1])
        except ValueError:
            seq_len = 0
    return {"success": True, "db": db, "example": seq_name, "length": seq_len}


@router.get("/status")
async def blast_status():
    """检查 BLAST 环境"""
    def check(path):
        exists = os.path.exists(path)
        ver = ""
        if exists:
            try:
                r = subprocess.run([path, "-version"], capture_output=True, text=True, timeout=5)
                ver = r.stdout.strip().split("\n")[0] if r.stdout else ""
            except Exception:
                ver = "?"
        return {"exists": exists, "path": path, "version": ver}

    # Run all 7 version probes concurrently in the thread pool — sequential
    # subprocess.run would block the event loop for up to 35s on a hung binary.
    paths = [BLASTP, BLASTN, BLASTX, TBLASTN, TBLASTX, BLASTDBCMD]
    results = await asyncio.gather(*(asyncio.to_thread(check, p) for p in paths))
    return {
        "success": True,
        **{("blastp" if p == BLASTP else
            "blastn" if p == BLASTN else
            "blastx" if p == BLASTX else
            "tblastn" if p == TBLASTN else
            "tblastx" if p == TBLASTX else
            "blastdbcmd"): r for p, r in zip(paths, results)},
        "db_dir": {"path": DB_DIR, "exists": os.path.isdir(DB_DIR)},
        "protein_dbs": list_dbs("blastp"),
        "nucleotide_dbs": list_dbs("blastn"),
    }
