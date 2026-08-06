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
                "SELECT table_name, display_name, labels, citation, group_name, subgroup FROM project_meta"
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
                    "subgroup": row.get("subgroup") or "",
                })
    except Exception:
        pass
    return projects


def list_projects() -> dict:
    """Build project list and groups from project_meta table.

    Returns a 3-level tree: group_name → subgroup → display_name / table_name.
    """

    all_projects = _fetch_all_projects()

    # Build tree: {group_name: {subgroup: [project_dict, ...]}}
    tree: dict[str, dict[str, list[dict]]] = {}
    for p in all_projects:
        gname = p["group"]
        # Normalise: empty subgroup maps to ""; strip whitespace
        sgname = (p.get("subgroup") or "").strip()
        tree.setdefault(gname, {}).setdefault(sgname, []).append({
            "id": p["id"],
            "description": p["description"],
            "categories": p["categories"],
            "citation": p["citation"],
        })

    # Build ordered list of groups
    group_order = [
        "wheat developmental tissues",
        "wheat biotic stresses",
        "wheat abiotic stresses",
        "wheat population",
        "Others",
    ]
    groups_out: list[dict] = []
    seen: set[str] = set()

    for gname in group_order:
        if gname in tree and gname not in seen:
            seen.add(gname)
            subgroups = []
            for sgname, projects in tree[gname].items():
                # Sort projects within each subgroup by description
                projects.sort(key=lambda p: p["description"])
                subgroups.append({
                    "name": sgname,
                    "projects": projects,
                })
            # Sort subgroups by name
            subgroups.sort(key=lambda s: s["name"])
            groups_out.append({
                "name": gname,
                "subgroups": subgroups,
            })

    # Remaining groups not in the fixed order
    for gname in sorted(tree):
        if gname not in seen:
            subgroups = []
            for sgname, projects in tree[gname].items():
                projects.sort(key=lambda p: p["description"])
                subgroups.append({"name": sgname, "projects": projects})
            subgroups.sort(key=lambda s: s["name"])
            groups_out.append({"name": gname, "subgroups": subgroups})

    # Flat project list for backwards compatibility
    flat = [
        {"id": p["id"], "description": p["description"],
         "categories": p["categories"], "citation": p["citation"],
         "group": p["group"], "subgroup": p.get("subgroup", "")}
        for p in all_projects
    ]

    return {"projects": flat, "groups": groups_out}


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
