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

import os
import subprocess
from datetime import datetime
from fastapi import APIRouter, Form, HTTPException, Query
from typing import Optional, List

from app.core.config import settings

router = APIRouter(prefix="/api/blast", tags=["BLAST"])

# === 和 CGI 脚本 get_fasta_bedtools.py 完全一致的路径 ===
# === 路径检测（和 blast2.pl 逻辑一致） ===
# blast2.pl:
#   if (-e "/usr/bin/blastall") { $blastPath = "/usr/bin"; }
#   else { $blastPath = "."; }
#   push @cmd, "$blastPath/blastp";

BLAST_BIN = "/var/www/html/blast/blast+/bin"  # BLAST+ 程序目录

MAX_QUERY_LENGTH = 100_000  # 查询序列最大字符数


def _find_blast_prog(name: str) -> str:
    """查找可用的 BLAST 程序"""
    exe = os.path.join(BLAST_BIN, name)
    if os.path.exists(exe):
        return exe
    # 兜底：可能在别的路径
    for p in ["/usr/bin", "/usr/local/bin"]:
        exe = os.path.join(p, name)
        if os.path.exists(exe):
            return exe
    return f"{BLAST_BIN}/{name}"  # 默认


BLASTP = _find_blast_prog("blastp")
BLASTN = _find_blast_prog("blastn")
BLASTDBCMD = _find_blast_prog("blastdbcmd")

