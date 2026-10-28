"""KnownGene 写接口的服务层：字段规格、校验/归一化/派生、事务内写入与审计。

本模块把"纯函数校验"与"数据库事务写入"分开，便于测试：
- 纯函数：``validate_create_payload`` / ``validate_update_payload`` /
  ``derive_species_primary`` / ``derive_chromosome`` / ``split_multi_value`` 等，
  不触碰数据库，单测可完全离线跑；
- 事务函数：``create_known_gene`` / ``update_known_gene`` / ``run_bulk`` /
  ``delete_known_gene`` 接收**已在事务中的 cursor**，只做 SQL 与审计写入，
  **不 commit / rollback**——事务边界由路由（``mysql_cursor``）或 CLI 控制，
  从而保证"主表写 + 审计写"同事务提交/回滚。

数据事实（与 docs/known_genes/ 的 v2056 冻结口径一致）
------------------------------------------------------
- ``cloned_gene_tbl`` 共 24 列（16 旧列 + v2056 新增 8 列），本模块
  ``DB_INSERT_COLUMNS`` 就是"除 clone_id 外的 23 个可写列"；
- 多值字段 ``paper_title`` / ``paper_doi`` / ``publication_years`` 在 DB 里用
  ``###`` 连接、**按位置一一对应**；API 入参允许 list 或 ``"; "`` 分隔的
  字符串（含 ``###`` 时按 ``###`` 拆，避免误伤标题里本身的 ``;``）；
- ``functional_category`` 6 值、``research_strategy`` 3 值受控；
- ``species_primary``（23 个 NCBI 学名）与 ``chromosome``（38 个标签）是派生列，
  由 ``gene_species`` / ``chrom_pos`` 自动计算；调用方显式传入时也接受，但会
  按受控集合校验（便于 ``scripts/known_gene_push.py`` 回放 JSONL 的派生值）。

审计
----
每次写操作都往 ``cloned_gene_change_log`` 写一行：``action`` +
``before_json`` / ``after_json``（**完整行**，date/Decimal 转字符串）+
``changed_fields``（逗号分隔列名）+ actor（``key_id`` / ``label``）+
``client_ip`` + ``reason``。create/bulk_create 的 ``before_json`` 为 NULL；
delete 只由 ``scripts/known_gene_admin.py`` 调用（v1 API 不暴露删除）。

用法（路由层）::

    with mysql_cursor(settings.DB_CLONED_GENE) as cursor:
        result = create_known_gene(cursor, row, actor=ctx, client_ip=ip)
    # 正常退出 → mysql_cursor 自动 commit；异常 → 自动 rollback（审计同事务）

用法（CLI 层）::

    conn = pymysql.connect(..., cursorclass=DictCursor)
    with conn.cursor() as cursor:
        result = delete_known_gene(cursor, 1625, confirm_gene_id="TraesCS...", reason="...")
    conn.commit()
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from app.core.exceptions import ResourceNotFound

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 规格常量
# ---------------------------------------------------------------------------
DATA_DIR = Path(__file__).resolve().parent / "data"
SPECIES_MAP_PATH = DATA_DIR / "known_gene_species_map.json"

#: 受控功能大类（v2056 数据 5 值，见 docs/known_genes/CONTEXT.md §1）。
FUNCTIONAL_CATEGORIES: tuple[str, ...] = (
    "Biotic Stress",
    "Abiotic Stress",
    "Quality & Yield",
    "Morphology & Domestication",
    "Physiology & Metabolic Processes",
    "Reproduction & Phenology",
)
#: 受控研究策略（v2056 数据 3 值）。
RESEARCH_STRATEGIES: tuple[str, ...] = (
    "Reverse genetics",
    "Forward genetics",
    "Not reported",
)

#: 新增必填字段（顺序即报错顺序、也是文档顺序）。
REQUIRED_WRITE_FIELDS: tuple[str, ...] = (
    "gene_id",
    "gene_name",
    "reference_genome_id",
    "gene_species",
    "chrom_pos",
    "gene_phenotype",
    "functional_category",
    "research_strategy",
    "key_result",
)
#: 可选字段（含可显式覆盖的派生列）。
OPTIONAL_WRITE_FIELDS: tuple[str, ...] = (
    "protein_family",
    "validation_method",
    "cloning_method",
    "cloning_method_description",
    "function_description",
    "author",
    "author_mail",
    "submission_date",
    "publication_year",
    "publication_years",
    "paper_title",
    "paper_doi",
    "species_primary",
    "chromosome",
)
#: 写接口允许出现的全部字段（白名单；其余字段 → 422）。
ALLOWED_WRITE_FIELDS: frozenset[str] = frozenset(REQUIRED_WRITE_FIELDS + OPTIONAL_WRITE_FIELDS)
#: 服务端派生列：未传时自动派生，显式传入时按受控集合校验。
DERIVED_WRITE_FIELDS: tuple[str, ...] = (
    "species_primary",
    "chromosome",
    "publication_year",
    "publication_years",
)

#: INSERT 白名单（23 列，不含自增 clone_id；顺序对齐 v2056 迁移脚本）。
DB_INSERT_COLUMNS: tuple[str, ...] = (
    "gene_id",
    "reference_genome_id",
    "gene_name",
    "gene_species",
    "chrom_pos",
    "chromosome",
    "gene_phenotype",
    "key_result",
    "function_description",
    "protein_family",
    "cloning_method",
    "cloning_method_description",
    "validation_method",
    "research_strategy",
    "functional_category",
    "paper_title",
    "paper_doi",
    "publication_year",
    "publication_years",
    "species_primary",
    "author",
    "author_mail",
    "submission_date",
)
#: UPDATE 允许的列集合（同 INSERT 白名单）。
DB_WRITE_COLUMNS: frozenset[str] = frozenset(DB_INSERT_COLUMNS)

#: 列长度上限（与 scripts/known_genes_v2055_ddl.sql 的 v2056 结构一致）。
#: TEXT 列按 MySQL TEXT 的 65535 字节量级给软上限（按字符计，中文更保守）。
TEXT_SOFT_LIMIT = 65535
MAX_LENGTHS: dict[str, int] = {
    "gene_id": 300,
    "gene_name": 500,
    "chrom_pos": 500,
    "gene_phenotype": 2000,
    "gene_species": 1000,
    "reference_genome_id": 100,
    "research_strategy": 32,
    "functional_category": 64,
    "species_primary": 64,
    "publication_years": 64,
    "chromosome": 16,
    "cloning_method": 255,
    "key_result": 15000,
    "paper_title": TEXT_SOFT_LIMIT,
    "paper_doi": TEXT_SOFT_LIMIT,
    "function_description": TEXT_SOFT_LIMIT,
    "cloning_method_description": TEXT_SOFT_LIMIT,
    "protein_family": TEXT_SOFT_LIMIT,
    "validation_method": TEXT_SOFT_LIMIT,
    "author": 100,
    "author_mail": 200,
}

#: 新增时缺省作者/邮箱/提交日期（规格固定值；API 与 v2056 迁移的占位作者不同，
#: 便于按来源区分"API 新增"与"表格导入"）。
DEFAULT_AUTHOR = "WheatOmics API"
DEFAULT_AUTHOR_MAIL = "shengweima@icloud.com"

#: 审计表允许的 action 值（与 scripts/sql/known_gene_write_api.sql 注释一致）。
KNOWN_GENE_ACTIONS: tuple[str, ...] = (
    "create",
    "update",
    "delete",
    "bulk_create",
    "bulk_update",
)

#: 批量模式。
BULK_MODES: tuple[str, ...] = ("insert_only", "upsert")

_YEAR_RE = re.compile(r"^\d{4}$")
_CHR_IN_TEXT_RE = re.compile(r"chr\s*([0-9]+[A-Za-z]{0,2})", re.IGNORECASE)
_CHR_TOKEN_RE = re.compile(r"\b([0-9]+[A-Za-z]{0,2})\s*:")
_CHR_LABEL_RE = re.compile(r"^(?:chr)?[0-9]{1,2}[A-Za-z]{0,2}$", re.IGNORECASE)
_GENE_LIKE_RE = re.compile(r"^[A-Za-z0-9_.:\-]+$")
_DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_CV_SPLIT_RE = re.compile(r"\s+cv\.\s+", re.IGNORECASE)
_SPECIES_SPLIT_RE = re.compile(r"\s*[\(;]\s*")
_AUTHORITY_SUFFIX_RE = re.compile(r"\s+(?:L\.|L|R\.Br\.|Host\.)$")


# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------
class GeneWriteValidationError(Exception):
    """字段校验失败（路由映射为 422）。``errors`` / ``warnings`` 都是中文短句。"""

    def __init__(self, errors: list[str], warnings: Optional[list[str]] = None) -> None:
        self.errors = list(errors)
        self.warnings = list(warnings or [])
        super().__init__("; ".join(self.errors))

    def as_detail(self) -> dict[str, Any]:
        """转成 HTTPException detail（保留 warnings 供调用方提示）。"""

        detail: dict[str, Any] = {"errors": self.errors}
        if self.warnings:
            detail["warnings"] = self.warnings
        return detail


class DuplicateGeneError(Exception):
    """(gene_id, gene_name) 已存在（路由映射为 409）。"""

    def __init__(self, gene_id: str, gene_name: str, clone_id: Optional[int] = None) -> None:
        self.gene_id = gene_id
        self.gene_name = gene_name
        self.clone_id = clone_id
        super().__init__(f"KnownGene 已存在: gene_id={gene_id!r}, gene_name={gene_name!r}")


# ---------------------------------------------------------------------------
# 物种映射 / 派生（纯函数）
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _species_map() -> dict[str, Any]:
    """加载 ``app/services/data/known_gene_species_map.json``（进程内缓存）。"""

    with SPECIES_MAP_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=1)
def canonical_species() -> frozenset[str]:
    """23 个受控物种学名（NCBI binomial token）。"""

    return frozenset(_species_map()["canonical_values"])


@lru_cache(maxsize=1)
def species_aliases() -> dict[str, str]:
    """小写别名 → 受控学名。

    覆盖：23 个规范学名本身、英文常用名（bread wheat 等）、人工整理的同义名
    （Triticum durum → Triticum turgidum subsp. durum 等），以及属名缩写
    （``T. aestivum``）。**未命中别名表的写法不会被猜成某个受控值**，而是
    学名回退 + warning，交由维护者补映射。
    """

    payload = _species_map()
    aliases: dict[str, str] = {}
    for canonical in payload["canonical_values"]:
        aliases.setdefault(canonical.casefold(), canonical)
    for common_name, canonical in payload.get("common_names", {}).items():
        aliases.setdefault(str(common_name).casefold(), canonical)
    for synonym, canonical in payload.get("synonyms", {}).items():
        if canonical in payload["canonical_values"]:
            aliases.setdefault(str(synonym).casefold(), canonical)
    # 属名缩写：Triticum aestivum -> T. aestivum；Aegilops tauschii -> A. tauschii
    for canonical in payload["canonical_values"]:
        parts = canonical.split()
        if len(parts) >= 2 and re.fullmatch(r"[A-Z][a-z]+", parts[0]):
            abbreviated = f"{parts[0][0]}. {' '.join(parts[1:])}"
            aliases.setdefault(abbreviated.casefold(), canonical)
    # 同义名也补属名缩写：Triticum durum -> T. durum（命中 synonyms 里的 canonical）
    for synonym, canonical in payload.get("synonyms", {}).items():
        parts = str(synonym).split()
        if (
            canonical in payload["canonical_values"]
            and len(parts) >= 2
            and re.fullmatch(r"[A-Z][a-z]+", parts[0])
        ):
            abbreviated = f"{parts[0][0]}. {' '.join(parts[1:])}"
            aliases.setdefault(abbreviated.casefold(), canonical)
    return aliases


def _species_head(raw: str) -> str:
    """取 "学名 (常用名)" / 多物种串里的首个学名并去掉命名人/品种尾巴。"""

    head = _SPECIES_SPLIT_RE.split(raw.strip(), maxsplit=1)[0].strip()
    head = _CV_SPLIT_RE.split(head, maxsplit=1)[0].strip()
    head = _AUTHORITY_SUFFIX_RE.sub("", head).strip()
    head = re.sub(r"\s+", " ", head)
    return head


def derive_species_primary(gene_species: object) -> tuple[str, list[str]]:
    """从 ``gene_species`` 派生受控 ``species_primary``（学名 token）。

    规则（与 ``scripts/known_genes_v2055/extract.py::derive_species_primary`` 对齐）:
    1. 原文整串命中 ``raw_to_canonical``（296 条，含多物种长描述）→ 直接用；
    2. 规范化空白后整串再命中一次；
    3. 取首个学名（截断到第一个 ``(`` / ``;``，去 ``cv.`` 材料描述和命名人缩写），
       按别名表（规范名 / 英文常用名 / 同义名 / 属名缩写）归一；
    4. 仍不命中 → 返回该学名本身 + warning（提示补映射）。

    返回 ``(species_primary, warnings)``；空输入返回 ``("", [warning])``。

    案例::

        >>> derive_species_primary("Triticum aestivum (bread wheat)")
        ('Triticum aestivum', [])
        >>> derive_species_primary("T. durum cv. Svevo")
        ('Triticum turgidum subsp. durum', [...])
    """

    text = "" if gene_species is None else str(gene_species).strip()
    if not text:
        return "", ["gene_species 为空，无法派生 species_primary"]
    mapping: dict[str, str] = _species_map()["raw_to_canonical"]
    if text in mapping:
        return mapping[text], []
    compact = re.sub(r"\s+", " ", text)
    if compact in mapping:
        return mapping[compact], []

    aliases = species_aliases()
    head = _species_head(text)
    candidates = [head]
    stripped = _AUTHORITY_SUFFIX_RE.sub("", head).strip()
    if stripped and stripped != head:
        candidates.append(stripped)
    for candidate in candidates:
        hit = aliases.get(candidate.casefold())
        if hit:
            return hit, [f"gene_species 未命中原文映射表，按学名别名归一到 {hit!r}"]
    if not head:
        return "", [f"gene_species 无法解析出学名: {text[:80]!r}"]
    return head, [
        f"gene_species 未命中映射表，按学名回退为 {head!r}；"
        "如需归一化请补充 app/services/data/known_gene_species_map.json 的 synonyms/raw_to_canonical"
    ]


def _format_chrom_token(token: str) -> str:
    """``7a`` → ``7A``；``54`` → ``chr54``（与 v2056 数据标签一致）。"""

    token = token.strip()
    if re.search(r"[A-Za-z]", token):
        return token.upper()
    return "chr" + token


def derive_chromosome(chrom_pos: object) -> tuple[str, list[str]]:
    """从 ``chrom_pos`` 派生 ``chromosome`` 标签。

    优先 ``chr\\s*([0-9]+[A-Za-z]{0,2})``（``Refv1.0 chr7A:...`` / ``MorexV3 chr3H:...``），
    其次 ``\\b([0-9]+[A-Za-z]{0,2})\\s*:``（``AetTA1675 2D:2.33-2.45Mb``）；
    纯数字 token 存 ``chr<N>``（``chr54`` / ``chr51``），其余大写（``7A`` / ``3H``）。

    返回 ``(chromosome, warnings)``；解析失败返回 ``("", [warning])``。
    """

    text = "" if chrom_pos is None else str(chrom_pos).strip()
    if not text:
        return "", ["chrom_pos 为空，无法派生 chromosome"]
    match = _CHR_IN_TEXT_RE.search(text)
    if match:
        return _format_chrom_token(match.group(1)), []
    match = _CHR_TOKEN_RE.search(text)
    if match:
        token = _format_chrom_token(match.group(1))
        return token, [f"chrom_pos 缺少 'chr' 前缀，按位置正则解析 chromosome={token!r}"]
    return "", [f"无法从 chrom_pos 解析 chromosome（应形如 'Refv1.0 chr7A:112.2-112.3Mb'）: {text[:80]!r}"]


def normalize_chromosome_override(value: object) -> tuple[str, list[str]]:
    """校验调用方显式传入的 chromosome（``7a`` / ``chr54`` 等）。"""

    text = "" if value is None else str(value).strip()
    if not text:
        return "", []
    if len(text) > MAX_LENGTHS["chromosome"]:
        raise GeneWriteValidationError([f"chromosome 超长：{len(text)} > {MAX_LENGTHS['chromosome']}"])
    if not _CHR_LABEL_RE.match(text):
        raise GeneWriteValidationError(
            [f"chromosome 取值非法: {text!r}（应形如 7A / 3H / 1R / chr54）"]
        )
    match = re.fullmatch(r"chr(\d+)([A-Za-z]{0,2})", text, re.IGNORECASE)
    if match:
        if match.group(2):
            return match.group(2).upper(), []
        return "chr" + match.group(1), []
    if text.isdigit():
        # 纯数字 token 统一存 chr<N>（与 derive_chromosome 的规则一致）
        return "chr" + text, []
    return text.upper(), []


# ---------------------------------------------------------------------------
# 多值字段 / 年份 / 文本归一化（纯函数）
# ---------------------------------------------------------------------------
def split_multi_value(value: object) -> list[str]:
    """把多值入参拆成 token 列表。

    - ``list/tuple``：逐项 ``str().strip()``，保留中间空串（位置对齐），去掉尾部空串；
    - ``str``：含 ``###`` → 按 ``###`` 拆；否则按 ``"; "``（分号+空白）拆；
    - ``None`` → ``[]``。

    案例::

        >>> split_multi_value(["A", "B"])
        ['A', 'B']
        >>> split_multi_value("A; B")
        ['A', 'B']
        >>> split_multi_value("A###B")
        ['A', 'B']
    """

    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        items = [str(item).strip() for item in value]
    elif isinstance(value, str):
        if "###" in value:
            items = [part.strip() for part in value.split("###")]
        else:
            items = [part.strip() for part in re.split(r";\s+", value)]
    else:
        items = [str(value).strip()]
    while items and not items[-1]:
        items.pop()
    return items


def join_multi_value(items: list[str]) -> Optional[str]:
    """``###`` 连接多值；全空返回 None（DB 存 NULL 而不是空串）。"""

    cleaned = [item.strip() for item in items if item is not None]
    while cleaned and not cleaned[-1]:
        cleaned.pop()
    if not cleaned:
        return None
    return "###".join(cleaned)


def parse_year_tokens(items: list[str]) -> tuple[list[int], list[str]]:
    """从 token 列表里提取 4 位年份；非法 token 记 warning 但不阻断。"""

    years: list[int] = []
    warnings: list[str] = []
    for token in items:
        token = token.strip()
        if not token:
            continue
        if _YEAR_RE.match(token):
            years.append(int(token))
        else:
            warnings.append(f"publication_years 中 {token!r} 不是 4 位年份，已保留原文但不计入 publication_year")
    return years, warnings


def derive_publication_year(years_text: object) -> Optional[int]:
    """从 ``###`` 原文里取最早年份（``publication_year = int(min(year tokens))``）。"""

    years, _ = parse_year_tokens(split_multi_value(years_text))
    return min(years) if years else None


def _validate_year_scalar(value: object) -> Optional[int]:
    """校验单个 ``publication_year``（YEAR(4)：1901–2155）。"""

    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise GeneWriteValidationError([f"publication_year 取值非法: {value!r}（应为 4 位年份整数）"])
    text = str(value).strip()
    if not _YEAR_RE.match(text):
        raise GeneWriteValidationError([f"publication_year 取值非法: {value!r}（应为 4 位年份整数）"])
    year = int(text)
    if not 1901 <= year <= 2155:
        raise GeneWriteValidationError([f"publication_year 超出 MySQL YEAR(4) 范围 1901–2155: {year}"])
    return year


def _coerce_date(value: object) -> Optional[date]:
    """校验 ``submission_date``（date / datetime / 'YYYY-MM-DD'）。"""

    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise GeneWriteValidationError(
            [f"submission_date 取值非法: {value!r}（应为 'YYYY-MM-DD'）"]
        ) from exc


def _clean_text(field_name: str, value: object) -> Optional[str]:
    """文本清洗：统一换行、去首尾空白、拒绝 NUL；空值 → None。"""

    if value is None:
        return None
    if isinstance(value, (dict, list, tuple)):
        raise GeneWriteValidationError([f"{field_name} 必须是字符串，收到 {type(value).__name__}"])
    text = str(value).replace("\r\n", "\n").replace("\r", "\n").strip()
    if "\x00" in text:
        raise GeneWriteValidationError([f"{field_name} 含非法字符 NUL(\\x00)"])
    return text or None


def _check_length(field_name: str, text: Optional[str]) -> None:
    limit = MAX_LENGTHS.get(field_name)
    if text is not None and limit is not None and len(text) > limit:
        raise GeneWriteValidationError(
            [f"{field_name} 超长：{len(text)} 字符 > 上限 {limit} 字符（DB 列宽）"]
        )


# ---------------------------------------------------------------------------
# 校验结果
# ---------------------------------------------------------------------------
@dataclass
class NormalizedWrite:
    """一次校验的结果：``columns`` 为 DB 白名单列 → 值，``warnings`` 为提示。"""

    columns: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def _check_unknown_fields(payload: dict, errors: list[str]) -> None:
    unknown = sorted(set(payload) - ALLOWED_WRITE_FIELDS)
    if unknown:
        errors.append(
            "未知字段（写入白名单之外）: "
            + ", ".join(unknown)
            + "；允许字段: "
            + ", ".join(REQUIRED_WRITE_FIELDS + OPTIONAL_WRITE_FIELDS)
        )


def _validate_enum(name: str, value: Optional[str], allowed: tuple[str, ...], errors: list[str]) -> Optional[str]:
    if value is None:
        return None
    if value not in allowed:
        errors.append(f"{name} 取值非法: {value!r}；允许值: " + " / ".join(allowed))
        return None
    return value


def _validate_text_field(name: str, value: object, errors: list[str], warnings: list[str]) -> Optional[str]:
    """通用文本字段：清洗 + 长度。个体错误即时收集，不中断其它字段。"""

    try:
        text = _clean_text(name, value)
        _check_length(name, text)
        return text
    except GeneWriteValidationError as exc:
        errors.extend(exc.errors)
        return None


def _validate_multi_field(
    name: str, value: object, errors: list[str], warnings: list[str]
) -> Optional[str]:
    """``paper_title`` / ``paper_doi`` 等多值字段：list 或 ``; `` 字符串 → ``###`` 原文。"""

    try:
        items = split_multi_value(value)
        text = join_multi_value(items)
        _check_length(name, text)
        return text
    except GeneWriteValidationError as exc:
        errors.extend(exc.errors)
        return None


def _validate_multi_text_field(
    name: str, value: object, errors: list[str], warnings: list[str], sep: str = "; "
) -> Optional[str]:
    """文本字段但允许 list（``; `` 连接后入库，如 validation_method）。"""

    if isinstance(value, (list, tuple)):
        items = [str(item).strip() for item in value if str(item).strip()]
        value = sep.join(items)
    return _validate_text_field(name, value, errors, warnings)


# ---------------------------------------------------------------------------
# 入参校验：新增
# ---------------------------------------------------------------------------
def validate_create_payload(payload: dict) -> NormalizedWrite:
    """校验并归一化"新增 KnownGene"的入参，返回完整 23 列 INSERT 行。

    必填：``gene_id`` / ``gene_name`` / ``reference_genome_id`` / ``gene_species`` /
    ``chrom_pos`` / ``gene_phenotype`` / ``functional_category`` /
    ``research_strategy`` / ``key_result``；且 ``paper_doi`` 与 ``paper_title``
    至少一个非空。
    可选：``protein_family`` / ``validation_method`` / ``cloning_method`` /
    ``cloning_method_description`` / ``function_description`` / ``author`` /
    ``author_mail`` / ``submission_date`` / ``publication_year`` /
    ``publication_years`` / ``paper_title`` / ``paper_doi``（以及派生列
    ``species_primary`` / ``chromosome`` 的显式覆盖）。
    缺省：``author='WheatOmics API'``、``author_mail='shengweima@icloud.com'``、
    ``submission_date=今天``。

    Raises:
        GeneWriteValidationError: 任一字段校验失败（``errors`` 汇总全部问题）。
    """

    if not isinstance(payload, dict):
        raise GeneWriteValidationError(["gene 必须是 JSON object"])
    errors: list[str] = []
    warnings: list[str] = []
    _check_unknown_fields(payload, errors)
    values = {key: payload.get(key) for key in ALLOWED_WRITE_FIELDS if key in payload}

    columns: dict[str, Any] = {}
    # --- 必填文本字段 -------------------------------------------------------
    for name in REQUIRED_WRITE_FIELDS:
        if name in ("functional_category", "research_strategy") or name == "key_result":
            continue
        raw = values.get(name)
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            errors.append(f"缺少必填字段 {name}")
        columns[name] = _validate_text_field(name, raw, errors, warnings)

    raw_key_result = values.get("key_result")
    if raw_key_result is None or (isinstance(raw_key_result, str) and not raw_key_result.strip()):
        errors.append("缺少必填字段 key_result")
    columns["key_result"] = _validate_text_field("key_result", raw_key_result, errors, warnings)

    # --- 受控枚举（必填：缺省也算错误） -------------------------------------
    functional_category = _validate_enum(
        "functional_category",
        _validate_text_field("functional_category", values.get("functional_category"), errors, warnings),
        FUNCTIONAL_CATEGORIES,
        errors,
    )
    if functional_category is None and not any("functional_category" in error for error in errors):
        errors.append("缺少必填字段 functional_category")
    columns["functional_category"] = functional_category

    research_strategy = _validate_enum(
        "research_strategy",
        _validate_text_field("research_strategy", values.get("research_strategy"), errors, warnings),
        RESEARCH_STRATEGIES,
        errors,
    )
    if research_strategy is None and not any("research_strategy" in error for error in errors):
        errors.append("缺少必填字段 research_strategy")
    columns["research_strategy"] = research_strategy

    # --- 可选文本字段 -------------------------------------------------------
    for name in (
        "protein_family",
        "cloning_method",
        "cloning_method_description",
        "function_description",
    ):
        columns[name] = _validate_text_field(name, values.get(name), errors, warnings)
    columns["validation_method"] = _validate_multi_text_field(
        "validation_method", values.get("validation_method"), errors, warnings
    )

    # --- 多值题名/DOI --------------------------------------------------------
    columns["paper_title"] = _validate_multi_field("paper_title", values.get("paper_title"), errors, warnings)
    columns["paper_doi"] = _validate_multi_field("paper_doi", values.get("paper_doi"), errors, warnings)
    if not columns["paper_title"] and not columns["paper_doi"]:
        errors.append("paper_doi 与 paper_title 至少提供一个（都为空时无法关联文献）")
    if columns["paper_doi"]:
        for doi in split_multi_value(columns["paper_doi"]):
            if doi and not _DOI_RE.match(doi):
                warnings.append(f"paper_doi 中 {doi!r} 不符合标准 DOI 形式（10.xxxx/...），已原样保存")

    # --- 年份 ---------------------------------------------------------------
    pub_years_text: Optional[str] = None
    pub_year: Optional[int] = None
    if "publication_years" in values and values.get("publication_years") not in (None, "", []):
        tokens = split_multi_value(values.get("publication_years"))
        years, year_warnings = parse_year_tokens(tokens)
        warnings.extend(year_warnings)
        pub_years_text = join_multi_value(tokens)
        _check_length("publication_years", pub_years_text)
        pub_year = min(years) if years else None
        if "publication_year" in values and values.get("publication_year") not in (None, ""):
            explicit = _validate_year_scalar(values.get("publication_year"))
            if explicit is not None and pub_year is not None and explicit != pub_year:
                warnings.append(
                    f"publication_year={explicit} 与 publication_years 最早年份 {pub_year} 不一致，"
                    f"已按最小值 {pub_year} 写入"
                )
    elif "publication_year" in values and values.get("publication_year") not in (None, ""):
        pub_year = _validate_year_scalar(values.get("publication_year"))
        pub_years_text = str(pub_year) if pub_year is not None else None
    columns["publication_year"] = pub_year
    columns["publication_years"] = pub_years_text

    # --- 派生：species_primary / chromosome --------------------------------
    _fill_derived_columns(columns, values, errors, warnings)

    # --- 作者 / 邮箱 / 日期（缺省值） ---------------------------------------
    author = _validate_text_field("author", values.get("author"), errors, warnings) or DEFAULT_AUTHOR
    author_mail = _validate_text_field("author_mail", values.get("author_mail"), errors, warnings) or DEFAULT_AUTHOR_MAIL
    if not _EMAIL_RE.match(author_mail):
        errors.append(f"author_mail 不是合法邮箱: {author_mail!r}")
    columns["author"] = author
    columns["author_mail"] = author_mail
    submission_date = _coerce_date(values.get("submission_date"))
    columns["submission_date"] = submission_date or date.today()

    # --- gene_id 形状提示（不阻断；读接口 /known/{gene_id} 有更严正则） ------
    gene_id = columns.get("gene_id")
    if gene_id and not _GENE_LIKE_RE.match(gene_id):
        warnings.append(
            f"gene_id {gene_id!r} 含字符集之外的字符，读接口 /api/genes/known/{{gene_id}} 将无法按 gene_id 查询，"
            "但可用 clone_id 访问详情"
        )

    if errors:
        raise GeneWriteValidationError(errors, warnings)
    missing = [name for name in DB_INSERT_COLUMNS if name not in columns]
    if missing:  # pragma: no cover - 防御性断言，正常路径不会触发
        raise GeneWriteValidationError([f"内部错误：INSERT 列缺失 {missing}"], warnings)
    return NormalizedWrite(columns={name: columns[name] for name in DB_INSERT_COLUMNS}, warnings=warnings)


def _fill_derived_columns(
    columns: dict[str, Any],
    values: dict[str, Any],
    errors: list[str],
    warnings: list[str],
) -> None:
    """填 ``species_primary`` / ``chromosome``：显式传入则校验，否则自动派生。"""

    # species_primary
    if values.get("species_primary") not in (None, ""):
        try:
            species = _clean_text("species_primary", values.get("species_primary")) or ""
        except GeneWriteValidationError as exc:
            errors.extend(exc.errors)
            species = ""
        _check_length("species_primary", species or None)
        if species and species not in canonical_species():
            errors.append(
                f"species_primary 必须是 23 个受控学名之一，收到 {species!r}；"
                "不传该字段时服务端会自动从 gene_species 派生"
            )
        columns["species_primary"] = species or None
    else:
        species, species_warnings = derive_species_primary(columns.get("gene_species"))
        warnings.extend(species_warnings)
        columns["species_primary"] = species or None

    # chromosome
    if values.get("chromosome") not in (None, ""):
        try:
            chromosome, chrom_warnings = normalize_chromosome_override(values.get("chromosome"))
            warnings.extend(chrom_warnings)
        except GeneWriteValidationError as exc:
            errors.extend(exc.errors)
            chromosome = ""
        columns["chromosome"] = chromosome or None
    else:
        chromosome, chrom_warnings = derive_chromosome(columns.get("chrom_pos"))
        warnings.extend(chrom_warnings)
        columns["chromosome"] = chromosome or None


# ---------------------------------------------------------------------------
# 入参校验：更新（部分字段）
# ---------------------------------------------------------------------------
def validate_update_payload(payload: dict, before_row: dict) -> NormalizedWrite:
    """校验"更新 KnownGene"的入参，返回**本次要更新的列**（不含未提供的列）。

    规则:
    - 只允许写白名单字段；``clone_id`` / 审计列 / 未知字段 → 422；
    - 必填字段若显式传入则不能为空（否则无法通过读接口/前端）；
    - 源字段变更时重算派生列：``gene_species`` → ``species_primary``、
      ``chrom_pos`` → ``chromosome``、``publication_years``/``publication_year``
      → 年份标量。显式传入派生列时以显式值为准（校验后使用）；
    - 只传 ``publication_year``（不传 ``publication_years``）时只改标量年份，
      保留原多值年份原文（避免误清多篇文献的年份列表）。

    Raises:
        GeneWriteValidationError: 任一字段校验失败。
    """

    if not isinstance(payload, dict):
        raise GeneWriteValidationError(["fields 必须是 JSON object"])
    if not payload:
        raise GeneWriteValidationError(["fields 不能为空（PATCH 至少要传 1 个字段）"])
    errors: list[str] = []
    warnings: list[str] = []
    _check_unknown_fields(payload, errors)
    values = {key: payload.get(key) for key in ALLOWED_WRITE_FIELDS if key in payload}

    columns: dict[str, Any] = {}
    # 文本/多值字段映射（类型规则与新增一致）
    plain_fields = (
        "gene_id",
        "gene_name",
        "reference_genome_id",
        "gene_species",
        "chrom_pos",
        "gene_phenotype",
        "key_result",
        "protein_family",
        "cloning_method",
        "cloning_method_description",
        "function_description",
        "author",
        "author_mail",
    )
    for name in plain_fields:
        if name not in values:
            continue
        raw = values[name]
        text = _validate_text_field(name, raw, errors, warnings)
        if (raw is None or (isinstance(raw, str) and not raw.strip())) and name in REQUIRED_WRITE_FIELDS:
            errors.append(f"必填字段 {name} 不能改为空")
        if (
            name in ("author", "author_mail")
            and (raw is None or (isinstance(raw, str) and not raw.strip()))
        ):
            # 这两列是 DB NOT NULL，不能通过 PATCH 清空。
            errors.append(f"{name} 不能改为空（DB NOT NULL 列）")
        columns[name] = text or None

    if "functional_category" in values:
        columns["functional_category"] = _validate_enum(
            "functional_category",
            _validate_text_field("functional_category", values["functional_category"], errors, warnings),
            FUNCTIONAL_CATEGORIES,
            errors,
        )
    for enum_name, enum_allowed in (
        ("functional_category", FUNCTIONAL_CATEGORIES),
        ("research_strategy", RESEARCH_STRATEGIES),
    ):
        if enum_name not in values:
            continue
        raw_enum = values[enum_name]
        columns[enum_name] = _validate_enum(
            enum_name,
            _validate_text_field(enum_name, raw_enum, errors, warnings),
            enum_allowed,
            errors,
        )
        if raw_enum is None or (isinstance(raw_enum, str) and not raw_enum.strip()):
            errors.append(f"必填字段 {enum_name} 不能改为空")
    if "validation_method" in values:
        columns["validation_method"] = _validate_multi_text_field(
            "validation_method", values["validation_method"], errors, warnings
        )
    if "paper_title" in values:
        columns["paper_title"] = _validate_multi_field("paper_title", values["paper_title"], errors, warnings)
    if "paper_doi" in values:
        columns["paper_doi"] = _validate_multi_field("paper_doi", values["paper_doi"], errors, warnings)
    if "paper_title" in values or "paper_doi" in values:
        merged_title = columns.get("paper_title", before_row.get("paper_title"))
        merged_doi = columns.get("paper_doi", before_row.get("paper_doi"))
        if not merged_title and not merged_doi:
            errors.append("paper_doi 与 paper_title 至少保留一个（不允许同时清空）")

    # --- 年份 ---------------------------------------------------------------
    if "publication_years" in values and values["publication_years"] not in (None, "", []):
        tokens = split_multi_value(values["publication_years"])
        years, year_warnings = parse_year_tokens(tokens)
        warnings.extend(year_warnings)
        years_text = join_multi_value(tokens)
        _check_length("publication_years", years_text)
        columns["publication_years"] = years_text
        columns["publication_year"] = min(years) if years else None
        if "publication_year" in values and values["publication_year"] not in (None, ""):
            explicit = _validate_year_scalar(values["publication_year"])
            if explicit is not None and columns["publication_year"] is not None and explicit != columns["publication_year"]:
                warnings.append(
                    f"publication_year={explicit} 与 publication_years 最早年份 "
                    f"{columns['publication_year']} 不一致，已按最小值写入"
                )
    elif "publication_years" in values:
        # 显式传空 → 清空多值年份（标量同步清空）
        columns["publication_years"] = None
        columns["publication_year"] = None
    elif "publication_year" in values:
        columns["publication_year"] = _validate_year_scalar(values["publication_year"])

    # --- 日期 / 作者邮箱 -----------------------------------------------------
    if "submission_date" in values:
        columns["submission_date"] = _coerce_date(values["submission_date"])
    if "author_mail" in values and columns.get("author_mail"):
        if not _EMAIL_RE.match(str(columns["author_mail"])):
            errors.append(f"author_mail 不是合法邮箱: {columns['author_mail']!r}")

    # --- 派生列重算（源字段变了才重算，未显式提供时） ---------------------
    merged_species_raw = columns.get("gene_species", before_row.get("gene_species"))
    if "species_primary" in values and values["species_primary"] not in (None, ""):
        try:
            species = _clean_text("species_primary", values["species_primary"]) or ""
        except GeneWriteValidationError as exc:
            errors.extend(exc.errors)
            species = ""
        _check_length("species_primary", species or None)
        if species and species not in canonical_species():
            errors.append(
                f"species_primary 必须是 23 个受控学名之一，收到 {species!r}"
            )
        columns["species_primary"] = species or None
    elif "gene_species" in columns:
        species, species_warnings = derive_species_primary(merged_species_raw)
        warnings.extend(f"派生 species_primary: {w}" for w in species_warnings)
        columns["species_primary"] = species or None

    merged_chrom_pos = columns.get("chrom_pos", before_row.get("chrom_pos"))
    if "chromosome" in values and values["chromosome"] not in (None, ""):
        try:
            chromosome, chrom_warnings = normalize_chromosome_override(values["chromosome"])
            warnings.extend(chrom_warnings)
        except GeneWriteValidationError as exc:
            errors.extend(exc.errors)
            chromosome = ""
        columns["chromosome"] = chromosome or None
    elif "chrom_pos" in columns:
        chromosome, chrom_warnings = derive_chromosome(merged_chrom_pos)
        warnings.extend(f"派生 chromosome: {w}" for w in chrom_warnings)
        columns["chromosome"] = chromosome or None

    if errors:
        raise GeneWriteValidationError(errors, warnings)
    unknown_columns = set(columns) - DB_WRITE_COLUMNS
    if unknown_columns:  # pragma: no cover - 防御性断言
        raise GeneWriteValidationError([f"内部错误：UPDATE 列不在白名单 {sorted(unknown_columns)}"], warnings)
    return NormalizedWrite(columns=columns, warnings=warnings)


# ---------------------------------------------------------------------------
# 行 / 审计 JSON 序列化
# ---------------------------------------------------------------------------
def to_jsonable_row(row: Optional[dict]) -> Optional[dict]:
    """把 DB 行转成可 JSON 序列化的 dict（date/datetime→ISO 字符串、Decimal→str）。

    审计快照要求"完整行"（含长文本），因此这里**不裁剪任何列**。
    """

    if row is None:
        return None
    payload: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, (datetime, date)):
            payload[key] = value.isoformat()
        elif isinstance(value, Decimal):
            payload[key] = str(value)
        elif isinstance(value, bytes):
            payload[key] = value.decode("utf-8", errors="replace")
        else:
            payload[key] = value
    return payload


