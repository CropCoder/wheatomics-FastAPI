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
from app.services.blast_runner import (
    BLASTDBCMD, BLAST_FORMATTER, BLASTN, BLASTP, BLASTX,
    BLAST_PROG_MAP, DB_DIR, TBLASTN, TBLASTX,
    read_status, write_params, write_status,
)

router = APIRouter(prefix="/blast", tags=["BLAST"])

# Binary paths, DB dir and the job state files moved to
# app/services/blast_runner.py — shared with the standalone job daemon.

MAX_QUERY_LENGTH = 100_000  # 查询序列最大字符数

#: uuid4 job id — accepted shape for /status/{job_id} (also guards the path
#: join against traversal).
_JOB_ID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

#: wait=true poll loop: how often to check the job status file.
_SYNC_POLL_INTERVAL_SECONDS = 0.5
#: Total time a wait=true request may wait for its job. Must stay below
#: gunicorn's worker timeout=1200 (gunicorn.conf.py); jobs queued behind
#: others legitimately take a while, so this is generous.
_SYNC_POLL_TIMEOUT_SECONDS = 1100

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
    evalue: float = Form(default=10.0,
        description="E-value 阈值"),
    max_targets: int = Form(default=1000, alias="max_target_seqs",
        description="最多返回的匹配数"),
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

    missing = [d for d in dbs if not check_db_exists(d, program)]
    if missing:
        raise HTTPException(404,
            f"以下数据库在 {DB_DIR} 中找不到索引: {missing}")

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
    """列出可用数据库（按蛋白/核酸分组）"""
    db_type = _program_db_type(program) if program else None
    prot_dbs = list_dbs("blastp") if db_type in (None, "prot") else []
    nuc_dbs = list_dbs("blastn") if db_type in (None, "nuc") else []
    # ---- 按分类组织（供 AI agent 选择数据库时参考） ----
    all_dbs = prot_dbs + nuc_dbs
    cat_map: dict[str, dict] = {}
    for cat in DB_CLASSIFICATION:
        cat_dbs = [d for d in all_dbs if _classify_db(d) == cat["id"]]
        cat_map[cat["id"]] = {"label": cat["label"], "description": cat["description"], "count": len(cat_dbs), "databases": cat_dbs}
    
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
        "categories": categories,
    }


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
