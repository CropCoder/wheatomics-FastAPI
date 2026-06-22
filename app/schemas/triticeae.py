"""Schemas for Triticeae Research Filter paper database."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class TriticeaePaper(BaseModel):
    """一篇论文的完整功能基因标注信息
    (functional_gene_annotations LEFT JOIN papers)。"""

    # ===== functional_gene_annotations 表 (f.) — AI/人工标注层 =====
    # 这一层记录的是"这篇论文被 AI 标注为什么"，是核心标注产出

    fga_id: int | None = None
    """标注记录 ID (functional_gene_annotations.id)"""

    pubmedid: str | None = None
    """PubMed 唯一标识符 (f.pubmedid)，用于关联论文表"""

    fga_title: str | None = None
    """标注时的论文标题快照 (f.title)，与 papers.title 可能略有差异"""

    is_functional_gene: bool | None = None
    """AI 判断是否为功能基因 (1=是, 0=否)，核心筛选字段"""

    confidence: float | None = None
    """AI 判断置信度 (0~1)，越高越可信"""

    gene_name: list[str] = Field(default_factory=list)
    """论文涉及的功能基因名称列表，如 ["TaCPK-1", "TaCDPK2"]"""

    gene_type: str | None = None
    """基因类型标签，如 known_positive_by_seed_title (种子正样本)、nlr、rlp 等"""

    trait_label: str | None = None
    """性状标签，如 stripe_rust、heat_tolerance、yield，标注所涉农艺性状"""

    function_summary: str | None = None
    """功能基因判断依据的简要文字说明"""

    evidence_type: str | None = None
    """证据类型，如 seed_title_match (标题匹配)、llm_determined (LLM 判断)"""

    new_tags: str | None = None
    """新标注的标签 (JSON 数组字符串)"""

    llm_reason: str | None = None
    """LLM 判断该论文属于功能基因的详细推理过程 (自然语言)"""

    source_method: str | None = None
    """标注来源方法，如 seed_title_match (种子标题匹配)、llm_review (LLM 重审)"""

    review_status: str | None = None
    """审核状态：auto_pass (自动通过)、pending_review (待人工审核) 等"""

    fga_created_at: str | None = None
    """标注记录创建时间 (f.created_at)，即该论文首次被 AI 标注的时间"""

    fga_updated_at: str | None = None
    """标注记录最后更新时间 (f.updated_at)，即 AI 重新判断或人工修改的时间"""

    fga_disease_gene_tags: str | None = None
    """病害/抗病基因标签 (JSON 字符串)"""

    # ===== papers 表 (p.) — 论文元数据层 =====
    # 这一层记录的是"这篇论文本身的基本信息"，来自 PubMed 导入

    paper_id: int | None = None
    """论文元数据记录 ID (papers.id)"""

    pmid: str | None = None
    """PubMed ID (p.pmid)，与 pubmedid 相同，用于跨表关联"""

    pub_date: str | None = None
    """论文发表时间，如 2024 Jun 或 2024 Jun 15"""

    paper_title: str | None = None
    """PubMed 中的论文完整标题 (p.title)"""

    journal: str | None = None
    """期刊名称，如 3 Biotech、BMC Plant Biol"""

    authors: str | None = None
    """作者列表字符串"""

    abstract: str | None = None
    """论文摘要全文"""

    pubmed_keywords: str | None = None
    """PubMed 自带的关键词列表 (分号分隔)"""

    ai_tags: str | None = None
    """AI 生成的论文标签 (自动打标)，分号或空格分隔"""

    keywords_source: str | None = None
    """关键词来源标记: ai_generated (AI生成)、pubmed (PubMed原生)、mixed (混合)"""

    link: str | None = None
    """PubMed 原文链接"""

    paper_created_at: str | None = None
    """论文元数据首次导入 WheatOmics 的时间 (p.created_at)"""

    functional_gene_flag: str | None = None
    """论文级的功能基因标记 (1/0/空)，与 is_functional_gene 类似但独立标注"""

    functional_gene_tags: str | None = None
    """论文级的功能基因名称标签，如 TaCPK-1 (单/多基因逗号分隔)"""

    functional_gene_source: str | None = None
    """论文级功能基因标注的来源，如 seed_title_match"""

    paper_disease_gene_tags: str | None = None
    """论文级的病害/抗病基因标签 (JSON 字符串)"""

    function_gene_flag: str | None = None
    """[备用] 功能基因标记 (第二套标注体系，暂存新方法标注结果)"""

    function_gene_tags: str | None = None
    """[备用] 功能基因标签 (第二套标注体系，与 function_gene_flag 对应)"""


class TriticeaeSearchResult(BaseModel):
    """分页搜索结果。"""

    total: int = 0
    """匹配的总论文数"""
    limit: int = 20
    """每页返回条数 (默认 20, 上限 200)"""
    offset: int = 0
    """分页偏移量"""
    papers: list[TriticeaePaper] = Field(default_factory=list)
    """当前页的论文列表"""