def row_to_audit_json(row: Optional[dict]) -> Optional[str]:
    """审计 ``before_json`` / ``after_json`` 的落库字符串（UTF-8，不转义中文）。"""

    if row is None:
        return None
    return json.dumps(to_jsonable_row(row), ensure_ascii=False, default=str)


def changed_columns(before_row: Optional[dict], after_row: Optional[dict]) -> list[str]:
    """对比两行的白名单列，返回发生变化的列名（排序后，便于稳定断言）。"""

    if before_row is None or after_row is None:
        return []
    columns: list[str] = []
    for name in DB_INSERT_COLUMNS:
        if before_row.get(name) != after_row.get(name):
            columns.append(name)
    return sorted(columns)


def _sql_identifier(column: str) -> str:
    """列名只可能来自本模块常量；仍是防御：非白名单列拒绝拼进 SQL。"""

    if column not in DB_WRITE_COLUMNS:
        raise ValueError(f"refusing to build SQL with non-whitelisted column: {column!r}")
    return column


# ---------------------------------------------------------------------------
# 审计写入 / 查询
# ---------------------------------------------------------------------------
def write_audit_entry(
    cursor: Any,
    *,
    action: str,
    clone_id: Optional[int],
    gene_id: Optional[str],
    gene_name: Optional[str],
    changed_fields: list[str] | str = "",
    before_row: Optional[dict] = None,
    after_row: Optional[dict] = None,
    actor: Any = None,
    actor_label: Optional[str] = None,
    client_ip: Optional[str] = None,
    reason: Optional[str] = None,
) -> int:
    """写一条 ``known_gene_change_log`` 审计；返回 audit_id（``lastrowid``）。

    ``actor`` 可以是 ``known_gene_auth.AuthContext``（有 ``key_id``/``label``）；
    CLI 维护操作没有 key，用 ``actor_label='cli:known_gene_admin'`` 标识来源。
    **必须与主表写操作使用同一个 cursor / 同一事务**，由调用方保证。
    """

    if action not in KNOWN_GENE_ACTIONS:
        raise ValueError(f"unknown audit action: {action!r}")
    if isinstance(changed_fields, (list, tuple)):
        changed_text = ",".join(changed_fields)
    else:
        changed_text = str(changed_fields or "")
    actor_key_id = int(getattr(actor, "key_id", 0) or 0) or None
    actor_label_text = actor_label or getattr(actor, "label", None) or None
    cursor.execute(
        "INSERT INTO known_gene_change_log "
        "(action, clone_id, gene_id, gene_name, changed_fields, before_json, after_json, "
        " actor_key_id, actor_label, client_ip, reason) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (
            action,
            clone_id,
            gene_id,
            gene_name,
            changed_text,
            row_to_audit_json(before_row),
            row_to_audit_json(after_row),
            actor_key_id,
            actor_label_text,
            client_ip,
            reason,
        ),
    )
    try:
        return int(cursor.lastrowid)
    except (TypeError, ValueError):  # pragma: no cover - 防御性
        return 0


