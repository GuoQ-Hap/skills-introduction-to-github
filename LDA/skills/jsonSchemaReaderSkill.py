"""Schema JSON reading skill for LDA.

The schema files under LDA/data are large, so this skill exposes small,
task-oriented slices instead of passing the whole JSON to an LLM.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

from LDA.service.schemaService import schema_service


@dataclass
class TableProfile:
    table: str
    layer: str
    description: str
    column_count: int
    columns: List[Dict[str, Any]]


class JsonSchemaReaderSkill:
    """Read fixed table schemas from schema_index.json in bounded chunks."""

    def table_exists(self, table_name: str) -> bool:
        return table_name in schema_service.tables

    def get_table_profile(
        self,
        table_name: str,
        *,
        matched_terms: Optional[Iterable[str]] = None,
        max_columns: int = 80,
    ) -> Optional[TableProfile]:
        info = schema_service.tables.get(table_name)
        if not info:
            return None

        columns = list(info.get("columns", []))
        terms = [str(t).lower() for t in (matched_terms or []) if str(t).strip()]
        if terms:
            matched = []
            rest = []
            for col in columns:
                haystack = f"{col.get('name', '')} {col.get('description_cn', '')}".lower()
                (matched if any(t in haystack for t in terms) else rest).append(col)
            columns = matched + rest

        return TableProfile(
            table=table_name,
            layer=info.get("layer", ""),
            description=info.get("description_cn", ""),
            column_count=int(info.get("column_count") or len(columns)),
            columns=columns[:max_columns],
        )

    def search_tables(self, keywords: Iterable[str], *, limit: int = 20) -> List[TableProfile]:
        scores: Dict[str, float] = {}
        terms = [str(k).strip().lower() for k in keywords if str(k).strip()]
        for table_name, info in schema_service.tables.items():
            haystack = f"{table_name} {info.get('description_cn', '')}".lower()
            score = 0.0
            for term in terms:
                if term in table_name.lower():
                    score += 3.0
                if term in haystack:
                    score += 2.0
                for col in info.get("columns", []):
                    col_text = f"{col.get('name', '')} {col.get('description_cn', '')}".lower()
                    if term in col_text:
                        score += 0.5
            if score > 0:
                scores[table_name] = score

        ranked = sorted(scores, key=lambda t: -scores[t])[:limit]
        profiles = []
        for table_name in ranked:
            profile = self.get_table_profile(table_name, matched_terms=terms, max_columns=30)
            if profile:
                profiles.append(profile)
        return profiles

    @staticmethod
    def profile_to_schema_context(profile: TableProfile) -> str:
        lines = [
            f"-- {profile.layer} | {profile.description}",
            f"CREATE TABLE `{profile.table}` (",
        ]
        for col in profile.columns:
            line = f"  `{col.get('name')}` {col.get('type')}"
            desc = col.get("description_cn") or ""
            if desc and desc != col.get("name"):
                line += f"  -- {desc}"
            lines.append(line + ",")
        if lines[-1].endswith(","):
            lines[-1] = lines[-1][:-1]
        lines.append(");")
        return "\n".join(lines)


json_schema_reader_skill = JsonSchemaReaderSkill()
