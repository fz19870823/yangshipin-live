"""
直播地址存储 + 定时刷新

从 yangshipin browser_v2 模块获取频道播放地址，
每 6 小时自动刷新，供 Worker 使用。
"""

import asyncio
import json
import logging
import os
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


# 将项目根目录加入 path，以便导入 yangshipin 模块
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class UrlStore:
    """频道直播地址缓存

    用法:
        store = UrlStore()
        await store.refresh()          # 立即刷新
        store.start_scheduler(21600)   # 每 6 小时刷新

        urls = store.get_all()         # 获取所有频道 URL
        url  = store.get("CCTV-1 综合") # 获取单个频道 URL
    """

    def __init__(self, cache_path: Path = None, on_refresh: callable = None):
        self._urls: dict = {}          # channel_name → m3u8_url
        self._channels: list = []      # [{name, pid, ...}]
        self._last_refresh: datetime = None
        self._lock = threading.Lock()
        self._cache_path = cache_path or (PROJECT_ROOT / "channel_urls.json")
        self._on_refresh = on_refresh

        # 尝试加载缓存
        self._load_cache()

    def get(self, channel_name: str) -> str | None:
        with self._lock:
            return self._urls.get(channel_name)

    def get_all(self) -> dict:
        with self._lock:
            return dict(self._urls)

    def get_channels(self) -> list:
        with self._lock:
            return list(self._channels)

    def get_last_refresh(self) -> datetime | None:
        return self._last_refresh

    def _load_cache(self):
        """从本地文件加载缓存的 URL"""
        if self._cache_path.exists():
            try:
                data = json.loads(self._cache_path.read_text(encoding="utf-8"))
                self._urls = data.get("urls", {})
                self._channels = data.get("channels", [])
                ts = data.get("updated_at", "")
                if ts:
                    self._last_refresh = datetime.fromisoformat(ts)
                logger.info(
                    f"从缓存加载 {len(self._urls)} 个频道 "
                    f"(更新时间: {self._last_refresh})"
                )
            except Exception as e:
                logger.warning(f"缓存加载失败: {e}")

    def _save_cache(self):
        """保存 URL 到本地文件"""
        data = {
            "urls": self._urls,
            "channels": self._channels,
            "updated_at": datetime.now().isoformat(),
        }
        self._cache_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    async def refresh(self) -> int:
        """从浏览器抓取最新直播地址，返回成功数量"""
        logger.info("开始刷新直播地址...")
        t0 = time.time()

        try:
            from yangshipin.channels import ALL_CHANNELS
            from yangshipin.browser_v2 import BrowserParserV2
        except ImportError as e:
            logger.error(f"导入失败: {e}")
            return 0

        parser = BrowserParserV2(
            headless=True,
            timeout=30,
            wait_time=3.0,
            browser_channel="chrome",
        )

        try:
            results = await parser.parse_channels(ALL_CHANNELS)
        except Exception as e:
            logger.error(f"解析失败: {e}")
            return 0

        # 更新缓存
        with self._lock:
            self._urls.clear()
            self._channels.clear()
            for r in results:
                name = r.get("channel", "?")
                if "url" in r:
                    self._urls[name] = r["url"]
                self._channels.append({
                    "name": name,
                    "pid": r.get("pid", ""),
                    "has_url": "url" in r,
                })

        self._last_refresh = datetime.now()
        self._save_cache()

        elapsed = time.time() - t0
        success = len(self._urls)
        logger.info(
            f"刷新完成: {success}/{len(results)} 个频道 ({elapsed:.0f}s)"
        )

        # 触发回调（预热 init 段）
        if self._on_refresh:
            try:
                channels = [
                    {"name": c["name"], "pid": c["pid"]}
                    for c in self._channels if c["has_url"]
                ]
                self._on_refresh(channels)
            except Exception as e:
                logger.error(f"刷新回调失败: {e}")

        return success

    def start_scheduler(self, interval_seconds: int = 21600):
        """启动后台定时刷新线程，每天 0 点开始每 interval 秒刷新一次"""
        def _run():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            async def _refresh_loop():
                # Refresh immediately so a new deployment becomes usable
                # without waiting for the next scheduled interval.
                await self.refresh()
                # 之后每 interval 秒刷新
                while True:
                    await asyncio.sleep(interval_seconds)
                    try:
                        await self.refresh()
                    except Exception as e:
                        logger.error(f"定时刷新失败: {e}")

            try:
                loop.run_until_complete(_refresh_loop())
            except Exception as e:
                logger.error(f"刷新线程异常: {e}")

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        logger.info(
            f"后台刷新线程已启动 (间隔 {interval_seconds // 3600}h)"
        )


# ---- 全局单例 ----
_store: UrlStore | None = None


def get_store(on_refresh: callable = None) -> UrlStore:
    global _store
    if _store is None:
        _store = UrlStore(on_refresh=on_refresh)
    return _store