@dataclass
class GeneWriteResult:
    """一次 create/update 的事务内结果。"""

    clone_id: int
    audit_id: Optional[int]
    changed_fields: list[str]
    row: dict
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 查询辅助（事务内）
# ---------------------------------------------------------------------------
def fetch_row(cursor: Any, clone_id: int) -> Optional[dict]:
    """按 clone_id 读完整行（24 列）。"""

    cursor.execute("SELECT * FROM cloned_gene_tbl WHERE clone_id = %s LIMIT 1", (int(clone_id),))
    return cursor.fetchone()


def fetch_row_for_update(cursor: Any, clone_id: int) -> Optional[dict]:
    """按 clone_id 读完整行并加行锁（``SELECT ... FOR UPDATE``）。"""

    cursor.execute(
        "SELECT * FROM cloned_gene_tbl WHERE clone_id = %s FOR UPDATE",
        (int(clone_id),),
    )
    return cursor.fetchone()


def find_duplicate(
    cursor: Any,
    gene_id: str,
    gene_name: str,
    *,
    exclude_clone_id: Optional[int] = None,
) -> Optional[dict]:
    """按自然键 (gene_id, gene_name) 查重（返回 clone_id/gene_id/gene_name 或 None）。"""

    sql = "SELECT clone_id, gene_id, gene_name FROM cloned_gene_tbl WHERE gene_id = %s AND gene_name = %s"
    params: list[Any] = [gene_id, gene_name]
    if exclude_clone_id is not None:
        sql += " AND clone_id <> %s"
        params.append(int(exclude_clone_id))
    cursor.execute(sql + " LIMIT 1", tuple(params))
    return cursor.fetchone()


