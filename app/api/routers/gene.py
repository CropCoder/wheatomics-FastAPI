"""Gene and cloned-gene routes."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.core.config import settings
from app.core.exceptions import ResourceNotFound, ValidationFailure
from app.core.response import ok
from app.core.security import GENE_FUNCTION_TABLES, ensure_allowed_table, ensure_gene_like, ensure_interval_like

def _validate_genefunc_table(table: str) -> str:
    """Validate that a table exists in Genefuncdb. Replaces static allowlist."""
    from app.db.mysql import mysql_cursor
    with mysql_cursor(settings.DB_GENEFUNC) as cursor:
        cursor.execute("SELECT 1 FROM information_schema.TABLES WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s",
                       (settings.DB_GENEFUNC, table))
        if not cursor.fetchone():
            from app.core.exceptions import ValidationFailure
            raise ValidationFailure(f"Unknown gene function table: {table}")
    return table
from app.db.mysql import mysql_cursor
from app.schemas.gene import DOIReference, GeneDetailResponse, GeneFunctionRecord, KnownGeneDetail, KnownGeneSummary
from app.services.genome_examples import GENOME_EXAMPLES  # noqa: F401  (legacy re-export)
from app.services.legacy_parsers import normalize_text, split_legacy_multi_value

router = APIRouter(prefix="/genes", tags=["Known Genes"])
genehub_router = APIRouter(prefix="/genes", tags=["GeneHub"])
pfam_router = APIRouter(prefix="/genes/functions", tags=["PfamSearch"])
interval_router = APIRouter(prefix="/genes/functions", tags=["IntervalTool"])

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
        SELECT clone_id, gene_id, gene_name, chrom_pos, gene_phenotype, gene_species, paper_doi
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
            clone_id=row.get("clone_id", row.get("id")),
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

@router.get("/known/all")
def list_known_genes() -> dict:
    """获取所有已知功能克隆基因的列表。

    从 cloned_gene_tbl 中查询所有已知功能基因，返回基因 ID、
    基因名、染色体位置、表型、物种等核心信息。

    用法:
        GET /api/genes/known/all

    案例:
        curl "http://localhost:8000/api/genes/known/all"

        响应:
        {
          "total": 850,
          "records": [
            {
              "gene_id": "TraesCS5A02G391700",
              "gene_name": "VRN-A1",
              "chrom_pos": "5A",
              "phenotype": "vernalization response",
              "species": "Triticum aestivum"
            }
          ]
        }
    """

    with mysql_cursor(settings.DB_CLONED_GENE) as cursor:
        cursor.execute("SELECT clone_id, gene_id, gene_name, chrom_pos, gene_phenotype, gene_species FROM cloned_gene_tbl")
        rows = cursor.fetchall()

    records = [
        {
            "clone_id": row.get("clone_id", row.get("id")),
            "gene_id": str(row["gene_id"]),
            "gene_name": normalize_text(row["gene_name"]),
            "chrom_pos": normalize_text(row["chrom_pos"]),
            "phenotype": normalize_text(row["gene_phenotype"]),
            "species": normalize_text(row["gene_species"]),
        }
        for row in rows
    ]
    return ok({"total": len(records), "records": records})


@router.get("/known/by-chromosome/{chromosome}")
def list_known_genes_on_chromosome(
    chromosome: str,
) -> dict:
    """获取指定染色体上的所有已知功能克隆基因。

    染色体名支持常见格式，如 5A、chr5A、Chr5A 等。
    通过 cloned_gene_tbl 的 chrom_pos 字段匹配染色体。

    用法:
        GET /api/genes/known/by-chromosome/{chromosome}

    案例:
        curl "http://localhost:8000/api/genes/known/by-chromosome/5A"
    """

    with mysql_cursor(settings.DB_CLONED_GENE) as cursor:
        cursor.execute(
            "SELECT gene_id, gene_name, chrom_pos, gene_phenotype, gene_species FROM cloned_gene_tbl WHERE chrom_pos LIKE %s",
            (f"{chromosome}%",),
        )
        rows = cursor.fetchall()

    records = [
        {
            "gene_id": str(row["gene_id"]),
            "gene_name": normalize_text(row["gene_name"]),
            "chrom_pos": normalize_text(row["chrom_pos"]),
            "phenotype": normalize_text(row["gene_phenotype"]),
            "species": normalize_text(row["gene_species"]),
        }
        for row in rows
    ]
    return ok({"total": len(records), "chromosome": chromosome, "records": records})
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
        # Try clone_id first (numeric path-param), then fall back to
        # gene_id / gene_name. The URL detail page prefers clone_id
        # because gene_id can contain slashes, spaces, or DOI strings
        # (e.g. "MT783929/MT783930") that complicate URL encoding.
        if gene_id.isdigit():
            cursor.execute("SELECT * FROM cloned_gene_tbl WHERE clone_id = %s LIMIT 1", (int(gene_id),))
        else:
            cursor.execute("SELECT * FROM cloned_gene_tbl WHERE gene_id = %s OR gene_name = %s", (gene_id, gene_id))
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



@genehub_router.get("/detail/{gene_id}")
def get_gene_detail(gene_id: str) -> dict:
    """获取基因的标准化详细信息。

    功能:
        根据基因 ID（支持 IWGSC v1/v2/v3 三种版本），查询 GenePageIWGSCv1_table，
        返回基因的描述、染色体位置、蛋白长度、分子量、等电点、功能注释等信息，
        以及 JBrowse 基因组浏览器链接和 Ensembl 外部链接。

    用法:
        GET /api/genes/detail/{gene_id}
        - gene_id: 路径参数，支持 v1 (TraesCS5A02G391700)、v2 (TraesCS5A02G391700.1)、v3 (TraesCS5A03G1158600) 任一格式

    案例:
        请求:
          curl -X GET "http://localhost:8000/api/genes/detail/TraesCS5A02G391700"

        响应:
          {
            "success": true,
            "data": {
              "query_gene": "TraesCS5A02G391700",
              "gene_ids": ["TraesCS5A02G391700", "TraesCS5A01G391700", "TraesCS5A03G1158600"],
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
    with mysql_cursor(settings.DB_GENEHUB) as cursor:
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

def _make_function_record(row, table):
    """Build a GeneFunctionRecord from a DB row, handling different table schemas."""
    # The IWGSC v1.0 (v2) tables only have Gene03G/Gene02G columns; every
    # other Genefunc_* table uses `Gene`. Match both the old
    # Genefunc_IWGSC03G_table name and the renamed
    # Genefunc_CS_IWGSC03G_table so this works after the rename.
    is_iwgsc_v2 = table in ("Genefunc_IWGSC03G_table", "Genefunc_CS_IWGSC03G_table")
    if is_iwgsc_v2:
        return GeneFunctionRecord(
            chromosome=str(row["Chrom"]),
            start_mb=round(float(row["Start1"]) / 1_000_000.0, 6),
            end_mb=round(float(row["End1"]) / 1_000_000.0, 6),
            gene_primary=str(row["Gene03G"]),
            gene_secondary=str(row["Gene02G"]),
            strand=normalize_text(row["Strand"]) or None,
            description=normalize_text(row.get("Description") or row.get("description") or "") or None,
            domain=normalize_text(row["Domain"]) or None,
        )
    return GeneFunctionRecord(
        chromosome=str(row["Chrom"]),
        start_mb=round(float(row["Start1"]) / 1_000_000.0, 6),
        end_mb=round(float(row["End1"]) / 1_000_000.0, 6),
        gene_primary=str(row["Gene"]),
        strand=normalize_text(row["Strand"]) or None,
        description=normalize_text(row.get("Description") or row.get("description") or "") or None,
        domain=normalize_text(row["Domain"]) or None,
    )

@pfam_router.get("/pfam")
def search_pfam(
    domain: str = Query(..., alias="ID"),
    table: str = Query("Genefunc_table"),
) -> dict:
    """PfamSearch: 按 PFAM 结构域搜索基因 [gene family]

    功能:
        输入 PFAM 结构域 ID（以 PF 开头），返回包含该结构域的
        所有基因列表。可指定查询表（Genefunc_table 或 Genefunc_IWGSC03G_table）。

    关联网站:
        对应 PfamSearch 工具: https://wheatomics.sdau.edu.cn/tools/proteinfamily.html

    用法:
        GET /api/genes/functions/pfam?ID=<PFAM域名>&table=<表名>
        - ID: 必填，PFAM 结构域 ID，如 PF00319
        - table: 可选，默认 Genefunc_table

    案例:
        请求:
          curl -X GET "http://localhost:8000/api/genes/functions/pfam?ID=PF00319"

        响应:
          {
            "success": true,
            "data": {
              "table": "Genefunc_table",
              "domain": "PF00319",
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

    if not domain.startswith("PF"):
        raise ValidationFailure("PFAM domain ID must start with PF (e.g. PF00319)")

    table = _validate_genefunc_table(table)
    records: list[GeneFunctionRecord] = []

    with mysql_cursor(settings.DB_GENEFUNC) as cursor:
        cursor.execute(f"SELECT * FROM `{table}` WHERE Domain REGEXP %s", (domain,))
        for row in cursor.fetchall():
            records.append(_make_function_record(row, table))

    return ok({"table": table, "domain": domain, "count": len(records), "records": [record.model_dump() for record in records]})


@interval_router.get("/tables")
def list_gene_function_tables() -> dict:
    """查询 Genefuncdb 中所有表的信息。

    功能:
        直接连接 Genefuncdb 数据库，执行 SHOW TABLES 获取所有表名，
        同时查询每个表的行数和字段列表，返回结构化信息。

    用法:
        GET /api/genes/functions/tables
        无需参数。

    案例:
        请求:
          curl -X GET "http://localhost:8000/api/genes/functions/tables"

        响应:
          {
            "success": true,
            "data": {
              "database": "Genefuncdb",
              "total_tables": 5,
              "tables": [
                { "name": "Genefunc_table", "rows": 168900, "columns": ["Chrom", "Start1", ...] },
                ...
              ]
            }
          }
    """

    tables: list[dict] = []
    with mysql_cursor(settings.DB_GENEFUNC) as cursor:
        # Pull row counts and column names from information_schema in two
        # queries instead of running SHOW TABLES + COUNT(*) + DESCRIBE per
        # table (88 tables × 2 queries = 176 round-trips, ~68s). The
        # registry rarely changes, so approximate table_rows is fine.
        cursor.execute(
            """
            SELECT TABLE_NAME, TABLE_ROWS
            FROM information_schema.tables
            WHERE TABLE_SCHEMA = %s
            """,
            (settings.DB_GENEFUNC,),
        )
        rows_map = {
            row["TABLE_NAME"]: row.get("TABLE_ROWS")
            for row in cursor.fetchall()
        }

        cursor.execute(
            """
            SELECT TABLE_NAME, COLUMN_NAME
            FROM information_schema.columns
            WHERE TABLE_SCHEMA = %s
            ORDER BY TABLE_NAME, ORDINAL_POSITION
            """,
            (settings.DB_GENEFUNC,),
        )
        cols_map: dict[str, list[str]] = {}
        for row in cursor.fetchall():
            cols_map.setdefault(row["TABLE_NAME"], []).append(
                row["COLUMN_NAME"]
            )

    for tbl_name in sorted(rows_map):
        tables.append(
            {
                "name": tbl_name,
                "rows": rows_map[tbl_name],
                "columns": cols_map.get(tbl_name, []),
            }
        )

    return ok({"database": "Genefuncdb", "total_tables": len(tables), "tables": tables})


@interval_router.get("/examples")
def list_genome_examples() -> dict:
    """获取所有基因组的示例查询数据。

    功能:
        返回每个基因组对应的示例 Region、Gene ID、Pfam ID，
        用于 Interval Tool 前端的示例链接展示。

    用法:
        GET /api/genes/functions/examples
        无需参数。

    案例:
        请求:
          curl -X GET "http://localhost:8000/api/genes/functions/examples"

        响应:
          {
            "success": true,
            "data": {
              "examples": [
                { "table_name": "Genefunc_table", "display_name": "Chinese Spring genome v1.0",
                  "region": "chr1A:1-141522", "gene": "TraesCS1A01G000100LC", "pfam": "" },
                ...
              ]
            }
          }
    """

    # Read from Genefunc_registry so the dropdown stays in sync with
    # the actual list of installed genomes. The registry has 86 rows
    # (visible=1) as of 2026-07; the legacy hardcoded GENOME_EXAMPLES
    # list only had 32.
    # We use the legacy example_chr_id / example_gene_id columns
    # (not example_species_chr_id / example_cds_id) per user request.
    # Note: Genefunc_registry has no `display_name` column; we alias
    # table_name to display_name for the frontend (the /registry
    # endpoint does the same thing).
    sql = """
        SELECT table_name AS display_name, example_chr_id,
               example_gene_id, COALESCE(Polyploidy, '') AS polyploidy
        FROM Genefunc_registry
        WHERE visible = 1
        ORDER BY display_order, id
    """
    with mysql_cursor(settings.DB_GENEFUNC) as cursor:
        cursor.execute(sql)
        rows = cursor.fetchall()

    def _ensure_range(chr_id):
        # example_chr_id may store only a chromosome (e.g. "chr1A") without
        # a start-end range. The interval frontend expects "chr:start-end",
        # so append a default 1-5000000 window when no ":" is present.
        s = (chr_id or "").strip()
        if not s:
            return s
        return s if ":" in s else f"{s}:1-5000000"

    def _friendly_name(tbl):
        # Turn `Genefunc_<species>_<cultivar>_table` into a short human
        # label like `<Polyploidy>_<species>_<cultivar>` for the interval
        # dropdown, where `<Polyploidy>` comes from the Genefunc_registry
        # row (e.g. AABBDD / AABB / AA / DD / SS). Falls back to the raw
        # name if the pattern doesn't match. table_name itself is
        # unchanged so the interval query (`?table=...`) keeps working.
        if not tbl:
            return tbl
        s = tbl
        if s.startswith("Genefunc_"):
            s = s[len("Genefunc_"):]
        if s.endswith("_table"):
            s = s[:-len("_table")]
        return s

    examples = [
        {
            "table_name":   r.get("display_name"),
            "display_name": (
                f"{r['polyploidy']}_{_friendly_name(r.get('display_name'))}"
                if r.get("polyploidy")
                else _friendly_name(r.get("display_name"))
            ),
            # Frontend keys are region / gene / pfam for backward compat.
            "region":       _ensure_range(r.get("example_chr_id")),
            "gene":         r.get("example_gene_id"),
            # Genefunc_registry has no Pfam-domain column; use a default.
            "pfam":         "PF00931",
        }
        for r in rows
    ]
    return ok({"examples": examples})
@interval_router.get("/registry")
def list_gene_function_registry() -> dict:
    """查询 Genefuncdb.Genefunc_registry 表。

    功能:
        返回 Genefunc_registry 表中所有注册的基因功能表元数据。
        包含 id, table_name, display_name, Subgenome, Polyploidy, chromosome_level,
        Doi, title, Abstract, example_chr, example_id 等字段。

    注意:
        表名大小写敏感（Linux 下 MySQL `lower_case_table_names=0`），必须写
        `Genefunc_registry`（首字母大写），否则 MySQL 抛 1146 表不存在。

    用法:
        GET /api/genes/functions/registry
        无需参数。

    案例:
        请求:
          curl -X GET "http://localhost:8000/api/genes/functions/registry"

        响应:
          {
            "success": true,
            "data": {
              "database": "genefunc_registry",
              "count": 2,
              "records": [
                {
                  "id": 1,
                  "table_name": "Genefunc_Abo_table",
                  "display_name": "Abbondanza (Abo)",
                  "subgenome": "ABD",
                  "polyploidy": "Allohexaploid",
                  "chromosome_level": "AABBDD",
                  "doi": "10.1038/s41586-024-08277-0",
                  "title": "Unraveling Allelic Impacts...",
                  "abstract": "The TaVP1-B gene...",
                  "example_species_chr": "chr1A_Abo",
                  "example_cds": "Abo1A000100.1",
                  "example_protein": "Abo1A000100.1.p"
                }
              ]
            }
          }
    """
    records: list[dict] = []
    with mysql_cursor(settings.DB_GENEFUNC) as cursor:
        # MySQL table names are case-sensitive on Linux. The actual table on
        # Genefuncdb is `Genefunc_registry` (capital G), per /tables endpoint.
        cursor.execute("""
            SELECT
                id,
                table_name,
                Accession,
                `Group`,
                Polyploidy,
                chromosome_level,
                Doi,
                title,
                Abstract,
                example_species_chr_id,
                example_cds_id,
                example_protein_id,
                display_order,
                visible
            FROM Genefunc_registry
            WHERE visible = 1
            ORDER BY display_order, id
        """)
        for row in cursor.fetchall():
            records.append({
                "id": row.get("id"),
                "table_name": row.get("table_name"),
                "display_name": row.get("table_name"),
                "subgenome": row.get("Accession"),
                "group": row.get("Group"),
                "polyploidy": row.get("Polyploidy"),
                "chromosome_level": row.get("chromosome_level"),
                "doi": row.get("Doi"),
                "title": row.get("title"),
                "abstract": row.get("Abstract"),
                "example_species_chr": row.get("example_species_chr_id"),
                "example_cds": row.get("example_cds_id"),
                "example_protein": row.get("example_protein_id"),
            })
    return ok({"database": "genefunc_registry", "count": len(records), "records": records})

@interval_router.get("/interval")
def search_gene_interval(
    region: str = Query(..., alias="ID"),
    table: str = Query("Genefunc_table"),
) -> dict:
    """按染色体区间搜索基因。

    功能:
        输入染色体区间（如 chr5A:587000000..587200000），返回该区间内
        的所有基因列表。可指定查询表（Genefunc_table 或 Genefunc_IWGSC03G_table）。

    关联网站:
        对应 IntervalTool: https://wheatomics.sdau.edu.cn/tools/intervalTools.html

    用法:
        GET /api/genes/functions/interval?ID=<区间>&table=<表名>
        - ID: 必填，染色体区间，格式 chr5A:587000000..587200000
        - table: 可选，默认 Genefunc_table

    案例:
        请求:
          curl -X GET "http://localhost:8000/api/genes/functions/interval?ID=chr5A:587000000..587200000"

        响应:
          {
            "success": true,
            "data": {
              "table": "Genefunc_table",
              "region": "chr5A:587000000..587200000",
              "count": 5,
              "records": [
                {
                  "chromosome": "chr5A",
                  "start_mb": 587.123456,
                  "end_mb": 587.125000,
                  "gene_primary": "TraesCS5A02G391700",
                  "strand": "+",
                  "description": "MADS-box transcription factor",
                  "domain": null
                }
              ]
            }
          }
    """

    table = _validate_genefunc_table(table)
    records: list[GeneFunctionRecord] = []

    # 如果不是区间格式（不含:），按基因 ID 搜索
    if ":" not in region:
        with mysql_cursor(settings.DB_GENEFUNC) as cursor:
            # 根据表类型动态选择基因列
            if table in ("Genefunc_IWGSC03G_table", "Genefunc_CS_IWGSC03G_table"):
                gene_cols = ["Gene03G", "Gene02G"]
            else:
                gene_cols = ["Gene"]
            where_clause = " OR ".join(f"`{col}`=%s" for col in gene_cols)
            cursor.execute(
                f"SELECT * FROM `{table}` WHERE {where_clause}",
                tuple(region for _ in gene_cols),
            )
            for row in cursor.fetchall():
                records.append(_make_function_record(row, table))
        return ok({"table": table, "region": region, "count": len(records), "records": [record.model_dump() for record in records]})

    ensure_interval_like(region)
    chrom = region.split(":")[0]
    interval = region.split(":")[1].replace("..", "-")
    start_text, end_text = interval.split("-")
    start, end = int(start_text), int(end_text)

    if end <= start or end - start > 30_000_000:
        raise ValidationFailure("End number should be more than start number and region should not be more than 30Mb")

    with mysql_cursor(settings.DB_GENEFUNC) as cursor:
        cursor.execute(
            f"SELECT * FROM `{table}` WHERE Chrom=%s AND Start1 >= %s AND End1 <= %s",
            (chrom, start, end),
        )
        for row in cursor.fetchall():
            records.append(_make_function_record(row, table))

    return ok({"table": table, "region": region, "count": len(records), "records": [record.model_dump() for record in records]})


