"""Expression project metadata — now reads entirely from project_meta table."""

from __future__ import annotations
import json
from typing import Any

from app.core.config import settings
from app.db.mysql import mysql_cursor


def _fetch_all_projects() -> list[dict[str, Any]]:
    """Fetch all project metadata from project_meta table."""
    projects: list[dict[str, Any]] = []
    try:
        with mysql_cursor(settings.DB_GENE_EXPRESSION) as cursor:
            cursor.execute(
                "SELECT table_name, display_name, labels, citation, group_name FROM project_meta"
            )
            for row in cursor.fetchall():
                labels_raw = row.get("labels")
                if isinstance(labels_raw, str):
                    try:
                        labels_raw = json.loads(labels_raw)
                    except json.JSONDecodeError:
                        labels_raw = []
                projects.append({
                    "id": row["table_name"],
                    "description": row["display_name"],
                    "categories": labels_raw or [],
                    "citation": row.get("citation") or "",
                    "group": row.get("group_name") or "Others",
                })
    except Exception:
        pass
    return projects


def list_projects() -> dict:
    """Build project list and groups from project_meta table."""

    all_projects = _fetch_all_projects()

    # 构建分组结构
    group_order = [
        "wheat developmental tissues",
        "wheat biotic stresses",
        "wheat abiotic stresses",
        "wheat population",
        "Others",
    ]
    groups: list[dict] = []
    seen_groups: dict[str, list[str]] = {}
    for p in all_projects:
        gname = p["group"]
        if gname not in seen_groups:
            seen_groups[gname] = []
        seen_groups[gname].append(p["id"])

    # 按固定顺序输出
    for gname in group_order:
        if gname in seen_groups:
            groups.append({"name": gname, "projects": seen_groups[gname]})

    # 不在固定顺序中的归到最后
    for gname, pids in seen_groups.items():
        if gname not in group_order:
            groups.append({"name": gname, "projects": pids})

    flat = [
        {"id": p["id"], "description": p["description"],
         "categories": p["categories"], "citation": p["citation"]}
        for p in all_projects
    ]

    return {"projects": flat, "groups": groups}


def get_project_labels(project_name: str) -> list[str]:
    """Get labels for a given project from the database."""
    try:
        with mysql_cursor(settings.DB_GENE_EXPRESSION) as cursor:
            cursor.execute(
                "SELECT labels FROM project_meta WHERE table_name = %s", (project_name,)
            )
            row = cursor.fetchone()
            if row:
                labels_raw = row["labels"]
                if isinstance(labels_raw, str):
                    return json.loads(labels_raw) or []
                return labels_raw or []
    except Exception:
        pass
    return []