def load_existing_key_map(cursor: Any, keys: list[tuple[str, str]]) -> dict[tuple[str, str], int]:
    """批量加载已有自然键 → clone_id 映射（IN 查询分块，避免 500 行逐条查）。"""

    result: dict[tuple[str, str], int] = {}
    gene_ids = sorted({gene_id for gene_id, _ in keys if gene_id})
    chunk_size = 200
    for start in range(0, len(gene_ids), chunk_size):
        chunk = gene_ids[start : start + chunk_size]
        placeholders = ", ".join(["%s"] * len(chunk))
        cursor.execute(
            f"SELECT clone_id, gene_id, gene_name FROM cloned_gene_tbl WHERE gene_id IN ({placeholders})",
            tuple(chunk),
        )
        for row in cursor.fetchall() or []:
            result[(row["gene_id"], row["gene_name"])] = int(row["clone_id"])
    return result


# ---------------------------------------------------------------------------
# 事务函数：新增 / 更新 / 批量 / 删除
# ---------------------------------------------------------------------------
def create_known_gene(
    cursor: Any,
    row: dict,
    *,
    actor: Any = None,
    client_ip: Optional[str] = None,
    reason: Optional[str] = None,
    action: str = "create",
) -> GeneWriteResult:
    """在事务内新增一行 KnownGene + 一条 create/bulk_create 审计。

    - 先做 (gene_id, gene_name) 查重（``DuplicateGeneError`` → 路由 409）；
    - INSERT 不写 clone_id（自增），``cursor.lastrowid`` 即新 clone_id；
    - 审计 ``after_json`` = 重新 SELECT 出来的完整行（类型已由 MySQL 归一）；
    - **不 commit**：由调用方的 ``mysql_cursor`` 统一提交，保证审计同事务。
    """

    gene_id = str(row.get("gene_id") or "")
    gene_name = str(row.get("gene_name") or "")
    duplicate = find_duplicate(cursor, gene_id, gene_name)
    if duplicate:
        raise DuplicateGeneError(gene_id, gene_name, int(duplicate["clone_id"]))

    values = [row.get(column) for column in DB_INSERT_COLUMNS]
    placeholders = ", ".join(["%s"] * len(DB_INSERT_COLUMNS))
    cursor.execute(
        f"INSERT INTO cloned_gene_tbl ({', '.join(DB_INSERT_COLUMNS)}) VALUES ({placeholders})",
        tuple(values),
    )
    clone_id = int(cursor.lastrowid)
    after_row = fetch_row(cursor, clone_id)
    audit_id = write_audit_entry(
        cursor,
        action=action,
        clone_id=clone_id,
        gene_id=gene_id,
        gene_name=gene_name,
        changed_fields="",
        before_row=None,
        after_row=after_row,
        actor=actor,
        client_ip=client_ip,
        reason=reason,
    )
    return GeneWriteResult(clone_id=clone_id, audit_id=audit_id, changed_fields=[], row=after_row or {})


