"""领星 ERP Open API 服务 —— Listing 提交"""
from __future__ import annotations

import hashlib
import logging
import os
import time
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger("LSTA.service.lingxingService")

_TOKEN_CACHE: Dict[str, Any] = {"access_token": "", "expires_at": 0}


class LingxingService:
    """封装领星 ERP Open API 的认证和 Listing 提交逻辑。"""

    def __init__(self):
        self.app_id = os.getenv("LINGXING_APP_ID", "")
        self.app_secret = os.getenv("LINGXING_APP_SECRET", "")
        self.base_url = os.getenv("LINGXING_API_BASE", "https://openapi.lingxingerp.com/erp/sc")

    @property
    def configured(self) -> bool:
        return bool(self.app_id and self.app_secret)

    def _get_access_token(self) -> str:
        """获取/刷新 access_token（带缓存）。"""
        now = time.time()
        if _TOKEN_CACHE["access_token"] and _TOKEN_CACHE["expires_at"] > now + 60:
            return _TOKEN_CACHE["access_token"]

        url = self.base_url.rstrip("/").rsplit("/erp/sc", 1)[0] + "/api/auth-server/oauth/access-token"
        ts = str(int(now))
        sign_str = f"{self.app_id}{ts}{self.app_secret}"
        sign = hashlib.md5(sign_str.encode()).hexdigest()

        resp = requests.post(url, json={
            "appId": self.app_id,
            "appSecret": self.app_secret,
            "timestamp": ts,
            "sign": sign,
        }, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") != 0:
            raise RuntimeError(f"领星认证失败: {data.get('msg', data)}")

        token_data = data.get("data", {})
        _TOKEN_CACHE["access_token"] = token_data["access_token"]
        _TOKEN_CACHE["expires_at"] = now + token_data.get("expires_in", 7200) - 120
        logger.info("领星 access_token 获取成功")
        return _TOKEN_CACHE["access_token"]

    def _request(self, method: str, path: str, **kwargs) -> Dict[str, Any]:
        """带认证的通用请求。"""
        token = self._get_access_token()
        url = f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {token}"
        headers.setdefault("Content-Type", "application/json")

        resp = requests.request(method, url, headers=headers, timeout=30, **kwargs)
        resp.raise_for_status()
        result = resp.json()
        if result.get("code") not in (0, 200, None):
            raise RuntimeError(f"领星 API 错误: {result.get('msg', result)}")
        return result

    def submit_listing(
        self,
        *,
        asin: str,
        marketplace: str,
        title: str,
        bullet_points: List[str],
        description: str,
        search_terms: str,
        seller_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        将优化后的 Listing 提交到领星 ERP。

        领星 Open API listing 编辑端点：/routing/listing/editListing
        具体参数需根据领星最新文档调整。
        """
        if not self.configured:
            raise RuntimeError(
                "领星 ERP 未配置：请在 .env 中设置 LINGXING_APP_ID 和 LINGXING_APP_SECRET"
            )

        bullet_text = "\n".join(bullet_points) if bullet_points else ""

        payload: Dict[str, Any] = {
            "asin": asin,
            "marketplace_id": self._marketplace_to_id(marketplace),
            "title": title,
            "bullet_point": bullet_text,
            "product_description": description,
            "search_terms": search_terms,
        }
        if seller_id:
            payload["sid"] = seller_id

        logger.info("正在提交 Listing 到领星: ASIN=%s, 站点=%s", asin, marketplace)
        result = self._request("POST", "/routing/listing/editListing", json=payload)
        logger.info("领星提交成功: %s", result.get("msg", "OK"))
        return result

    @staticmethod
    def _marketplace_to_id(marketplace: str) -> str:
        """站点代码 -> 领星 marketplace_id 映射。"""
        mapping = {
            "US": "ATVPDKIKX0DER",
            "UK": "A1F83G8C2ARO7P",
            "DE": "A1PA6795UKMFR9",
            "FR": "A13V1IB3VIYZZH",
            "IT": "APJ6JRA9NG5V4",
            "ES": "A1RKKUPIHCS9HS",
            "JP": "A1VC38T7YXB528",
            "CA": "A2EUQ1WTGCTBG2",
            "AU": "A39IBJ37TRP1C6",
            "IN": "A21TJRUUN4KGV",
            "MX": "A1AM78C64UM0Y8",
        }
        return mapping.get(marketplace.upper(), marketplace)


lingxing_service = LingxingService()
