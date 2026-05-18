"""State-machine table planning skill for LDA queries."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Tuple

from LDA.skills.jsonSchemaReaderSkill import json_schema_reader_skill


INVENTORY_MONITOR_TERMS = [
    "库存监控", "仓库监控", "库存预警", "库存预测", "未来库存",
    "断货", "缺货", "补货", "补货倒计时", "可售天数", "安全库存",
    "在途", "批次", "全部仓库", "FBA库存", "海外仓库存", "本地仓库存",
]

INVENTORY_FORECAST_TERMS = [
    "未来", "预测", "预警", "连续", "forecast", "ending_inventory",
    "预计到货", "预计销量", "期末库存", "期初库存",
]

INVENTORY_HISTORY_TERMS = ["历史", "昨日", "昨天", "近", "最近", "日期", "趋势"]

INVENTORY_MONITOR_TABLE = "ads_lingxing_all_warehouse_new"
INVENTORY_MONITOR_HISTORY_TABLE = "ads_lingxing_all_warehouse_new_sh"
INVENTORY_FORECAST_TABLE = "dim_inventory_forecast2"


@dataclass
class TablePlanState:
    status: str = "schema_read"
    attempts: int = 0
    selected_tables: List[str] = field(default_factory=list)
    audit_notes: List[str] = field(default_factory=list)


@dataclass
class TablePlanResult:
    status: str
    ordered_tables: List[Tuple[str, float]]
    selected_tables: List[str]
    attempts: int
    audit_notes: List[str]


class TableQueryPlanningSkill:
    """Plan query tables with bounded schema reads and up to three audit rounds."""

    custom_words = [
        "库存监控", "库存预警", "库存预测", "断货", "缺货",
        "补货倒计时", "可售天数", "全部仓库",
    ]

    def plan_tables(
        self, query: str, ranked_tables: Sequence[Tuple[str, float]]
    ) -> TablePlanResult:
        state = TablePlanState()
        ordered = list(ranked_tables)

        for attempt in range(1, 4):
            state.attempts = attempt
            state.status = "audit"
            ordered = self._apply_inventory_monitor_plan(query, ordered)
            selected = [table for table, _ in ordered[:5]]

            ok, note = self._audit(query, selected)
            state.audit_notes.append(note)
            state.selected_tables = selected
            if ok:
                state.status = "found"
                break

            state.status = "deepen_schema"
            ordered = self._deepen_with_schema_search(query, ordered)
        else:
            state.status = "failed"

        return TablePlanResult(
            status=state.status,
            ordered_tables=ordered,
            selected_tables=state.selected_tables,
            attempts=state.attempts,
            audit_notes=state.audit_notes,
        )

    @staticmethod
    def is_inventory_monitor_query(query: str) -> bool:
        return any(term in query for term in INVENTORY_MONITOR_TERMS)

    def _apply_inventory_monitor_plan(
        self, query: str, ranked_tables: Sequence[Tuple[str, float]]
    ) -> List[Tuple[str, float]]:
        scores: Dict[str, float] = dict(ranked_tables)
        if not self.is_inventory_monitor_query(query):
            return list(ranked_tables)

        def boost(table_name: str, score: float) -> None:
            if json_schema_reader_skill.table_exists(table_name):
                scores[table_name] = max(scores.get(table_name, 0.0), score)

        if any(term in query for term in INVENTORY_FORECAST_TERMS):
            boost(INVENTORY_FORECAST_TABLE, 200.0)
            boost(INVENTORY_MONITOR_TABLE, 95.0)
            boost(INVENTORY_MONITOR_HISTORY_TABLE, 90.0)
        elif any(term in query for term in INVENTORY_HISTORY_TERMS):
            boost(INVENTORY_MONITOR_HISTORY_TABLE, 120.0)
            boost(INVENTORY_MONITOR_TABLE, 110.0)
            boost(INVENTORY_FORECAST_TABLE, 80.0)
        else:
            boost(INVENTORY_MONITOR_TABLE, 120.0)
            boost(INVENTORY_MONITOR_HISTORY_TABLE, 100.0)
            boost(INVENTORY_FORECAST_TABLE, 80.0)

        return sorted(scores.items(), key=lambda x: -x[1])

    def _audit(self, query: str, selected_tables: Sequence[str]) -> tuple[bool, str]:
        if not self.is_inventory_monitor_query(query):
            return True, "通用查询：使用关键词召回结果。"

        if any(term in query for term in INVENTORY_FORECAST_TERMS):
            expected = INVENTORY_FORECAST_TABLE
            intent = "未来库存预测/预警"
        elif any(term in query for term in INVENTORY_HISTORY_TERMS):
            expected = INVENTORY_MONITOR_HISTORY_TABLE
            intent = "历史库存监控快照"
        else:
            expected = INVENTORY_MONITOR_TABLE
            intent = "当前库存监控底表"

        if expected in selected_tables[:3]:
            return True, f"{intent} 已命中 {expected}。"
        return False, f"{intent} 未命中前三候选，需要继续读取 schema。"

    @staticmethod
    def _query_terms(query: str) -> List[str]:
        terms = [t for t in INVENTORY_MONITOR_TERMS + INVENTORY_FORECAST_TERMS if t in query]
        return terms or [query]

    def _deepen_with_schema_search(
        self, query: str, ranked_tables: Sequence[Tuple[str, float]]
    ) -> List[Tuple[str, float]]:
        scores: Dict[str, float] = dict(ranked_tables)
        profiles = json_schema_reader_skill.search_tables(self._query_terms(query), limit=20)
        for idx, profile in enumerate(profiles):
            scores[profile.table] = max(scores.get(profile.table, 0.0), 60.0 - idx)
        return sorted(scores.items(), key=lambda x: -x[1])


table_query_planning_skill = TableQueryPlanningSkill()