def update_known_gene(
    cursor: Any,
    clone_id: int,
    columns: dict[str, Any],
    *,
    actor: Any = None,
    client_ip: Optional[str] = None,
    reason: Optional[str] = None,
    action: str = "update",
    allow_noop: bool = False,
) -> GeneWriteResult:
    """在事务内更新一行 KnownGene + 一条 update/bulk_update 审计。

    - ``SELECT ... FOR UPDATE`` 锁行；不存在 → ``ResourceNotFound``（路由 404）；
    - 只 UPDATE 传入的白名单列（参数化）；
    - 无实际变化时：``allow_noop=False`` 返回 changed_fields=[] 且不写审计
      （路由据此提示"无字段变化"）；``allow_noop=True``（batch upsert 用）同样
      不写审计但正常返回；
    - 审计 ``before_json`` / ``after_json`` 均为完整行，``changed_fields`` 为
      逗号分隔的真实变化列。
    """

    before_row = fetch_row_for_update(cursor, clone_id)
    if not before_row:
        raise ResourceNotFound(f"KnownGene 不存在: clone_id={clone_id}")
    unknown = set(columns) - DB_WRITE_COLUMNS
    if unknown:
        raise ValueError(f"refusing to update non-whitelisted columns: {sorted(unknown)}")

    # 只写"真正有变化"的列：避免整行重写，也让 changed_fields 与 UPDATE 列一致。
    effective = {
        column: value
        for column, value in columns.items()
        if before_row.get(column) != value
    }
    if not effective:
        return GeneWriteResult(
            clone_id=int(clone_id),
            audit_id=None,
            changed_fields=[],
            row=before_row,
            warnings=["无字段变化，未执行 UPDATE，也未写审计"],
        )

    assignments = ", ".join(f"{_sql_identifier(column)} = %s" for column in effective)
    params = [effective[column] for column in effective] + [int(clone_id)]
    cursor.execute(
        f"UPDATE cloned_gene_tbl SET {assignments} WHERE clone_id = %s",
        tuple(params),
    )
    after_row = fetch_row(cursor, clone_id) or {**before_row, **effective}
    actual_changed = changed_columns(before_row, after_row)
    audit_id = write_audit_entry(
        cursor,
        action=action,
        clone_id=int(clone_id),
        gene_id=after_row.get("gene_id"),
        gene_name=after_row.get("gene_name"),
        changed_fields=actual_changed,
        before_row=before_row,
        after_row=after_row,
        actor=actor,
        client_ip=client_ip,
        reason=reason,
    )
    return GeneWriteResult(
        clone_id=int(clone_id),
        audit_id=audit_id,
        changed_fields=actual_changed,
        row=after_row,
    )


