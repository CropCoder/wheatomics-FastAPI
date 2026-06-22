"""Comparative genomics and ID conversion routes."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.core.config import settings
from app.core.exceptions import ValidationFailure
from app.core.response import ok
from app.core.security import ID_CONVERSION_TABLES, SYNTENY_TABLES, ensure_allowed_table, ensure_gene_like, ensure_interval_like
from app.db.mysql import mysql_cursor
from app.schemas.comparative import HomologHit, IDMapping, SyntenyRecord
from app.services.legacy_parsers import normalize_text, pick_first

router = APIRouter(tags=["Comparative"])


@router.get("/homologs/wheat-rice-arabidopsis")
def wheat_rice_arabidopsis_homologs(
    gene_id: str = Query(...),
    max_targets: int = Query(3, ge=1, le=100),
) -> dict:
    """查询小麦基因在水稻和拟南芥中的同源基因。

    功能:
        根据小麦基因 ID 查询 WheatRiceArabidopsis_tbl 表，
        返回该基因在水稻（Rice）和拟南芥（Arabidopsis）中的同源基因，
        包含比对的 Qcovs、Identity、E-value、Score 等详细信息。
        max_targets 控制每个物种返回的同源基因数量上限。

    用法:
        GET /api/homologs/wheat-rice-arabidopsis?gene_id=<基因ID>&max_targets=<数量>
        - gene_id: 必填，小麦基因 ID（Traes 开头）或其他物种基因 ID
        - max_targets: 可选，每个物种最多返回的同源基因数（默认 3，1-100）

    案例:
        请求:
          curl -X GET "http://localhost:8000/api/homologs/wheat-rice-arabidopsis?gene_id=TraesCS5A02G391700&max_targets=3"

        响应:
          {
            "success": true,
            "data": {
              "query_gene": "TraesCS5A02G391700",
              "count": 6,
              "hits": [
                {
                  "query_gene": "TraesCS5A02G391700",
                  "target_gene": "Os01g0100100",
                  "description": "MADS-box transcription factor",
                  "species": "Rice",
                  "qcovs": 95.0,
                  "identity": 85.2,
                  "evalue": 1e-120,
                  "score": 450.0
                }
              ]
            }
          }
    """

    gene_id = ensure_gene_like(gene_id)
    hits: list[HomologHit] = []
    table = "WheatRiceArabidopsis_tbl"

    with mysql_cursor(settings.DB_GENEFUNC) as cursor:
        if gene_id.startswith("Traes"):
            cursor.execute(f"SELECT * FROM `{table}` WHERE `Query` = %s", (gene_id,))
            rows = cursor.fetchall()
            rice_rows = [row for row in rows if str(row.get("Species", row.get("species", row.get("Target_species", "")))) == "Rice"]
            arab_rows = [row for row in rows if str(row.get("Species", row.get("species", row.get("Target_species", "")))) == "Arabidopsis"]
            selected_rows = sorted(rice_rows, key=lambda row: float(row.get("Score", row.get("RawScore", row.get("score", 0)))), reverse=True)[:max_targets]
            selected_rows += sorted(arab_rows, key=lambda row: float(row.get("Score", row.get("RawScore", row.get("score", 0)))), reverse=True)[:max_targets]
        else:
            cursor.execute(f"SELECT * FROM `{table}` WHERE Target1 = %s", (gene_id.upper(),))
            rows = cursor.fetchall()
            selected_rows = sorted(rows, key=lambda row: float(row.get("Score", row.get("RawScore", row.get("score", 0)))), reverse=True)[: max_targets * 3]

        for row in selected_rows:
            hits.append(
                HomologHit(
                    query_gene=str(row.get("Query", row.get("query", ""))),
                    target_gene=str(row.get("Target1", row.get("Target", row.get("target", "")))),
                    description=normalize_text(row.get("Description")),
                    species=str(row.get("Species", row.get("species", ""))),
                    gene_name=normalize_text(row.get("Name")) or None,
                    qcovs=float(row.get("Qcovs", row.get("qcovs", 0)) or 0),
                    length=int(row.get("Length", row.get("length", 0)) or 0),
                    identity=float(row.get("Identity", row.get("identity", 0)) or 0),
                    positive=float(row.get("Positive", row.get("positive", 0)) or 0),
                    evalue=float(row.get("Evalue", row.get("evalue", 0)) or 0),
                    score=float(row.get("Score", row.get("RawScore", row.get("score", 0))) or 0),
                )
            )

    return ok({"query_gene": gene_id, "count": len(hits), "hits": [hit.model_dump() for hit in hits]})


@router.get("/homologs/triticeae")
def triticeae_homologs(
    gene_id: str = Query(...),
    max_targets: int = Query(1, ge=1, le=100),
) -> dict:
    """查询小麦基因在麦族物种中的同源基因。

    功能:
        根据小麦基因 ID 查询 Triticeae_table，返回在麦族（Triticeae）
        各物种中的同源基因。覆盖物种包括: 普通小麦、硬粒小麦、
        野生二粒小麦、乌拉尔图小麦、节节麦、大麦。按 E-value 排序，
        每个物种返回有限数量（按 max_targets 比例）。

    用法:
        GET /api/homologs/triticeae?gene_id=<基因ID>&max_targets=<数量>
        - gene_id: 必填，小麦基因 ID
        - max_targets: 可选，基准返回数量（默认 1，1-100）

    案例:
        请求:
          curl -X GET "http://localhost:8000/api/homologs/triticeae?gene_id=TraesCS5A02G391700&max_targets=2"

        响应:
          {
            "success": true,
            "data": {
              "query_gene": "TraesCS5A02G391700",
              "count": 10,
              "hits": [
                {
                  "query_gene": "TraesCS5A02G391700",
                  "target_gene": "...",
                  "species": "Triticum aestivum",
                  "identity": 99.0,
                  "evalue": 0.0
                }
              ]
            }
          }
    """

    gene_id = ensure_gene_like(gene_id)
    species_limits = {
        "Triticum aestivum": max_targets * 3,
        "Durum wheat": max_targets * 2,
        "Wild emmer": max_targets * 2,
        "Triticum urartu": max_targets,
        "Aegilops tauschii": max_targets,
        "Hordeum vulgare": max_targets,
    }

    with mysql_cursor(settings.DB_GENEFUNC) as cursor:
        cursor.execute("SELECT * FROM Triticeae_table WHERE `Query` = %s", (gene_id,))
        rows = cursor.fetchall()

    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(str(row.get("Species", row.get("species", ""))), []).append(row)

    hits: list[HomologHit] = []
    for species, limit in species_limits.items():
        subset = sorted(grouped.get(species, []), key=lambda row: float(row.get("Evalue", row.get("evalue", 0)) or 0))[:limit]
        for row in subset:
            hits.append(
                HomologHit(
                    query_gene=str(row.get("Query", "")),
                    target_gene=str(row.get("Target", row.get("Target1", ""))),
                    species=species,
                    qcovs=float(row.get("Qcovs", 0) or 0),
                    length=int(row.get("Length", 0) or 0),
                    identity=float(row.get("Identity", 0) or 0),
                    positive=float(row.get("Positive", 0) or 0),
                    evalue=float(row.get("Evalue", 0) or 0),
                    score=float(row.get("Score", 0) or 0),
                )
            )

    return ok({"query_gene": gene_id, "count": len(hits), "hits": [hit.model_dump() for hit in hits]})


@router.get("/synteny/search")
def search_synteny(
    query: str = Query(..., alias="ID"),
    table: str = Query("CSsymaptbl"),
) -> dict:
    """搜索小麦与其他麦族物种的共线性（Synteny）信息。

    功能:
        支持两种查询模式:
        1. 基因组区间查询 - 格式 chr5A:100000-200000，返回该区段内基因的共线性记录
        2. 基因 ID 查询 - 精确查找单个基因的共线性关系
        结果为每个基因在 Chinese Spring、Durum wheat、Wild emmer、
        Triticum urartu、Aegilops tauschii 中的共线性对应关系。

    用法:
        GET /api/synteny/search?ID=<查询内容>&table=<表名>
        - ID: 必填，基因ID 或 染色体区间
        - table: 可选，共线性表名，默认 CSsymaptbl

    案例:
        请求:
          curl -X GET "http://localhost:8000/api/synteny/search?ID=TraesCS5A02G391700"

        响应:
          {
            "success": true,
            "data": {
              "count": 1,
              "records": [
                {
                  "chromosome": "chr5A",
                  "start_mb": 587.123456,
                  "end_mb": 587.125000,
                  "strand": "+",
                  "gene": "TraesCS5A02G391700",
                  "chinese_spring": "...",
                  "durum_wheat": "...",
                  "wild_emmer": "...",
                  "triticum_urartu": "...",
                  "aegilops_tauschii": "..."
                }
              ]
            }
          }
    """

    table = ensure_allowed_table(table, SYNTENY_TABLES, "synteny table")
    tokens = [item.strip() for item in query.split() if item.strip()]
    records: list[SyntenyRecord] = []

    with mysql_cursor(settings.DB_SYMAP) as cursor:
        for token in tokens:
            if ":" in token:
                ensure_interval_like(token)
                chrom = token.split(":")[0]
                interval = token.split(":")[1].replace("..", "-")
                start_text, end_text = interval.split("-")
                start, end = int(start_text), int(end_text)
                if end <= start or end - start > 30_000_000:
                    raise ValidationFailure("Region should be <= 30Mb and end > start")
                cursor.execute(
                    f"SELECT * FROM `{table}` WHERE Chrom=%s AND Start1 >= %s AND End1 <= %s",
                    (chrom, start, end),
                )
            else:
                ensure_gene_like(token)
                cursor.execute(f"SELECT * FROM `{table}` WHERE Gene = %s", (token,))

            for row in cursor.fetchall():
                records.append(
                    SyntenyRecord(
                        chromosome=str(row["Chrom"]),
                        start_mb=round(float(row["Start1"]) / 1_000_000.0, 6),
                        end_mb=round(float(row["End1"]) / 1_000_000.0, 6),
                        strand=str(row["Strand"]),
                        gene=str(row["Gene"]),
                        chinese_spring=normalize_text(pick_first(row, "Chinese_spring", "ChineseSpring", "Chinese spring")) or None,
                        durum_wheat=normalize_text(pick_first(row, "Durum_wheat", "Durum wheat")) or None,
                        wild_emmer=normalize_text(pick_first(row, "Wild_emmer", "Wild emmer")) or None,
                        triticum_urartu=normalize_text(pick_first(row, "Triticum_urartu", "Triticum urartu")) or None,
                        aegilops_tauschii=normalize_text(pick_first(row, "Aegilops_tauschii", "Aegilops tauschii")) or None,
                    )
                )

    return ok({"count": len(records), "records": [record.model_dump() for record in records]})


@router.get("/id-conversion")
def convert_gene_ids(
    gene_ids: str = Query(..., alias="ID"),
    version: str = Query(..., alias="gene_version"),
) -> dict:
    """在不同基因注释版本间转换基因 ID（统一转换为 IWGSC v1.1 / 02G）。

    ⚠️  版本说明:
        以下三个源版本的基因 ID 可转换为 IWGSC v1.1 (02G):
        - MIPS_result:  MIPS v2.2 格式，例如 "Traes_1AS_E6058767A.1"
        - TGACv1_result: TGACv1 格式，例如 "TRIAE_CS42_6BL_TGACv1_501926_AA1621570.1"
        - IWGSCv1_result: IWGSC v1.0 格式，例如 "TraesCS6B01G342500.1"
        请输入转录本 ID（带 ".1" 后缀），输出的 reference_gene 为 02G 格式（如 "TraesCS6B02G084800"）。

    功能:
        输入多个源基因 ID（%0D%0A 分隔），在指定版本表中查询并
        转换到 IWGSC v1.1 (02G)。返回每个基因的映射结果（reference_gene、
        code、length）。未找到的基因列在 not_found 中。

    用法:
        GET /api/id-conversion?ID=<基因1 基因2>&gene_version=<源版本表>
        - ID: 必填，基因 ID 列表，多基因用 %0D%0A（URL编码换行符）分隔（需带 ".1" 后缀的转录本 ID）
        - gene_version: 必填，源版本对应的数据库表名：
          "MIPS_result" / "TGACv1_result" / "IWGSCv1_result"

    案例:
        请求 (MIPS v2.2 → IWGSC v1.1):
          curl -X GET "http://localhost:8000/api/id-conversion?ID=Traes_1AS_E6058767A.1&gene_version=MIPS_result"

        请求 (IWGSC v1.0 → IWGSC v1.1):
          curl -X GET "http://localhost:8000/api/id-conversion?ID=TraesCS6B01G342500.1%0D%0ATraesCS6B01G123400.1&gene_version=IWGSCv1_result"

        响应:
          {
            "success": true,
            "data": {
              "version": "IWGSCv1_result",
              "mappings": [
                {
                  "query_gene": "TraesCS6B01G342500.1",
                  "reference_gene": "TraesCS6B02G342500",
                  "code": "-",
                  "length": "1500"
                }
              ],
              "not_found": []
            }
          }
    """

    version = ensure_allowed_table(version, ID_CONVERSION_TABLES, "id conversion table")
    # Decode URL-encoded separators (handles double-encoding from agent HTTP libs)
    for sep in ("%0D%0A", "%0A", "%2B"):
        gene_ids = gene_ids.replace(sep, " ")
    # + in query string is treated as space by web frameworks, but handle literally too
    gene_ids = gene_ids.replace("+", " ")
    genes = [ensure_gene_like(g.strip()) for g in gene_ids.split() if g.strip()]
    mappings: list[IDMapping] = []
    not_found: list[str] = []

    with mysql_cursor(settings.DB_CONVERT_GENE_ID) as cursor:
        for gene in genes:
            cursor.execute(f"SELECT * FROM `{version}` WHERE MIPS = %s", (gene,))
            row = cursor.fetchone()
            if not row:
                not_found.append(gene)
                continue
            # Discover actual column names from cursor.description (positional, matching CGI)
            col_map = {}
            if cursor.description:
                cnames = [d[0] for d in cursor.description]
                col_map = {
                    "query_gene":    cnames[0] if len(cnames) > 0 else "MIPS",
                    "reference_gene": cnames[1] if len(cnames) > 1 else "ReferenceGene",
                    "code":          cnames[2] if len(cnames) > 2 else "Code",
                    "length":        cnames[3] if len(cnames) > 3 else "Length",
                }
            mappings.append(
                IDMapping(
                    query_gene=str(row.get(col_map.get("query_gene", "MIPS"), gene)),
                    reference_gene=str(row.get(col_map.get("reference_gene", "ReferenceGene"), "")),
                    code=str(row.get(col_map.get("code", "Code"), "")),
                    length=str(row.get(col_map.get("length", "Length"), "")),
                )
            )

    return ok({"version": version, "mappings": [mapping.model_dump() for mapping in mappings], "not_found": not_found})
