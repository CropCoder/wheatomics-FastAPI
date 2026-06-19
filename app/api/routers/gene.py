"""Gene and cloned-gene routes."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.core.config import settings
from app.core.exceptions import ResourceNotFound, ValidationFailure
from app.core.response import ok
from app.core.security import GENE_FUNCTION_TABLES, ensure_allowed_table, ensure_gene_like, ensure_interval_like
from app.db.mysql import mysql_cursor
from app.schemas.gene import DOIReference, GeneDetailResponse, GeneFunctionRecord, KnownGeneDetail, KnownGeneSummary
from app.services.legacy_parsers import normalize_text, split_legacy_multi_value

router = APIRouter(prefix="/genes", tags=["Known Genes"])

@router.get("/known/search")
def search_known_genes(search: str = Query(..., alias="searchid")) -> dict:
    """搜索已知功能的克隆基因。

    功能:
        根据用户输入的关键词，在克隆基因数据库的多个字段中模糊搜索，
        包括: gene_id, gene_name, chrom_pos, gene_phenotype, gene_species, paper_doi。
        返回匹配的基因摘要列表。

    用法:
        GET /api/genes/known/search?searchid=<关键词>
        - searchid: 必填，搜索关键词（支持部分匹配）

    案例:
        请求:
          curl -X GET "http://localhost:8000/api/genes/known/search?searchid=VRN1"

        响应:
          {
            "success": true,
            "message": "ok",
            "data": {
              "query": "VRN1",
              "total": 2,
              "records": [
                {
                  "gene_id": "TraesCS5A02G391700",
                  "gene_name": "VRN-A1",
                  "chrom_pos": "5A",
                  "phenotype": "vernalization",
                  "species": "Triticum aestivum",
                  "dois": ["10.1007/s00122-003-1453-3"]
                }
              ]
            }
          }
    """

    term = search.strip().replace('"', "")
    if not term:
        raise ValidationFailure("searchid is required")

    pattern = f"%{term}%"
    sql = """
        SELECT gene_id, gene_name, chrom_pos, gene_phenotype, gene_species, paper_doi
        FROM cloned_gene_tbl
        WHERE gene_id LIKE %s
        OR gene_name LIKE %s
        OR chrom_pos LIKE %s
        OR gene_phenotype LIKE %s
        OR gene_species LIKE %s
        OR paper_doi LIKE %s
    """
    with mysql_cursor(settings.DB_CLONED_GENE) as cursor:
        cursor.execute(sql, (pattern, pattern, pattern, pattern, pattern, pattern))
        rows = cursor.fetchall()

    records = [
        KnownGeneSummary(
            gene_id=str(row["gene_id"]),
            gene_name=normalize_text(row["gene_name"]),
            chrom_pos=normalize_text(row["chrom_pos"]),
            phenotype=normalize_text(row["gene_phenotype"]),
            species=normalize_text(row["gene_species"]),
            dois=split_legacy_multi_value(row["paper_doi"]),
        )
        for row in rows
    ]
    return ok({"query": term, "total": len(records), "records": [record.model_dump() for record in records]})

@router.get("/known/{gene_id}")
def get_known_gene(gene_id: str) -> dict:
    """获取指定克隆基因的详细信息。

    功能:
        根据基因 ID 查询克隆基因的完整信息，包括基因名称、染色体位置、
        表型、物种、参考文献（DOI + 标题）、关键结果、作者和提交日期。

    用法:
        GET /api/genes/known/{gene_id}
        - gene_id: 路径参数，如 TraesCS5A02G391700

    案例:
        请求:
          curl -X GET "http://localhost:8000/api/genes/known/TraesCS5A02G391700"

        响应:
          {
            "success": true,
            "data": {
              "clone_id": 1,
              "gene_id": "TraesCS5A02G391700",
              "gene_name": "VRN-A1",
              "chrom_pos": "5A",
              "phenotype": "vernalization response",
              "species": "Triticum aestivum",
              "paper_title": ["..."],
              "references": [{"doi": "10.1007/...", "title": "..."}],
              "key_result": ["..."],
              "author": "...",
              "submission_date": "2024-01-01"
            }
          }
    """

    gene_id = ensure_gene_like(gene_id)
    with mysql_cursor(settings.DB_CLONED_GENE) as cursor:
        cursor.execute("SELECT * FROM cloned_gene_tbl WHERE gene_id = %s", (gene_id,))
        row = cursor.fetchone()

    if not row:
        raise ResourceNotFound(f"Known gene not found: {gene_id}")

    titles = split_legacy_multi_value(row.get("paper_title"))
    dois = split_legacy_multi_value(row.get("paper_doi"))
    references = [DOIReference(doi=doi, title=titles[idx] if idx < len(titles) else None) for idx, doi in enumerate(dois)]

    detail = KnownGeneDetail(
        clone_id=row.get("clone_id", row.get("id", gene_id)),
        gene_id=str(row.get("gene_id", "")),
        gene_name=normalize_text(row.get("gene_name")),
        chrom_pos=normalize_text(row.get("chrom_pos")),
        phenotype=normalize_text(row.get("gene_phenotype")),
        species=normalize_text(row.get("gene_species")),
        paper_title=titles,
        references=references,
        key_result=split_legacy_multi_value(row.get("key_result")),
        author=normalize_text(row.get("author")) or None,
        author_mail=normalize_text(row.get("author_mail")) or None,
        submission_date=row.get("submission_date"),
    )
    return ok(detail.model_dump())

@router.get("/detail/{gene_id}")
def get_gene_detail(gene_id: str) -> dict:
    """获取基因的标准化详细信息。

    功能:
        根据基因 ID（支持 IWGSC v1/v2/v3 三种版本），查询 GenePageIWGSCv1_table，
        返回基因的描述、染色体位置、蛋白长度、分子量、等电点、功能注释等信息，
        以及 JBrowse 基因组浏览器链接和 Ensembl 外部链接。

    用法:
        GET /api/genes/detail/{gene_id}
        - gene_id: 路径参数，支持 v1 (TraesCS5A02G391700)、v2 (TraesCS5A02G391700.1)、v3 (TraesCS5A03G123456) 任一格式

    案例:
        请求:
          curl -X GET "http://localhost:8000/api/genes/detail/TraesCS5A02G391700"

        响应:
          {
            "success": true,
            "data": {
              "query_gene": "TraesCS5A02G391700",
              "gene_ids": ["TraesCS5A02G391700", "TraesCS5A01G391700", "TraesCS5A03G123456"],
              "description": "MADS-box transcription factor",
              "genome": "A",
              "chromosome": "chr5A",
              "start": 587123456,
              "end": 587125000,
              "strand": "+",
              "protein_length": "240",
              "molecular_weight": "27.5",
              "isoelectric_point": "6.2",
              "functions": ["vernalization response", "flowering time regulation"],
              "jbrowse_links": { "structure_center": "http://..." },
              "external_links": { "ensembl": "https://ensembl.gramene.org/..." }
            }
          }
    """

    gene_id = ensure_gene_like(gene_id)
    with mysql_cursor(settings.DB_GENEFUNC) as cursor:
        cursor.execute(
            """
            SELECT * FROM GenePageIWGSCv1_table
            WHERE GeneIDv2=%s OR GeneIDv1=%s OR GeneIDv3=%s
            """,
            (gene_id, gene_id, gene_id),
        )
        row = cursor.fetchone()

    if not row:
        raise ResourceNotFound(f"Gene detail not found: {gene_id}")

    gene_v2 = str(row.get("GeneIDv2", ""))
    chromosome = str(row.get("Chrom", row.get("Chromosome", "")))
    genome = str(row.get("Genome", row.get("SubGenome", "")))
    start = int(row.get("Start", row.get("Start1", 0)) or 0)
    end = int(row.get("End", row.get("End1", 0)) or 0)
    loc = f"{chromosome}:{max(start - 200, 1)}..{end + 200}" if chromosome and start and end else ""

    detail = GeneDetailResponse(
        query_gene=gene_id,
        gene_ids=[value for value in [row.get("GeneIDv2"), row.get("GeneIDv1"), row.get("GeneIDv3")] if value],
        description=normalize_text(row.get("Description")) or normalize_text(row.get("description")) or None,
        genome=genome or None,
        chromosome=chromosome or None,
        start=start or None,
        end=end or None,
        strand=normalize_text(row.get("Strand")) or None,
        protein_length=str(row.get("Protein_length", row.get("ProteinLength", "")) or "") or None,
        molecular_weight=str(row.get("MolecularWeight", row.get("Molecular_Weight", "")) or "") or None,
        isoelectric_point=str(row.get("IsoelectricPoint", row.get("Isoelectric_points", "")) or "") or None,
        functions=[
            item
            for item in [
                normalize_text(row.get("Function")),
                normalize_text(row.get("Function2")),
                normalize_text(row.get("Function3")),
            ]
            if item
        ],
        jbrowse_links={
            "structure_center": f"http://wheatomics.sdau.edu.cn/jbrowse-1.12.3-release/?data=Chinese_Spring1.0&loc={loc}&tracks=IWGSCv1.1_HC_LC&tracklist=0&nav=0&overview=0&fullviewlink=0"
            if loc
            else ""
        },
        external_links={
            "ensembl": f"https://ensembl.gramene.org/Triticum_aestivum/Gene/Summary?g={gene_v2}" if gene_v2 else "",
        },
    )
    return ok(detail.model_dump())

@router.get("/functions/search")
def search_gene_functions(
    query: str = Query(..., alias="ID"),
    table: str = Query("Genefunc_table"),
) -> dict:
    """搜索基因功能注释。

    功能:
        支持三种查询模式:
        1. 基因组区间查询 - 格式 chr5A:100000-200000，查看指定染色体区段内的基因
        2. 基因 ID 查询 - 如 TraesCS5A02G391700，精确查找单个基因
        3. PFAM 结构域查询 - 以 PF 开头的 Token，按蛋白结构域搜索
        可指定查询的功能注释表（Genefunc_table 或 Genefunc_IWGSC03G_table）。

    用法:
        GET /api/genes/functions/search?ID=<查询内容>&table=<表名>
        - ID: 必填，支持基因ID / 区间 / PFAM域名
        - table: 可选，默认 Genefunc_table，也可选 Genefunc_IWGSC03G_table

    案例:
        请求 (基因ID):
          curl -X GET "http://localhost:8000/api/genes/functions/search?ID=TraesCS5A02G391700"

        请求 (区间):
          curl -X GET "http://localhost:8000/api/genes/functions/search?ID=chr5A:587000000..587200000"

        请求 (PFAM):
          curl -X GET "http://localhost:8000/api/genes/functions/search?ID=PF00319"

        响应:
          {
            "success": true,
            "data": {
              "table": "Genefunc_table",
              "count": 5,
              "records": [
                {
                  "chromosome": "chr5A",
                  "start_mb": 587.123456,
                  "end_mb": 587.125000,
                  "gene_primary": "TraesCS5A02G391700",
                  "strand": "+",
                  "description": "MADS-box transcription factor",
                  "domain": "PF00319"
                }
              ]
            }
          }
    """

    table = ensure_allowed_table(table, {"Genefunc_table", "Genefunc_IWGSC03G_table"}, "gene function table")
    tokens = [item.strip() for item in query.split() if item.strip()]
    records: list[GeneFunctionRecord] = []

    with mysql_cursor(settings.DB_GENEFUNC) as cursor:
        for token in tokens:
            if ":" in token:
                ensure_interval_like(token)
                chrom = token.split(":")[0]
                interval = token.split(":")[1].replace("..", "-")
                start_text, end_text = interval.split("-")
                start, end = int(start_text), int(end_text)
                if end <= start or end - start > 30_000_000:
                    raise ValidationFailure("End number should be more than start number and region should not be more than 30Mb")
                cursor.execute(
                    f"SELECT * FROM `{table}` WHERE Chrom=%s AND Start1 >= %s AND End1 <= %s",
                    (chrom, start, end),
                )
            elif token.startswith("PF"):
                cursor.execute(f"SELECT * FROM `{table}` WHERE Domain REGEXP %s", (token,))
            else:
                ensure_gene_like(token)
                if table == "Genefunc_IWGSC03G_table":
                    cursor.execute(f"SELECT * FROM `{table}` WHERE Gene03G=%s OR Gene02G=%s", (token, token))
                else:
                    cursor.execute(f"SELECT * FROM `{table}` WHERE Gene=%s", (token,))

            for row in cursor.fetchall():
                if table == "Genefunc_IWGSC03G_table":
                    records.append(
                        GeneFunctionRecord(
                            chromosome=str(row["Chrom"]),
                            start_mb=round(float(row["Start1"]) / 1_000_000.0, 6),
                            end_mb=round(float(row["End1"]) / 1_000_000.0, 6),
                            gene_primary=str(row["Gene03G"]),
                            gene_secondary=str(row["Gene02G"]),
                            strand=normalize_text(row["Strand"]) or None,
                            description=normalize_text(row["Description"]) or None,
                            domain=normalize_text(row["Domain"]) or None,
                        )
                    )
                else:
                    records.append(
                        GeneFunctionRecord(
                            chromosome=str(row["Chrom"]),
                            start_mb=round(float(row["Start1"]) / 1_000_000.0, 6),
                            end_mb=round(float(row["End1"]) / 1_000_000.0, 6),
                            gene_primary=str(row["Gene"]),
                            strand=normalize_text(row["Strand"]) or None,
                            description=normalize_text(row["Description"]) or None,
                            domain=normalize_text(row["Domain"]) or None,
                        )
                    )

    return ok({"table": table, "count": len(records), "records": [record.model_dump() for record in records]})