def delete_known_gene(
    cursor: Any,
    clone_id: int,
    *,
    confirm_gene_id: str,
    reason: str,
    actor_label: str = "cli:known_gene_admin",
    client_ip: Optional[str] = None,
) -> dict[str, Any]:
    """在事务内删除一行 + 一条 ``delete`` 审计（仅供维护 CLI，v1 API 不暴露）。

    安全约束：``--confirm`` 必须与库里的 ``gene_id`` **完全一致**（防止误删
    clone_id），不匹配 → ``GeneWriteValidationError``。
    """

    before_row = fetch_row_for_update(cursor, clone_id)
    if not before_row:
        raise ResourceNotFound(f"KnownGene 不存在: clone_id={clone_id}")
    actual_gene_id = str(before_row.get("gene_id") or "")
    if not confirm_gene_id or actual_gene_id != confirm_gene_id:
        raise GeneWriteValidationError(
            [
                f"--confirm 不匹配：clone_id={clone_id} 的 gene_id 是 {actual_gene_id!r}，"
                f"而 --confirm 传的是 {confirm_gene_id!r}；请核对后重试"
            ]
        )
    audit_id = write_audit_entry(
        cursor,
        action="delete",
        clone_id=int(clone_id),
        gene_id=actual_gene_id,
        gene_name=before_row.get("gene_name"),
        changed_fields="",
        before_row=before_row,
        after_row=None,
        actor=None,
        actor_label=actor_label,
        client_ip=client_ip,
        reason=reason,
    )
    cursor.execute("DELETE FROM cloned_gene_tbl WHERE clone_id = %s", (int(clone_id),))
    return {
        "clone_id": int(clone_id),
        "gene_id": actual_gene_id,
        "gene_name": before_row.get("gene_name"),
        "audit_id": audit_id,
    }


