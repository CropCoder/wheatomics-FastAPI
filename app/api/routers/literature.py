"""Literature routes."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.core.config import settings
from app.core.response import ok
from app.db.mysql import mysql_cursor
from app.schemas.literature import LiteraturePaper, LiteratureTagCount

router = APIRouter(prefix="/literature", tags=["Literature"])


@router.get("/tags")
def popular_tags(limit: int = Query(20, ge=1, le=100)) -> dict:
    """获取热门文献标签。

    功能:
        从 paper_tags 表中统计标签出现频次，按频次降序返回
        最热门的标签列表，支持限制返回数量。

    用法:
        GET /api/literature/tags?limit=<数量>
        - limit: 可选，返回标签数量，默认 20（范围 1-100）

    案例:
        请求:
          curl -X GET "http://localhost:8000/api/literature/tags?limit=10"

        响应:
          {
            "success": true,
            "data": [
              { "tag_name": "drought", "count": 156 },
              { "tag_name": "flowering", "count": 132 },
              { "tag_name": "yield", "count": 98 }
            ]
          }
    """

    with mysql_cursor(settings.DB_LITERATURE) as cursor:
        cursor.execute(
            "SELECT tag_name, COUNT(*) AS c FROM paper_tags GROUP BY tag_name ORDER BY c DESC LIMIT %s",
            (limit,),
        )
        tags = [LiteratureTagCount(tag_name=str(row["tag_name"]), count=int(row["c"])) for row in cursor.fetchall()]
    return ok([tag.model_dump() for tag in tags])


@router.get("/search")
def search_literature(
    search: str | None = Query(default=None),
    tag: str | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
) -> dict:
    """搜索文献。

    功能:
        支持三种查询模式:
        1. 关键词搜索 - 在论文标题和摘要中模糊匹配
        2. 标签搜索 - 按标签精确筛选文献
        3. 最近文献 - 不提供搜索参数时返回最新文献
        每篇文献返回 pmid、标题、期刊、日期、作者、摘要、链接和标签。

    用法:
        GET /api/literature/search?search=<关键词>&tag=<标签>&limit=<数量>
        - search: 可选，关键词（标题和摘要中模糊匹配）
        - tag: 可选，按标签筛选
        - limit: 可选，返回数量，默认 50（范围 1-200）
        （search 和 tag 至少提供一个）

    案例:
        请求 (关键词):
          curl -X GET "http://localhost:8000/api/literature/search?search=drought+tolerance&limit=10"

        请求 (标签):
          curl -X GET "http://localhost:8000/api/literature/search?tag=flowering&limit=10"

        响应:
          {
            "success": true,
            "data": {
              "count": 5,
              "papers": [
                {
                  "pmid": "12345678",
                  "title": "A wheat drought tolerance gene...",
                  "journal": "Nature Genetics",
                  "pub_date": "2024-01-15",
                  "authors": ["Zhang S", "Li W"],
                  "abstract": "Drought is a major...",
                  "link": "https://doi.org/10.1038/...",
                  "tags": ["drought", "GWAS"]
                }
              ]
            }
          }
    """

    with mysql_cursor(settings.DB_LITERATURE) as cursor:
        if search:
            pattern = f"%{search.strip()}%"
            cursor.execute(
                """
                SELECT pmid, title, journal, pub_date, authors, abstract, link
                FROM papers
                WHERE title LIKE %s OR abstract LIKE %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (pattern, pattern, limit),
            )
        elif tag:
            cursor.execute(
                """
                SELECT p.pmid, p.title, p.journal, p.pub_date, p.authors, p.abstract, p.link
                FROM papers p
                JOIN paper_tags t ON p.pmid = t.pmid
                WHERE t.tag_name = %s
                ORDER BY p.created_at DESC
                LIMIT %s
                """,
                (tag.strip(), limit),
            )
        else:
            cursor.execute(
                """
                SELECT pmid, title, journal, pub_date, authors, abstract, link
                FROM papers
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (limit,),
            )
        rows = cursor.fetchall()

        papers: list[LiteraturePaper] = []
        for row in rows:
            cursor.execute("SELECT tag_name FROM paper_tags WHERE pmid = %s", (row["pmid"],))
            tags = [str(item["tag_name"]) for item in cursor.fetchall()]
            authors = [author.strip() for author in str(row["authors"] or "").split(",") if author.strip()]
            papers.append(
                LiteraturePaper(
                    pmid=str(row["pmid"]),
                    title=str(row["title"]),
                    journal=str(row["journal"]) if row["journal"] else None,
                    pub_date=str(row["pub_date"]) if row["pub_date"] else None,
                    authors=authors,
                    abstract=str(row["abstract"]) if row["abstract"] else None,
                    link=str(row["link"]) if row["link"] else None,
                    tags=tags,
                )
            )

    return ok({"count": len(papers), "papers": [paper.model_dump() for paper in papers]})
