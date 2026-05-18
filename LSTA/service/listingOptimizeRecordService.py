"""Listing 优化确认入库与前后对比记录。"""
from __future__ import annotations

import json
import mimetypes
import tempfile
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import pymysql
import requests

from Base.Client.minioClient import default_minio_client
from Base.Config.setting import settings
from LDA.service.dbService import db_service
from LSTA.service.base import service_logger

logger = service_logger

RECORD_TABLE = "lsta_listing_optimize_record"
TARGET_HOST = "10.0.10.21"
TARGET_DB = "ric_ai_base"
IMAGE_BUCKET = "lsta-listing-optimize"


def _json_dumps(value: Any) -> str:
    return json.dumps(value or {}, ensure_ascii=False)


def _json_loads(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return default


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _safe_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(float(value))
    except Exception:
        return None


def _as_date(value: Any) -> Optional[date]:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if value in (None, ""):
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except Exception:
        try:
            return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
        except Exception:
            return None
    try:
        return int(float(value))
    except Exception:
        return None


class ListingOptimizeRecordService:
    """保存人工确认采用的 Listing 优化结果，并动态拉取当前指标做对比。"""

    def _target_connect(self) -> pymysql.Connection:
        cfg = settings.mysql
        host = str(cfg.host or "")
        if host != TARGET_HOST:
            raise RuntimeError(f"安全限制：Listing优化记录只允许连接 {TARGET_HOST}，当前 DB_HOST={host}")
        bootstrap = pymysql.connect(
            host=TARGET_HOST,
            port=int(cfg.port or 3306),
            user=cfg.user,
            password=str(cfg.password or ""),
            charset=cfg.charset or "utf8mb4",
            autocommit=True,
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=10,
            read_timeout=120,
        )
        with bootstrap:
            with bootstrap.cursor() as cur:
                cur.execute(f"CREATE DATABASE IF NOT EXISTS `{TARGET_DB}` DEFAULT CHARSET utf8mb4")
        return pymysql.connect(
            host=TARGET_HOST,
            port=int(cfg.port or 3306),
            user=cfg.user,
            password=str(cfg.password or ""),
            database=TARGET_DB,
            charset=cfg.charset or "utf8mb4",
            autocommit=True,
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=10,
            read_timeout=120,
        )

    def ensure_tables(self) -> None:
        sql = f"""
        CREATE TABLE IF NOT EXISTS `{RECORD_TABLE}` (
          `id` BIGINT NOT NULL AUTO_INCREMENT,
          `asin` VARCHAR(32) NOT NULL DEFAULT '',
          `marketplace` VARCHAR(16) NOT NULL DEFAULT '',
          `store_name` VARCHAR(80) NOT NULL DEFAULT '',
          `country_code` VARCHAR(16) NOT NULL DEFAULT '',
          `sku` VARCHAR(160) NOT NULL DEFAULT '',
          `optimization_reason` VARCHAR(2048) NOT NULL DEFAULT '',
          `optimization_direction` VARCHAR(2048) NOT NULL DEFAULT '',
          `remark` VARCHAR(4000) NOT NULL DEFAULT '',
          `before_listing_json` JSON NOT NULL,
          `after_listing_json` JSON NOT NULL,
          `before_images_json` JSON NOT NULL,
          `after_images_json` JSON NOT NULL,
          `before_metrics_json` JSON NOT NULL,
          `metric_period_days` INT NOT NULL DEFAULT 30,
          `metric_start` DATE NOT NULL,
          `metric_end` DATE NOT NULL,
          `variant_rank` INT NULL,
          `variant_total` INT NULL,
          `source_memory_id` BIGINT NULL,
          `operator` VARCHAR(80) NOT NULL DEFAULT '',
          `updated_by` VARCHAR(80) NOT NULL DEFAULT '',
          `extra_json` JSON NOT NULL,
          `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          PRIMARY KEY (`id`),
          KEY `idx_listing_opt_record_asin` (`asin`, `created_at`),
          KEY `idx_listing_opt_record_store` (`store_name`, `country_code`, `created_at`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """
        with self._target_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                self._ensure_column(cur, "remark", "`remark` VARCHAR(4000) NOT NULL DEFAULT '' AFTER `optimization_direction`")
                self._ensure_column(cur, "updated_by", "`updated_by` VARCHAR(80) NOT NULL DEFAULT '' AFTER `operator`")

    def _ensure_column(self, cur: pymysql.cursors.DictCursor, column: str, ddl: str) -> None:
        cur.execute(f"SHOW COLUMNS FROM `{RECORD_TABLE}` LIKE %s", [column])
        if not cur.fetchone():
            cur.execute(f"ALTER TABLE `{RECORD_TABLE}` ADD COLUMN {ddl}")

    def create(self, payload: Dict[str, Any], operator: str = "") -> Dict[str, Any]:
        self.ensure_tables()
        asin = str(payload.get("asin") or "").strip()
        if len(asin) != 10:
            raise ValueError("ASIN 必须为 10 位")
        current_start, current_end = self._current_window(date.today())
        metric_start, metric_end = self._before_window(current_start, current_end)
        store_name = str(payload.get("store_name") or "").strip()
        country_code = str(payload.get("country_code") or "").strip()
        before_metrics = self._fetch_metrics_between(
            asin,
            metric_start,
            metric_end,
            store_name=store_name,
            country_code=country_code,
        )
        before_images = self._persist_images(asin, payload.get("before_images") or [], "before")
        after_images_src = payload.get("after_images") or payload.get("before_images") or []
        after_images = self._persist_images(asin, after_images_src, "after")

        fields = [
            "asin", "marketplace", "store_name", "country_code", "sku",
            "optimization_reason", "optimization_direction", "remark",
            "before_listing_json", "after_listing_json",
            "before_images_json", "after_images_json", "before_metrics_json",
            "metric_period_days", "metric_start", "metric_end",
            "variant_rank", "variant_total", "source_memory_id", "operator", "updated_by", "extra_json",
        ]
        row = {
            "asin": asin,
            "marketplace": payload.get("marketplace") or "",
            "store_name": store_name or before_metrics.get("store_name") or "",
            "country_code": country_code or before_metrics.get("country_code") or "",
            "sku": payload.get("sku") or before_metrics.get("msku") or "",
            "optimization_reason": payload.get("optimization_reason") or "",
            "optimization_direction": payload.get("optimization_direction") or "",
            "remark": payload.get("remark") or "",
            "before_listing_json": _json_dumps(payload.get("before_listing") or {}),
            "after_listing_json": _json_dumps(payload.get("after_listing") or {}),
            "before_images_json": _json_dumps(before_images),
            "after_images_json": _json_dumps(after_images),
            "before_metrics_json": _json_dumps(before_metrics),
            "metric_period_days": before_metrics.get("period_days") or 1,
            "metric_start": metric_start,
            "metric_end": metric_end,
            "variant_rank": payload.get("variant_rank"),
            "variant_total": payload.get("variant_total"),
            "source_memory_id": payload.get("source_memory_id"),
            "operator": operator or payload.get("operator") or "",
            "updated_by": operator or payload.get("operator") or "",
            "extra_json": _json_dumps(payload.get("extra") or {}),
        }
        sql = f"""
        INSERT INTO `{RECORD_TABLE}` ({", ".join(f"`{f}`" for f in fields)})
        VALUES ({", ".join(["%s"] * len(fields))})
        """
        with self._target_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, [row[f] for f in fields])
                record_id = cur.lastrowid
        return {"success": True, "id": record_id, "record": self.detail(record_id)}

    def list(self, *, asin: str = "", marketplace: str = "", limit: int = 100) -> Dict[str, Any]:
        self.ensure_tables()
        filters: List[str] = []
        params: List[Any] = []
        if asin:
            filters.append("asin = %s")
            params.append(asin)
        if marketplace:
            filters.append("marketplace = %s")
            params.append(marketplace)
        where = "WHERE " + " AND ".join(filters) if filters else ""
        sql = f"""
        SELECT *
        FROM `{RECORD_TABLE}`
        {where}
        ORDER BY created_at DESC, id DESC
        LIMIT %s
        """
        with self._target_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, [*params, max(1, min(int(limit or 100), 500))])
                rows = list(cur.fetchall())
        return {"items": [self._hydrate(row, include_current=True) for row in rows]}

    def detail(self, record_id: int) -> Dict[str, Any]:
        self.ensure_tables()
        with self._target_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SELECT * FROM `{RECORD_TABLE}` WHERE id = %s", [record_id])
                row = cur.fetchone()
        if not row:
            raise ValueError("记录不存在")
        return self._hydrate(row, include_current=True)

    def update_remark(self, record_id: int, remark: str, operator: str = "") -> Dict[str, Any]:
        self.ensure_tables()
        with self._target_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE `{RECORD_TABLE}` SET remark = %s, updated_by = %s WHERE id = %s",
                    [remark or "", operator or "", record_id],
                )
                if cur.rowcount == 0:
                    raise ValueError("记录不存在")
        return {"success": True, "record": self.detail(record_id)}

    def update_store(
        self,
        record_id: int,
        store_name: str,
        country_code: str = "",
        sku: str = "",
        operator: str = "",
    ) -> Dict[str, Any]:
        self.ensure_tables()
        with self._target_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    UPDATE `{RECORD_TABLE}`
                    SET store_name = %s,
                        country_code = %s,
                        sku = %s,
                        updated_by = %s
                    WHERE id = %s
                    """,
                    [store_name or "", country_code or "", sku or "", operator or "", record_id],
                )
                if cur.rowcount == 0:
                    raise ValueError("记录不存在")
        return {"success": True, "record": self.detail(record_id)}

    def store_options(self, asin: str) -> Dict[str, Any]:
        asin = str(asin or "").strip()
        if not asin:
            return {"items": []}
        asin_lit = asin.replace("'", "")
        try:
            sql = f"""
            SELECT
                a.store_name,
                a.country_code,
                MAX(a.price_list_seller_sku) AS msku,
                SUM(a.amount) AS total_amount,
                SUM(a.sessions_total) AS total_sessions
            FROM ads_lingxing_sc_sales_daily_new a
            WHERE a.asin = '{asin_lit}'
              AND a.store_name IS NOT NULL AND a.store_name != ''
              AND a.date >= DATE_SUB(CURRENT_DATE(), INTERVAL 180 DAY)
            GROUP BY a.store_name, a.country_code
            ORDER BY total_amount DESC, total_sessions DESC
            LIMIT 50
            """
            _, rows = db_service.execute_sql(sql)
        except Exception as exc:
            logger.warning("Listing优化记录: 查询店铺选项失败 ASIN=%s: %s", asin, exc)
            rows = []
        return {
            "items": [
                {
                    "store_name": row.get("store_name") or "",
                    "country_code": row.get("country_code") or "",
                    "msku": row.get("msku") or "",
                    "total_amount": _safe_float(row.get("total_amount")),
                    "traffic": _safe_int(row.get("total_sessions")),
                }
                for row in rows
                if row.get("store_name")
            ]
        }

    def delete(self, record_id: int) -> Dict[str, Any]:
        self.ensure_tables()
        with self._target_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SELECT * FROM `{RECORD_TABLE}` WHERE id = %s", [record_id])
                row = cur.fetchone()
                if not row:
                    raise ValueError("记录不存在")
                self._remove_record_images(row)
                cur.execute(f"DELETE FROM `{RECORD_TABLE}` WHERE id = %s", [record_id])
        return {"success": True, "id": record_id}

    def _hydrate(self, row: Dict[str, Any], *, include_current: bool) -> Dict[str, Any]:
        current_start, current_end = self._current_window(row.get("created_at"))
        store_name = row.get("store_name") or ""
        country_code = row.get("country_code") or ""
        before_metrics = _json_loads(row.get("before_metrics_json"), {})
        if not before_metrics:
            before_start, before_end = self._before_window(current_start, current_end)
            before_metrics = self._fetch_metrics_between(
                row.get("asin") or "",
                before_start,
                before_end,
                store_name=store_name,
                country_code=country_code,
            )
        current_metrics = self._fetch_metrics_between(
            row.get("asin") or "",
            current_start,
            current_end,
            store_name=store_name,
            country_code=country_code,
        ) if include_current else {}
        return {
            "id": row.get("id"),
            "asin": row.get("asin") or "",
            "marketplace": row.get("marketplace") or "",
            "store_name": row.get("store_name") or "",
            "country_code": row.get("country_code") or "",
            "sku": row.get("sku") or "",
            "optimization_reason": row.get("optimization_reason") or "",
            "optimization_direction": row.get("optimization_direction") or "",
            "remark": row.get("remark") or "",
            "before_listing": _json_loads(row.get("before_listing_json"), {}),
            "after_listing": _json_loads(row.get("after_listing_json"), {}),
            "before_images": _json_loads(row.get("before_images_json"), []),
            "after_images": _json_loads(row.get("after_images_json"), []),
            "before_metrics": before_metrics,
            "current_metrics": current_metrics,
            "metric_period_days": before_metrics.get("period_days") or row.get("metric_period_days") or 30,
            "metric_start": before_metrics.get("metric_start") or str(row.get("metric_start") or ""),
            "metric_end": before_metrics.get("metric_end") or str(row.get("metric_end") or ""),
            "current_metric_start": current_metrics.get("metric_start") or "",
            "current_metric_end": current_metrics.get("metric_end") or "",
            "variant_rank": row.get("variant_rank"),
            "variant_total": row.get("variant_total"),
            "source_memory_id": row.get("source_memory_id"),
            "operator": row.get("operator") or "",
            "updated_by": row.get("updated_by") or "",
            "extra": _json_loads(row.get("extra_json"), {}),
            "created_at": str(row.get("created_at") or ""),
            "updated_at": str(row.get("updated_at") or ""),
        }

    def _remove_record_images(self, row: Dict[str, Any]) -> None:
        images = []
        images.extend(_json_loads(row.get("before_images_json"), []))
        images.extend(_json_loads(row.get("after_images_json"), []))
        seen = set()
        for img in images:
            bucket = img.get("bucket") if isinstance(img, dict) else ""
            object_name = img.get("object_name") if isinstance(img, dict) else ""
            key = (bucket, object_name)
            if not bucket or not object_name or key in seen:
                continue
            seen.add(key)
            try:
                default_minio_client.remove_object(bucket, object_name)
            except Exception as exc:
                logger.warning("Listing优化记录: 删除MinIO图片失败 bucket=%s object=%s: %s", bucket, object_name, exc)

    def _current_window(self, updated_at: Any) -> tuple[str, str]:
        end = date.today() - timedelta(days=1)
        start = _as_date(updated_at) or end
        if start > end:
            start = end
        return str(start), str(end)

    def _before_window(self, current_start: str, current_end: str) -> tuple[str, str]:
        start = _as_date(current_start) or (date.today() - timedelta(days=1))
        end = _as_date(current_end) or start
        days = max(1, (end - start).days + 1)
        before_end = start - timedelta(days=1)
        before_start = before_end - timedelta(days=days - 1)
        return str(before_start), str(before_end)

    def _latest_sales_date(self) -> Optional[date]:
        try:
            _, rows = db_service.execute_sql("SELECT MAX(date) AS max_date FROM ads_lingxing_sc_sales_daily_new")
            if not rows:
                return None
            return _as_date(rows[0].get("max_date"))
        except Exception as exc:
            logger.warning("Listing优化记录: 查询销量源表最新日期失败: %s", exc)
            return None

    def _fetch_metrics_between(
        self,
        asin: str,
        metric_start: str,
        metric_end: str,
        *,
        store_name: str = "",
        country_code: str = "",
    ) -> Dict[str, Any]:
        start = _as_date(metric_start) or (date.today() - timedelta(days=1))
        end = _as_date(metric_end) or start
        latest_date = self._latest_sales_date()
        period_days = max(1, (end - start).days + 1)
        original_start_s = start.isoformat()
        original_end_s = end.isoformat()
        empty = {"metric_start": original_start_s, "metric_end": original_end_s, "period_days": period_days}
        if latest_date and start > latest_date:
            return empty
        if latest_date and end > latest_date:
            end = latest_date
        if start > end:
            start = end
        start_s = start.isoformat()
        end_s = end.isoformat()
        empty = {"metric_start": start_s, "metric_end": end_s, "period_days": max(1, (end - start).days + 1)}
        if not asin:
            return empty
        asin_lit = asin.replace("'", "")
        store_lit = (store_name or "").replace("'", "")
        country_lit = (country_code or "").replace("'", "")
        ad_store_filter = f"\n                  AND a.store_name = '{store_lit}'" if store_lit else ""
        session_store_filter = f"\n                  AND a.store_name = '{store_lit}'" if store_lit else ""
        ad_country_filter = f"\n                  AND a.country_code = '{country_lit}'" if country_lit else ""
        session_country_filter = f"\n                  AND a.country_code = '{country_lit}'" if country_lit else ""
        try:
            sql = f"""
            WITH ad_metrics AS (
                SELECT
                    a.asin,
                    MAX(a.price_list_seller_sku) AS msku,
                    MAX(a.store_name) AS store_name,
                    MAX(a.country_code) AS country_code,
                    MAX(a.category_2) AS category_2,
                    SUM(a.impressions) AS total_impressions,
                    SUM(a.clicks) AS total_clicks,
                    SUM(a.ad_order_quantity) AS total_ad_orders,
                    SUM(a.volume) AS total_volume,
                    ROUND(SUM(a.amount), 2) AS total_amount,
                    CASE WHEN SUM(a.impressions) > 0
                         THEN SUM(a.clicks) * 1.0 / SUM(a.impressions)
                         ELSE 0 END AS product_ctr,
                    CASE WHEN SUM(a.clicks) > 0
                         THEN SUM(a.ad_order_quantity) * 1.0 / SUM(a.clicks)
                         ELSE 0 END AS product_cvr
                FROM ads_lingxing_sc_sales_daily_new a
                WHERE a.date >= '{start_s}'
                  AND a.date <= '{end_s}'
                  AND a.asin = '{asin_lit}'
                  AND a.category_2 IS NOT NULL AND a.category_2 != ''
                  AND a.impressions > 0
                  {ad_store_filter}{ad_country_filter}
                GROUP BY a.asin
            ),
            session_metrics AS (
                SELECT
                    a.asin,
                    SUM(a.sessions_total) AS total_sessions
                FROM ads_lingxing_sc_sales_daily_new a
                WHERE a.date >= '{start_s}'
                  AND a.date <= '{end_s}'
                  AND a.asin = '{asin_lit}'{session_store_filter}{session_country_filter}
                GROUP BY a.asin
            )
            SELECT
                ad.asin,
                ad.msku,
                ad.store_name,
                ad.country_code,
                ad.category_2,
                ROUND(ad.product_ctr * 100, 4) AS product_ctr_pct,
                ROUND(ad.product_cvr * 100, 4) AS product_cvr_pct,
                COALESCE(sm.total_sessions, 0) AS recent_sessions,
                ad.total_volume,
                ad.total_amount
            FROM ad_metrics ad
            LEFT JOIN session_metrics sm
                ON ad.asin = sm.asin
            ORDER BY ad.total_amount DESC, COALESCE(sm.total_sessions, 0) DESC
            LIMIT 1
            """
            _, rows = db_service.execute_sql(sql)
            row = rows[0] if rows else {}
        except Exception as exc:
            logger.warning(
                "Listing优化记录: 查询区间指标失败 ASIN=%s start=%s end=%s: %s",
                asin,
                start_s,
                end_s,
                exc,
            )
            row = {}
        return {
            **empty,
            "ctr": _safe_float(row.get("product_ctr_pct")),
            "cvr": _safe_float(row.get("product_cvr_pct")),
            "traffic": _safe_int(row.get("recent_sessions")),
            "sessions_change_pct": None,
            "store_name": row.get("store_name") or "",
            "country_code": row.get("country_code") or "",
            "msku": row.get("msku") or "",
            "category_2": row.get("category_2") or "",
            "total_volume": _safe_int(row.get("total_volume")),
            "total_amount": _safe_float(row.get("total_amount")),
        }

    def _persist_images(self, asin: str, urls: List[str], stage: str) -> List[Dict[str, str]]:
        out: List[Dict[str, str]] = []
        for idx, url in enumerate([u for u in urls if u][:12]):
            item = {"source_url": str(url), "bucket": "", "object_name": "", "url": str(url)}
            try:
                stored = self._copy_image_to_minio(str(url), asin, stage, idx)
                if stored:
                    item.update(stored)
            except Exception as exc:
                logger.warning("Listing优化记录: 图片入MinIO失败 url=%s: %s", url, exc)
            out.append(item)
        return out

    def _copy_image_to_minio(self, url: str, asin: str, stage: str, idx: int) -> Optional[Dict[str, str]]:
        if url.startswith("minio://"):
            return None
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=20)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type") or "image/jpeg"
        ext = mimetypes.guess_extension(content_type.split(";")[0].strip()) or ".jpg"
        object_name = f"listing-optimize/{asin}/{date.today().isoformat()}/{stage}-{idx + 1}-{uuid.uuid4().hex[:8]}{ext}"
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp.write(resp.content)
            tmp_path = tmp.name
        try:
            ok = default_minio_client.upload_file(IMAGE_BUCKET, object_name, tmp_path, content_type=content_type)
            if not ok:
                return None
            presigned = default_minio_client.get_presigned_url(IMAGE_BUCKET, object_name, expiry_hours=24 * 7) or ""
            return {
                "bucket": IMAGE_BUCKET,
                "object_name": object_name,
                "url": presigned or f"minio://{IMAGE_BUCKET}/{object_name}",
            }
        finally:
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except Exception:
                pass


listing_optimize_record_service = ListingOptimizeRecordService()