# ---------------------------------------------------------------------------
# 批量：校验（纯函数部分）
# ---------------------------------------------------------------------------
@dataclass
class PreparedBulkRow:
    """批量一行：序号（1-based）+ 归一化结果或错误。"""

    index: int
    payload: dict
    normalized: Optional[NormalizedWrite] = None
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors and self.normalized is not None

    @property
    def key(self) -> tuple[str, str]:
        if not self.normalized:
            return ("", "")
        return (
            str(self.normalized.columns.get("gene_id") or ""),
            str(self.normalized.columns.get("gene_name") or ""),
        )


def prepare_bulk_rows(rows: list[dict]) -> list[PreparedBulkRow]:
    """逐行校验批量入参（纯函数；不查库）。

    - 每行按"完整新增记录"校验（upsert 也要求完整行，见 WRITE_API.md）；
    - 批内 (gene_id, gene_name) 重复：后出现的行为错误；
    - 返回每行 ``PreparedBulkRow``，错误不抛出，由批量入口决定 422 或 dry-run 汇总。
    """

    prepared: list[PreparedBulkRow] = []
    seen: dict[tuple[str, str], int] = {}
    for offset, payload in enumerate(rows):
        index = offset + 1
        item = PreparedBulkRow(index=index, payload=payload)
        if not isinstance(payload, dict):
            item.errors.append(f"第 {index} 行必须是 JSON object")
            prepared.append(item)
            continue
        try:
            item.normalized = validate_create_payload(payload)
        except GeneWriteValidationError as exc:
            item.errors.extend(exc.errors)
            item.errors.extend(f"提示: {warning}" for warning in exc.warnings)
            prepared.append(item)
            continue
        key = item.key
        if key in seen:
            item.errors.append(
                f"批量内重复：第 {index} 行与第 {seen[key]} 行的 (gene_id, gene_name) 相同: {key}"
            )
        else:
            seen[key] = index
        prepared.append(item)
    return prepared


