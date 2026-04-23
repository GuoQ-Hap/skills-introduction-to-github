"""智能数据脱敏服务：仅对 PII（个人隐私信息）脱敏，保留业务指标原样。

策略：
  1. 列名关键词识别 — 根据列名判断该列是否为 PII 字段
  2. 值正则兜底识别 — 即使列名未命中，也能通过值格式检测手机号/邮箱/身份证
  3. 业务指标（金额、数量、百分比等）全部保留，确保 LLM 能做出高质量分析

脱敏规则：
  手机号  138****5678      保留前3后4
  邮箱    z***@leang.com   保留首字母+域名
  身份证  110***********34 保留前3后4
  姓名    张**             保留姓氏
  地址    深圳市***        保留前3字符
  银行卡  ************1234 保留后4位
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


# ===================== 列名 → PII 类型映射 =====================

_COL_RULES: List[tuple[re.Pattern, str]] = [
    (re.compile(
        r"(姓名|真实姓名|员工名|sales_?man|人员名|联系人|负责人|组长|leader"
        r"|nick_?name|user_?name|full_?name|real_?name"
        r"|creator|updater|审批人|申请人|收件人|发件人)",
        re.I,
    ), "name"),
    (re.compile(
        r"(电话|手机|phone|mobile|tel(?:ephone)?|联系方式|contact_?no)",
        re.I,
    ), "phone"),
    (re.compile(r"(邮箱|email|e_?mail)", re.I), "email"),
    (re.compile(r"(身份证|id_?card|identity|证件号)", re.I), "id_card"),
    (re.compile(
        r"(?<!\w)(详细地址|收货地址|家庭住址|address|addr)(?!\w)",
        re.I,
    ), "address"),
    (re.compile(
        r"(银行卡|bank_?card|card_?no|账号|account_?no)",
        re.I,
    ), "bank"),
]

# ===================== 值正则（兜底检测） =====================

_PHONE_RE = re.compile(r"^(?:\+?86)?1[3-9]\d{9}$")
_EMAIL_RE = re.compile(r"^[\w.-]+@[\w.-]+\.\w{2,}$")
_ID_CARD_RE = re.compile(
    r"^[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]$"
)
_BANK_CARD_RE = re.compile(r"^[3-6]\d{15,18}$")


# ===================== 脱敏函数 =====================

def _mask_name(val: str) -> str:
    if not val:
        return "*"
    return val[0] + "*" * max(len(val) - 1, 1)


def _mask_phone(val: str) -> str:
    digits = re.sub(r"\D", "", val)
    if len(digits) >= 11:
        core = digits[-11:]
        return core[:3] + "****" + core[-4:]
    return "****" + digits[-4:] if len(digits) >= 4 else "****"


def _mask_email(val: str) -> str:
    parts = val.split("@", 1)
    if len(parts) == 2:
        local, domain = parts
        return (local[0] if local else "") + "***@" + domain
    return "***"


def _mask_id_card(val: str) -> str:
    if len(val) >= 15:
        return val[:3] + "*" * (len(val) - 7) + val[-4:]
    return "****"


def _mask_address(val: str) -> str:
    if len(val) <= 3:
        return "***"
    return val[:3] + "***"


def _mask_bank(val: str) -> str:
    if len(val) >= 8:
        return "*" * (len(val) - 4) + val[-4:]
    return "****"


_MASK_FN = {
    "name": _mask_name,
    "phone": _mask_phone,
    "email": _mask_email,
    "id_card": _mask_id_card,
    "address": _mask_address,
    "bank": _mask_bank,
}


# ===================== DataMasker =====================

class DataMasker:
    """智能 PII 脱敏器。业务指标（数字/金额/百分比）全部保留。"""

    def __init__(self):
        self._col_type_cache: Dict[str, Optional[str]] = {}
        self._mask_count = 0

    @staticmethod
    def _detect_col_type(col_name: str) -> Optional[str]:
        for pattern, pii_type in _COL_RULES:
            if pattern.search(col_name):
                return pii_type
        return None

    @staticmethod
    def _detect_val_type(val: str) -> Optional[str]:
        """通过值的格式兜底检测 PII 类型。"""
        if _PHONE_RE.match(val):
            return "phone"
        if _EMAIL_RE.match(val):
            return "email"
        if _ID_CARD_RE.match(val):
            return "id_card"
        if _BANK_CARD_RE.match(val):
            return "bank"
        return None

    def _get_col_type(self, col: str) -> Optional[str]:
        if col not in self._col_type_cache:
            self._col_type_cache[col] = self._detect_col_type(col)
        return self._col_type_cache[col]

    def mask_value(self, value: Any, column: str) -> str:
        """对单个值做智能脱敏。PII → 脱敏，其他 → 原样。"""
        if value is None:
            return ""
        str_val = str(value).strip()
        if not str_val:
            return ""

        pii_type = self._get_col_type(column)
        if not pii_type:
            pii_type = self._detect_val_type(str_val)

        if pii_type:
            fn = _MASK_FN.get(pii_type)
            if fn:
                self._mask_count += 1
                return fn(str_val)

        return str_val

    def mask_rows(
        self, columns: List[str], rows: List[Dict[str, Any]]
    ) -> List[Dict[str, str]]:
        """批量脱敏：仅替换 PII 字段，业务指标原样保留。"""
        return [
            {col: self.mask_value(row.get(col), col) for col in columns}
            for row in rows
        ]

    @property
    def mask_count(self) -> int:
        return self._mask_count