# === BLAST 数据库分类体系 ===
# 与 wheatomics.sdau.edu.cn 前端页面一致，按基因组倍性/物种分类
# 通过数据库名关键词匹配自动归类，未匹配的归入 "Other"
DB_CLASSIFICATION = [
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
            "triticum_aestivum_alchemy", "other_common_wheat",
        ],
    },
    {
        "id": "tetraploid_wheat",
        "label": "Tetraploid wheat genome",
        "description": "Durum wheat, wild emmer, domesticated emmer (Triticum turgidum, Triticum dicoccoides)",
        "keywords": [
            "wild_emmer", "durum", "langdon",
            "triticum_timopheevii", "triticum_turgidum",
            "kronos", "chili.", "mahmoudi", "pi192051", "pi94760",
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

def _classify_db(db_name: str) -> str:
    """根据数据库名判断所属分类 ID"""
    name_lower = db_name.lower()
    for cat in DB_CLASSIFICATION:
        if any(kw in name_lower for kw in cat["keywords"]):
            return cat["id"]
    return "other"

DB_DIR = "/var/www/html/getfasta/blastdb/"  # 和 CGI 的 DbPath 一致

# blast 输出格式（outfmt 6 的列）
OUTFMT = "6 qseqid sseqid pident length mismatch gapopen qstart qend sstart send evalue bitscore"
FIELDS = ["query_id", "subject_id", "pident", "alignment_length",
          "mismatches", "gap_opens", "q_start", "q_end",
          "s_start", "s_end", "evalue", "bitscore"]


def list_dbs(program: str) -> List[str]:
    """列出可用的 BLAST 数据库"""
    if not os.path.isdir(DB_DIR):
        return []
    # 蛋白库索引: .pin .phr .psq | 核酸库索引: .nin .nhr .nsq
    # 完整 BLAST 索引扩展名:
    #   .pin/.phr/.psq = 蛋白核心索引 | .pal = 蛋白别名
    #   .nin/.nhr/.nsq = 核酸核心索引 | .nal = 核酸别名
    prot_exts = (".pin", ".phr", ".psq", ".pal")
    nuc_exts = (".nin", ".nhr", ".nsq", ".nal")
    exts = prot_exts if program == "blastp" else nuc_exts
    dbs = {}
    for f in os.listdir(DB_DIR):
        for ext in exts:
            if f.endswith(ext):
                name = f[:-(len(ext))]
                dbs[name] = dbs.get(name, 0) + 1
    return sorted(name for name, count in dbs.items() if count >= 2)


def check_db_exists(db_name: str, program: str) -> bool:
    """检查数据库是否有 BLAST 索引"""
    exts = (".pin", ".phr", ".psq", ".pal") if program == "blastp" else (".nin", ".nhr", ".nsq", ".nal")
    full = os.path.join(DB_DIR, db_name)
    return any(os.path.exists(full + ext) for ext in exts)


def _fetch_full_sequences(sids: set, db_names: list) -> dict:
    """通过 blastdbcmd 从 BLAST 数据库提取全长序列。

    Args:
        sids: 不重复的 subject ID 集合
        db_names: 查询用到的数据库名列表

    Returns:
        { subject_id: ">full_fasta_sequence" }
    """
    result = {}
    if not os.path.exists(BLASTDBCMD):
        return result
    for sid in sids:
        for db in db_names:
            db_path = os.path.join(DB_DIR, db)
            try:
                r = subprocess.run(
                    [BLASTDBCMD, "-db", db_path, "-entry", sid, "-outfmt", "%f"],
                    capture_output=True, text=True, timeout=30,
                )
                if r.returncode == 0 and r.stdout.strip():
                    result[sid] = r.stdout.strip()
                    break
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                continue
    return result


def _cleanup_old_results():
    """清理过期的 BLAST 结果文件"""
    expire_days = settings.BLAST_RESULT_EXPIRE_DAYS
    result_dir = settings.BLAST_RESULT_DIR
    if not result_dir.is_dir():
        return
    cutoff = datetime.now().timestamp() - expire_days * 86400
    for f in result_dir.iterdir():
        if f.is_file() and f.stat().st_mtime < cutoff:
            try:
                f.unlink()
            except OSError:
                pass


def _generate_result_html(
    job_id: str,
    program: str,
    database: str,
    query_header: str,
    hits: list,
    parameters: dict,
) -> str:
    """生成 BLAST 结果静态 HTML 页面，返回文件路径"""
    result_dir = settings.BLAST_RESULT_DIR
    result_dir.mkdir(parents=True, exist_ok=True)

    rows_html = ""
    if hits:
        for i, h in enumerate(hits, 1):
            subject = h["subject_id"]
            ncbi_url = f"https://www.ncbi.nlm.nih.gov/nuccore/{subject}" if subject.isdigit() else f"https://www.ncbi.nlm.nih.gov/search/all/{subject}"
            seq = h.get("subject_full_sequence", "")
            seq_preview = ""
            if seq:
                seq_preview = (
                    f'<div class="seq-box" id="seq-{i}" style="display:none">'
                    f'<pre style="font-size:11px;max-height:150px;overflow:auto;word-break:break-all">{seq}</pre>'
                    f'</div>'
                )
            rows_html += f"""<tr>
                <td>{i}</td>
                <td><a href="{ncbi_url}" target="_blank">{subject}</a></td>
                <td>{h["pident"]:.2f}</td>
                <td>{h["alignment_length"]}</td>
                <td>{h["mismatches"]}</td>
                <td>{h["gap_opens"]}</td>
                <td>{h["q_start"]}</td>
                <td>{h["q_end"]}</td>
                <td>{h["s_start"]}</td>
                <td>{h["s_end"]}</td>
                <td>{h["evalue"]:.2e}</td>
                <td>{h["bitscore"]:.1f}</td>
                <td>{seq_preview}<button class="btn btn-sm btn-outline-secondary" onclick="document.getElementById('seq-{i}').style.display=document.getElementById('seq-{i}').style.display=='none'?'block':'none'">{'Show Seq' if seq else '—'}</button></td>
            </tr>"""
    else:
        rows_html = "<tr><td colspan='13' style='text-align:center'>No hits found</td></tr>"

    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>BLAST results - {job_id}</title>
    <meta charset="utf-8">
    <link rel="shortcut icon" href="/favicon.ico" type="image/x-icon" />
    <link rel="stylesheet" href="/css/style.css" type="text/css" />
    <link rel="stylesheet" href="/css/bootstrap-4.5.3-dist/css/bootstrap.css" type="text/css" />
    <script src="/js/jquery/1.9.1/jquery.min.js" type="text/javascript"></script>
    <script src="/css/bootstrap-4.5.3-dist/js/bootstrap.js" type="text/javascript"></script>
    <script>
    $(function(){{ $("#header").load("/header.html"); }});
    $(function(){{ $("#footer").load("/footer.html"); }});
    </script>
    <style>
        .result-container {{ padding: 20px 5%; }}
        .param-summary {{ background: #f8f9fa; border-radius: 6px; padding: 15px; margin-bottom: 20px; }}
        .param-summary dt {{ font-weight: 600; color: #2c3e50; }}
        .result-table {{ font-size: 13px; }}
        .result-table th {{ background: #2c3e50; color: #fff; white-space: nowrap; }}
        .result-table td {{ vertical-align: middle; }}
        .result-table tr:hover {{ background: #f1f4f7; }}
        .seq-box {{ background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 4px; padding: 8px; margin-top: 4px; }}
        h4 {{ color: #2c3e50; border-bottom: 2px solid #e74c3c; padding-bottom: 8px; }}
    </style>
</head>
<body>
<div id="header"></div>
<div class="result-container">
    <h4>BLAST Results</h4>

    <div class="param-summary">
        <dl class="row">
            <dt class="col-sm-2">Job ID</dt>
            <dd class="col-sm-4">{job_id}</dd>
            <dt class="col-sm-2">Program</dt>
            <dd class="col-sm-4">{program}</dd>
            <dt class="col-sm-2">Database</dt>
            <dd class="col-sm-4">{database}</dd>
            <dt class="col-sm-2">Query</dt>
            <dd class="col-sm-10"><code style="word-break:break-all">{query_header}</code></dd>
            <dt class="col-sm-2">E-value cutoff</dt>
            <dd class="col-sm-4">{parameters.get("evalue", "-")}</dd>
            <dt class="col-sm-2">Max targets</dt>
            <dd class="col-sm-4">{parameters.get("max_target_seqs", "-")}</dd>
            <dt class="col-sm-2">Total hits</dt>
            <dd class="col-sm-4"><span class="badge badge-primary" style="font-size:14px">{len(hits)}</span></dd>
        </dl>
    </div>

    <table class="table table-bordered table-hover result-table">
        <thead>
            <tr>
                <th>#</th><th>Subject ID</th><th>Identity (%)</th><th>Length</th>
                <th>Mismatches</th><th>Gaps</th><th>Q Start</th><th>Q End</th>
                <th>S Start</th><th>S End</th><th>E-value</th><th>Bit Score</th>
                <th>Full Seq</th>
            </tr>
        </thead>
        <tbody>
            {rows_html}
        </tbody>
    </table>
</div>
<div id="footer"></div>
</body>
</html>"""

    filepath = os.path.join(str(result_dir), f"{job_id}.html")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)
    return filepath


# ======================== 端点 ========================

@router.post("/search")
async def blast_search(
    program: str = Form(default="blastp",
        description="blastp（蛋白）/ blastn（核酸）"),
    database: str = Form(default=...,
        description="数据库名，多个用逗号分隔，如 Fielder_protein,AK58_protein.fasta"),
    query: str = Form(default=...,
        description="FASTA 格式的查询序列"),
    evalue: float = Form(default=10.0,
        description="E-value 阈值"),
    max_targets: int = Form(default=20, alias="max_target_seqs",
        description="最多返回的匹配数"),
    word_size: Optional[int] = Form(default=None),
    matrix: Optional[str] = Form(default=None),
    outfmt: str = Form(default="json",
        description="json（结构化）或 tabular（表格）"),
    save_html: bool = Form(default=False,
        description="是否生成可访问的静态结果页面")
):
    """
    执行 BLAST 搜索。

    outfmt 说明:
      json      - JSON 结构化（默认）
      tabular   - 纯文本表格

    save_html 说明:
      设为 true 会在服务器生成一份 HTML 结果页面，
      通过返回的 html_url 字段的地址可直接访问。

    调用示例:
      curl -X POST "https://wheatomics.sdau.edu.cn/api/blast/search" \\
        -d "program=blastp" \\
        -d "database=Fielder_protein" \\
        -d "save_html=true" \\
        --data-urlencode "query=>seq\\nMSSSTG..."
    """
    # ---- 校验 ----
    if program not in ("blastp", "blastn"):
        raise HTTPException(400, f"不支持的 BLAST 程序: {program}")
    query = query.strip()
    if not query:
        raise HTTPException(400, "查询序列不能为空")
    if len(query) > MAX_QUERY_LENGTH:
        raise HTTPException(400,
            f"查询序列过长（{len(query)} 字符），最大允许 {MAX_QUERY_LENGTH} 字符")
    if not query.startswith(">"):
        query = ">query\n" + query

    blast_path = BLASTP if program == "blastp" else BLASTN
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

    # ---- 构建 blast 命令 ----
    program_name = os.path.basename(blast_path)
    cmd = []
    if program_name == "blastall":
        cmd += [blast_path, "-p", program]
    else:
        if program in ("blastp", "blastn"):
            cmd += [blast_path, "-task", program]
        else:
            cmd += [blast_path]

    cmd += [
        "-db", " ".join(os.path.join(DB_DIR, d) for d in dbs),
        "-outfmt", OUTFMT,
        "-evalue", str(evalue),
        "-max_target_seqs", str(max_targets),
        "-num_threads", "4",
    ]
    if word_size is not None:
        cmd += ["-word_size", str(word_size)]
    if matrix is not None:
        cmd += ["-matrix", matrix]

    # ---- 执行 ----
    try:
        result = subprocess.run(
            cmd, input=query, capture_output=True, text=True, timeout=600
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "BLAST 超时（>10分钟）")
    except FileNotFoundError:
        raise HTTPException(500, f"BLAST 可执行文件未找到: {blast_path}")

    if result.returncode != 0:
        raise HTTPException(500, f"BLAST 执行错误: {result.stderr.strip()}")

    # ---- 解析结果 ----
    hits = []
    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) >= len(FIELDS):
            h = dict(zip(FIELDS, parts))
            h["pident"] = float(h["pident"])
            h["alignment_length"] = int(h["alignment_length"])
            h["mismatches"] = int(h["mismatches"])
            h["gap_opens"] = int(h["gap_opens"])
            h["q_start"] = int(h["q_start"])
            h["q_end"] = int(h["q_end"])
            h["s_start"] = int(h["s_start"])
            h["s_end"] = int(h["s_end"])
            h["evalue"] = float(h["evalue"])
            h["bitscore"] = float(h["bitscore"])
            hits.append(h)

    # ---- 提取全长序列（按唯一 subject_id 去重） ----
    if hits:
        unique_sids = set(h["subject_id"] for h in hits)
        seq_map = _fetch_full_sequences(unique_sids, dbs)
        for h in hits:
            h["subject_full_sequence"] = seq_map.get(h["subject_id"], "")

    # ---- 生成静态 HTML（可选） ----
    html_url = None
    if save_html:
        job_id = datetime.now().strftime("blast_%Y%m%d_%H%M%S_%f")
        params = {"evalue": evalue, "max_target_seqs": max_targets}
        _generate_result_html(
            job_id=job_id,
            program=program,
            database=", ".join(dbs),
            query_header=query.strip().split("\n")[0],
            hits=hits,
            parameters=params,
        )
        html_url = f"{settings.BLAST_SITE_BASE_URL}{settings.BLAST_RESULT_BASE_URL}/{job_id}.html"
        _cleanup_old_results()

    # ---- 返回 ----
    if outfmt == "tabular":
        text = "\t".join(FIELDS) + "\n" + "\n".join(
            "\t".join(str(h[f]) for f in FIELDS) for h in hits
        )
        if html_url:
            text += f"\n\nHTML result page: {html_url}"
        return text

    resp = {
        "success": True,
        "program": program,
        "database": dbs,
        "parameters": {"evalue": evalue, "max_target_seqs": max_targets},
        "query_header": query.strip().split("\n")[0],
        "total_hits": len(hits),
        "hits": hits,
    }
    if html_url:
        resp["html_url"] = html_url
    return resp


@router.get("/databases")
async def list_databases(
    program: Optional[str] = Query(None, description="blastp/blastn/留空=全部")
):
    """列出可用数据库（按蛋白/核酸分组）"""
    prot_dbs = list_dbs("blastp") if program in (None, "blastp") else []
    nuc_dbs = list_dbs("blastn") if program in (None, "blastn") else []
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

    return {
        "success": True,
        "blastp": check(BLASTP),
        "blastn": check(BLASTN),
        "blastdbcmd": check(BLASTDBCMD),
        "db_dir": {"path": DB_DIR, "exists": os.path.isdir(DB_DIR)},
        "protein_dbs": list_dbs("blastp"),
        "nucleotide_dbs": list_dbs("blastn"),
    }
