"""数据库 Schema 抓取与中文索引构建服务。

整合原 fetch_schema.py 和 build_schema_index.py 的逻辑。
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from LDA.service.base import service_logger
from LDA.service.dbService import db_service

logger = service_logger

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# ===================== 数据仓库分层映射 =====================
LAYER_MAP = {
    "ods": ("ODS-操作数据层", "原始数据存储，直接从业务系统同步"),
    "dwd": ("DWD-明细数据层", "清洗、规范后的明细数据"),
    "dws": ("DWS-汇总数据层", "按主题汇总的宽表数据"),
    "dim": ("DIM-维度表", "维度/字典/配置类数据"),
    "ads": ("ADS-应用数据层", "面向业务应用的最终结果表"),
    "temp": ("TEMP-临时表", "临时计算中间结果"),
    "tmp": ("TMP-临时表", "临时计算中间结果"),
}

# ===================== 业务领域关键字映射 =====================
DOMAIN_KEYWORDS: Dict[str, str] = {
    "sales": "销售", "sale": "销售", "order": "订单",
    "inventory": "库存", "warehouse": "仓库/仓储",
    "fba": "亚马逊FBA物流", "awd": "亚马逊AWD仓储",
    "shipment": "发货/物流", "shipping": "物流运输", "logistics": "物流",
    "purchase": "采购", "procurement": "采购", "product": "产品",
    "profit": "利润", "cost": "成本", "revenue": "营收",
    "return": "退货/退款", "refund": "退款",
    "review": "评论/评价", "advertising": "广告",
    "ad": "广告", "adv": "广告", "campaign": "广告活动",
    "sp": "SP广告(Sponsored Products)", "sb": "SB广告(Sponsored Brands)",
    "listing": "产品链接/Listing", "asin": "ASIN(亚马逊产品编号)",
    "sku": "SKU(库存单位)", "msku": "MSKU(商户SKU)",
    "fnsku": "FNSKU(亚马逊配送网络SKU)",
    "store": "店铺", "seller": "卖家", "brand": "品牌",
    "category": "品类/分类", "price": "价格",
    "stocking": "补货/备货", "forecast": "预测", "estimate": "预估",
    "performance": "业绩/表现", "report": "报告", "monitor": "监控",
    "claim": "索赔", "inbound": "入库", "outbound": "出库",
    "tracking": "追踪", "rate": "汇率/比率", "currency": "币种",
    "calendar": "日历", "date": "日期",
    "staff": "员工/人员", "team": "团队", "department": "部门",
    "leader": "组长/负责人", "account": "账号",
    "market": "市场/站点", "country": "国家", "region": "区域",
    "target": "目标", "completion": "完成率",
    "weekly": "周度", "monthly": "月度", "daily": "日度",
    "first_leg": "头程物流", "last_mile": "尾程物流",
    "local": "本地仓", "overseas": "海外仓",
    "clearance": "清仓", "redundant": "冗余/滞销",
    "stock": "库存", "quantity": "数量", "status": "状态",
    "plan": "计划", "allocation": "分配", "attribution": "归因",
    "activity": "活动", "schedule": "排期", "quality": "质量",
    "supplier": "供应商", "storage_fee": "仓储费", "turnover": "周转",
    "ledger": "台账", "transaction": "交易", "conversion": "转化",
    "health": "健康度", "risk": "风险", "safety": "安全库存",
    "multi_channel": "多渠道", "spu": "SPU(标准产品单位)",
    "parent_asin": "父ASIN", "lingxing": "领星ERP",
    "xiyou": "西邮物流", "feishu": "飞书", "leang": "凌昂(公司)",
}

# ===================== 常见字段名中文映射 =====================
COLUMN_NAME_MAP: Dict[str, str] = {
    "id": "ID主键", "year": "年份", "month": "月份", "day": "日", "date": "日期",
    "dt": "日期分区", "year_month": "年月", "week": "周", "quarter": "季度",
    "create_time": "创建时间", "update_time": "更新时间",
    "created_at": "创建时间", "updated_at": "更新时间",
    "platform": "平台", "store": "店铺", "store_name": "店铺名称",
    "seller_id": "卖家ID", "country": "国家", "country_code": "国家代码",
    "region": "区域", "market": "站点/市场", "marketplace_id": "站点ID",
    "channel": "渠道", "currency": "币种", "exchange_rate": "汇率",
    "msku": "MSKU(商户SKU)", "sku": "SKU(库存单位)",
    "fnsku": "FNSKU(FBA库存SKU)", "asin": "ASIN(产品编号)",
    "parent_asin": "父ASIN", "spu": "SPU(标准产品单位)",
    "brand": "品牌", "category": "品类",
    "category_level1": "一级品类", "category_level2": "二级品类",
    "category_level3": "三级品类",
    "product_name": "产品名称", "sku_name": "SKU名称", "title": "标题",
    "color": "颜色", "colour": "颜色", "size": "尺寸",
    "material": "材质", "weight": "重量",
    "price": "价格", "cost": "成本", "quantity": "数量", "amount": "金额",
    "sales_volume": "销量", "sales_amount": "销售额",
    "order_quantity": "订单数量", "order_amount": "订单金额",
    "revenue": "营收", "profit": "利润", "profit_rate": "利润率",
    "gross_profit": "毛利", "gross_profit_rate": "毛利率",
    "refund_quantity": "退款数量", "refund_amount": "退款金额",
    "return_quantity": "退货数量", "return_rate": "退货率",
    "impressions": "曝光量", "clicks": "点击量",
    "ctr": "点击率(CTR)", "cpc": "单次点击费用(CPC)",
    "acos": "广告销售成本比(ACoS)", "roas": "广告投资回报率(RoAS)",
    "spend": "广告花费", "ad_spend": "广告花费", "ad_sales": "广告销售额",
    "conversion_rate": "转化率", "sessions": "会话数",
    "page_views": "页面浏览量", "buy_box_percentage": "购物车占比",
    "rating": "评分", "review_count": "评论数", "star": "星级",
    "main_account": "主账号", "department": "部门",
    "team_leader": "组长", "sales_person": "销售", "salesman": "销售人员",
    "development_team": "开发组", "product_manager": "产品经理",
    "status": "状态", "remark": "备注", "note": "备注", "description": "描述",
    "is_delete": "是否删除", "is_active": "是否有效",
    "afn_fulfillable_quantity": "亚马逊可售库存",
    "reserved_fc_transfers": "FC转移预留", "reserved_fc_processing": "FC处理预留",
    "afn_inbound_receiving_quantity": "入库接收中数量",
    "afn_inbound_working_quantity": "入库处理中数量",
    "fba_warehouse_quantity": "FBA仓库存",
    "overseas_warehouse_quantity": "海外仓库存",
    "local_warehouse_quantity": "本地仓库存",
    "safety_stock_days": "安全库存天数", "safety_stock_sales": "安全库存销量",
    "production_duration": "生产周期(天)", "order_duration": "下单周期(天)",
    "logistics_model": "物流模式", "new_old_product": "新旧品",
    "product_development_status": "产品开发状态",
    "target_sales_volume": "目标销量",
    "target_sales_amount_usd": "目标销售额(美元)",
    "target_sales_amount_cny_ten_thousand": "目标销售额(万元人民币)",
    "data_dt": "数据日期", "etl_time": "ETL处理时间", "batch_id": "批次ID",
}

# ===================== 业务领域分类规则 =====================
_CATEGORY_RULES: List[Tuple[str, List[str]]] = [
    ("销售分析", ["sales", "sale", "order", "xiaoliang"]),
    ("库存管理", ["inventory", "warehouse", "stock", "kucun", "fba_warehouse"]),
    ("广告投放", ["ad_", "adv_", "campaign", "sp_", "sb_", "word_report", "asin_report"]),
    ("采购管理", ["purchase", "caigou", "procurement"]),
    ("物流管理", ["logistics", "shipment", "shipping", "first_leg", "last_mile", "inbound", "tracking"]),
    ("产品管理", ["product", "listing", "asin", "spu", "sku"]),
    ("退货退款", ["return", "refund", "tuihuo"]),
    ("利润报告", ["profit", "cost", "fee"]),
    ("评论评价", ["review", "rating"]),
    ("店铺管理", ["store", "seller", "account"]),
    ("人员组织", ["staff", "team", "leader", "department", "org"]),
    ("目标考核", ["target", "mubiao", "completion", "evaluation"]),
    ("仓储费用", ["storage_fee"]),
    ("数据预测", ["forecast", "estimate", "yugu"]),
]


def _identify_layer(table_name: str) -> Tuple[str, str]:
    prefix = table_name.split("_")[0].lower()
    if prefix in LAYER_MAP:
        return LAYER_MAP[prefix]
    for key in LAYER_MAP:
        if table_name.lower().startswith(key + "_"):
            return LAYER_MAP[key]
    return ("业务表", "业务相关数据表")


def _infer_table_description(table_name: str) -> str:
    parts = table_name.lower().replace("__", "_").split("_")
    known = []
    for p in parts:
        if p in DOMAIN_KEYWORDS:
            known.append(DOMAIN_KEYWORDS[p])
        elif p in ("incr", "incremental"):
            known.append("增量")
        elif p in ("new", "v1", "v2", "v3"):
            known.append(f"({p}版本)")
        elif p in ("tmp", "temp"):
            known.append("临时")
        elif p == "list":
            known.append("列表")
        elif p == "detail":
            known.append("明细")
        elif p in ("summary", "stat", "statistics"):
            known.append("统计/汇总")
        elif p == "all":
            known.append("全部")
        elif p == "analysis":
            known.append("分析")
        elif p == "mapping":
            known.append("映射关系")
        elif p == "info":
            known.append("信息")
        elif p == "num":
            known.append("数量")
        elif p == "rules":
            known.append("规则")
    return " - ".join(known) if known else table_name


def _infer_column_description(col_name: str, col_comment: str) -> str:
    if col_comment and col_comment.strip():
        return col_comment.strip()
    if col_name.lower() in COLUMN_NAME_MAP:
        return COLUMN_NAME_MAP[col_name.lower()]
    parts = col_name.lower().split("_")
    known = []
    for p in parts:
        if p in COLUMN_NAME_MAP:
            known.append(COLUMN_NAME_MAP[p])
        elif p in DOMAIN_KEYWORDS:
            known.append(DOMAIN_KEYWORDS[p])
    return "-".join(known) if known else col_name


class SchemaService:
    """Schema 索引管理：加载已有索引或从数据库重新构建。"""

    def __init__(self):
        self._index: Optional[Dict[str, Any]] = None

    @property
    def index(self) -> Dict[str, Any]:
        if self._index is None:
            self._index = self._load_or_build()
        return self._index

    @property
    def tables(self) -> Dict[str, Any]:
        return self.index.get("tables", {})

    @property
    def keyword_index(self) -> Dict[str, List[str]]:
        return self.index.get("keyword_index", {})

    @property
    def categories(self) -> Dict[str, List[str]]:
        return self.index.get("domain_categories", {})

    def _load_or_build(self) -> Dict[str, Any]:
        index_path = _DATA_DIR / "schema_index.json"
        if index_path.exists():
            logger.info("从缓存加载 schema 索引: %s", index_path)
            with open(index_path, "r", encoding="utf-8") as f:
                return json.load(f)
        logger.info("缓存不存在，从数据库重新构建索引...")
        return self.rebuild_index()

    def rebuild_index(self) -> Dict[str, Any]:
        """从数据库拉取所有表结构并构建中文索引。"""
        table_names = db_service.fetch_tables()
        logger.info("共发现 %d 张表", len(table_names))

        schema: Dict[str, List[Dict]] = {}
        for tn in table_names:
            schema[tn] = db_service.fetch_columns(tn)

        index = self._build_index(schema)
        self._index = index

        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        raw_path = _DATA_DIR / "schema_raw.json"
        with open(raw_path, "w", encoding="utf-8") as f:
            json.dump(schema, f, ensure_ascii=False, indent=2, default=str)

        idx_path = _DATA_DIR / "schema_index.json"
        with open(idx_path, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)

        logger.info("索引已保存: %s", idx_path)
        return index

    @staticmethod
    def _build_index(schema: Dict[str, List[Dict]]) -> Dict[str, Any]:
        index: Dict[str, Any] = {
            "database": "dw_leang",
            "database_description": "凌昂跨境电商数据仓库",     
            "total_tables": len(schema),
            "layers": {},
            "tables": {},
            "keyword_index": {},
            "domain_categories": {},
        }

        for table_name, columns in schema.items():
            layer_name, layer_desc = _identify_layer(table_name)
            table_desc = _infer_table_description(table_name)

            if layer_name not in index["layers"]:
                index["layers"][layer_name] = {"description": layer_desc, "tables": []}
            index["layers"][layer_name]["tables"].append(table_name)

            col_list = [
                {
                    "name": col["name"],
                    "type": col["type"],
                    "description_cn": _infer_column_description(col["name"], col.get("comment", "")),
                    "nullable": col.get("null", "YES"),
                    "key": col.get("key", ""),
                }
                for col in columns
            ]
            index["tables"][table_name] = {
                "layer": layer_name,
                "description_cn": table_desc,
                "column_count": len(columns),
                "columns": col_list,
            }

        # 关键字反向索引
        keyword_index: Dict[str, List[str]] = {}
        for table_name, table_info in index["tables"].items():
            kws: set = set()
            for word in re.split(r'[-/\s()（）]', table_info["description_cn"]):
                if len(word) >= 2:
                    kws.add(word)
            for col in table_info["columns"]:
                for word in re.split(r'[-/\s()（）]', col["description_cn"]):
                    if len(word) >= 2:
                        kws.add(word)
            for kw in kws:
                keyword_index.setdefault(kw, []).append(table_name)
        index["keyword_index"] = keyword_index

        # 业务领域分类
        categories: Dict[str, List[str]] = {name: [] for name, _ in _CATEGORY_RULES}
        categories["其他"] = []
        for table_name in schema:
            tn = table_name.lower()
            categorized = False
            for cat_name, cat_keys in _CATEGORY_RULES:
                if cat_name == "产品管理":
                    if any(k in tn for k in cat_keys) and "ad" not in tn:
                        categories[cat_name].append(table_name)
                        categorized = True
                elif any(k in tn for k in cat_keys):
                    categories[cat_name].append(table_name)
                    categorized = True
            if not categorized:
                categories["其他"].append(table_name)
        index["domain_categories"] = categories

        return index

    def search_tables(self, keyword: str) -> List[Dict[str, Any]]:
        results = []
        for table_name, info in self.tables.items():
            if keyword in info["description_cn"] or keyword in table_name:
                results.append({
                    "table": table_name,
                    "layer": info["layer"],
                    "description": info["description_cn"],
                    "column_count": info["column_count"],
                })
        return results

    def describe_table(self, table_name: str) -> Optional[Dict[str, Any]]:
        if table_name not in self.tables:
            return None
        info = self.tables[table_name]
        return {
            "table": table_name,
            "layer": info["layer"],
            "description": info["description_cn"],
            "columns": [
                {"name": c["name"], "type": c["type"], "description": c["description_cn"]}
                for c in info["columns"]
            ],
        }


schema_service = SchemaService()