# ---------------------------------------------------------------------------
# 批量：事务内执行
# ---------------------------------------------------------------------------
def run_bulk(
    cursor: Any,
    prepared: list[PreparedBulkRow],
    *,
    mode: str,
    dry_run: bool,
    actor: Any = None,
    client_ip: Optional[str] = None,
    reason: Optional[str] = None,
) -> dict[str, Any]:
    """在同一事务内执行批量 upsert / insert_only（或 dry-run 预演）。

    - ``insert_only``：任何已存在的自然键 / 校验错误 → 整批拒绝（422，不写库）；
    - ``upsert``：按 (gene_id, gene_name) 匹配 → 更新（``bulk_update``），
      否则插入（``bulk_create``）；字段内容完全相同的行计为 updated 但不写审计；
    - dry-run：只返回每行 ``would_create`` / ``would_update`` / ``error``；
    - **不 commit**：由调用方 ``mysql_cursor`` 统一提交（审计同事务）。

    返回::

        {"created": 0, "updated": 0, "errors": 0, "dry_run": bool,
         "results": [{"row": 1, "status": "created", "clone_id": 527,
                      "audit_id": 12, "changed_fields": [...]}, ...],
         "audit_ids": [12, 13]}
    """

    if mode not in BULK_MODES:
        raise GeneWriteValidationError([f"mode 取值非法: {mode!r}；允许值: insert_only / upsert"])

    errors_from_validation = [item for item in prepared if not item.ok]
    if errors_from_validation and not dry_run:
        detail: list[str] = []
        for item in errors_from_validation:
            detail.extend(f"第 {item.index} 行: {error}" for error in item.errors)
        raise GeneWriteValidationError(detail)

    existing = load_existing_key_map(cursor, [item.key for item in prepared if item.ok])

    # insert_only 的所有冲突先一次性收集：非 dry-run 时在**任何写之前**拒绝整批
    # （路由的 mysql_cursor 也会兜底 rollback，这里是更清晰的报错路径）。
    if not dry_run and mode == "insert_only":
        conflicts: list[str] = []
        for item in prepared:
            if item.ok and item.key in existing:
                conflicts.append(
                    f"第 {item.index} 行 (gene_id={item.key[0]!r}, gene_name={item.key[1]!r}) "
                    f"已存在 clone_id={existing[item.key]}，insert_only 模式拒绝覆盖"
                )
        if conflicts:
            raise GeneWriteValidationError(conflicts)

    results: list[dict[str, Any]] = []
    audit_ids: list[int] = []
    created = 0
    updated = 0
    error_count = 0

    for item in prepared:
        if not item.ok:
            error_count += 1
            results.append(
                {
                    "row": item.index,
                    "status": "error",
                    "errors": item.errors,
                    "gene_id": item.payload.get("gene_id") if isinstance(item.payload, dict) else None,
                    "gene_name": item.payload.get("gene_name") if isinstance(item.payload, dict) else None,
                }
            )
            continue
        assert item.normalized is not None
        columns = item.normalized.columns
        key = item.key
        existing_clone_id = existing.get(key)

        if mode == "insert_only" and existing_clone_id is not None:
            error_count += 1
            message = (
                f"第 {item.index} 行 (gene_id={key[0]!r}, gene_name={key[1]!r}) 已存在 "
                f"(clone_id={existing_clone_id})，insert_only 模式拒绝覆盖"
            )
            results.append({"row": item.index, "status": "error", "errors": [message], "clone_id": existing_clone_id})
            continue

        if dry_run:
            if existing_clone_id is not None:
                updated += 1
                results.append(
                    {
                        "row": item.index,
                        "status": "would_update",
                        "clone_id": existing_clone_id,
                        "changed_fields": [],
                        "dry_run": True,
                    }
                )
            else:
                created += 1
                results.append(
                    {
                        "row": item.index,
                        "status": "would_create",
                        "clone_id": None,
                        "dry_run": True,
                    }
                )
            continue

        if existing_clone_id is not None:
            write_result = update_known_gene(
                cursor,
                existing_clone_id,
                columns,
                actor=actor,
                client_ip=client_ip,
                reason=reason,
                action="bulk_update",
                allow_noop=True,
            )
            updated += 1
            if write_result.audit_id is not None:
                audit_ids.append(write_result.audit_id)
            results.append(
                {
                    "row": item.index,
                    "status": "updated",
                    "clone_id": write_result.clone_id,
                    "audit_id": write_result.audit_id,
                    "changed_fields": write_result.changed_fields,
                }
            )
        else:
            write_result = create_known_gene(
                cursor,
                columns,
                actor=actor,
                client_ip=client_ip,
                reason=reason,
                action="bulk_create",
            )
            created += 1
            if write_result.audit_id is not None:
                audit_ids.append(write_result.audit_id)
            results.append(
                {
                    "row": item.index,
                    "status": "created",
                    "clone_id": write_result.clone_id,
                    "audit_id": write_result.audit_id,
                }
            )

    return {
        "created": created,
        "updated": updated,
        "errors": error_count,
        "dry_run": dry_run,
        "results": results,
        "audit_ids": audit_ids,
    }


# ---------------------------------------------------------------------------
# 审计查询（GET /changes）
# ---------------------------------------------------------------------------
def parse_since(value: object) -> datetime:
    """解析 ``since`` 查询参数（ISO 日期或日期时间）。非法 → GeneWriteValidationError。"""

    text = str(value or "").strip()
    if not text:
        raise GeneWriteValidationError(["since 不能为空"])
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        pass
    else:
        # MySQL DATETIME 是 naive 本地时间：带时区的入参先转服务器本地时区再去掉 tzinfo。
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone().replace(tzinfo=None)
        return parsed
    try:
        return datetime.combine(date.fromisoformat(text), datetime.min.time())
    except ValueError as exc:
        raise GeneWriteValidationError(
            [f"since 取值非法: {value!r}（支持 'YYYY-MM-DD' 或 ISO 8601 日期时间）"]
        ) from exc


def list_change_log(
    cursor: Any,
    *,
    clone_id: Optional[int] = None,
    action: Optional[str] = None,
    since: Optional[object] = None,
    limit: int = 50,
    offset: int = 0,
    include_snapshot: bool = False,
) -> dict[str, Any]:
    """查询审计日志（``GET /changes``）；``total`` 为过滤后的总条数。

    ``before_json`` / ``after_json`` 默认不返回（快照含长文本，容易把列表撑到
    数 MB），``include_snapshot=True`` 时才返回解析后的 dict。
    """

    if action is not None and action not in KNOWN_GENE_ACTIONS:
        raise GeneWriteValidationError(
            [f"action 取值非法: {action!r}；允许值: " + " / ".join(KNOWN_GENE_ACTIONS)]
        )
    limit = int(limit)
    offset = int(offset)
    if limit < 1 or limit > 500:
        raise GeneWriteValidationError([f"limit 取值范围 1–500，收到 {limit}"])
    if offset < 0:
        raise GeneWriteValidationError([f"offset 不能为负数: {offset}"])

    where_sql = " WHERE 1=1"
    params: list[Any] = []
    if clone_id is not None:
        where_sql += " AND clone_id = %s"
        params.append(int(clone_id))
    if action is not None:
        where_sql += " AND action = %s"
        params.append(action)
    since_dt: Optional[datetime] = None
    if since is not None and str(since).strip():
        since_dt = parse_since(since)
        where_sql += " AND created_at >= %s"
        params.append(since_dt)

    cursor.execute("SELECT COUNT(*) AS total FROM known_gene_change_log" + where_sql, tuple(params))
    total_row = cursor.fetchone() or {}
    total = int(total_row.get("total") or 0)

    select_columns = (
        "id, action, clone_id, gene_id, gene_name, changed_fields, "
        "actor_key_id, actor_label, client_ip, reason, created_at"
    )
    if include_snapshot:
        select_columns += ", before_json, after_json"
    cursor.execute(
        f"SELECT {select_columns} FROM known_gene_change_log"
        + where_sql
        + " ORDER BY id DESC LIMIT %s OFFSET %s",
        tuple(params + [limit, offset]),
    )
    rows = cursor.fetchall() or []

    records: list[dict[str, Any]] = []
    for row in rows:
        changed = row.get("changed_fields")
        record: dict[str, Any] = {
            "id": int(row["id"]),
            "action": row.get("action"),
            "clone_id": int(row["clone_id"]) if row.get("clone_id") is not None else None,
            "gene_id": row.get("gene_id"),
            "gene_name": row.get("gene_name"),
            "changed_fields": [part for part in str(changed).split(",") if part] if changed else [],
            "actor_key_id": row.get("actor_key_id"),
            "actor_label": row.get("actor_label"),
            "client_ip": row.get("client_ip"),
            "reason": row.get("reason"),
            "created_at": (
                row["created_at"].isoformat() if isinstance(row.get("created_at"), (datetime, date)) else row.get("created_at")
            ),
        }
        if include_snapshot:
            record["before"] = _load_snapshot(row.get("before_json"))
            record["after"] = _load_snapshot(row.get("after_json"))
        records.append(record)

    return {"total": total, "limit": limit, "offset": offset, "records": records}


def _load_snapshot(raw: object) -> Optional[dict]:
    """审计快照字符串 → dict（容忍历史坏数据，解析失败返回 None）。"""

    if not raw:
        return None
    try:
        parsed = json.loads(str(raw))
    except (TypeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None
