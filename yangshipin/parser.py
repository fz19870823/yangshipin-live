"""
央视频直播地址解析器 — 统一入口

支持两种解析策略：
1. 浏览器模式 (Playwright) — 推荐，可靠性最高
2. API 直连模式 — 轻量但 cKey 可能过期

使用示例:
    from yangshipin import YangshipinParser

    parser = YangshipinParser()
    
    # 浏览器模式 — 解析所有 CCTV 频道
    results = await parser.parse_browser(category="cctv")
    
    # 浏览器模式 — 解析单个频道
    results = await parser.parse_browser(pids=["600001859"])
    
    # API 模式（实验性）
    results = parser.parse_api(category="cctv")
"""

import asyncio
import logging

from .api import YangshipinAPI
from .browser import BrowserParser
from .channels import (
    ALL_CHANNELS,
    CCTV_CHANNELS,
    CGTN_CHANNELS,
    SATELLITE_CHANNELS,
    PREMIUM_CHANNELS,
    Channel,
    get_channel_by_pid,
    get_channels_by_category,
)

logger = logging.getLogger(__name__)


class YangshipinParser:
    """央视频直播地址解析器"""

    def __init__(
        self,
        cookie: str = "",
        timeout: int = 30,
        defn: str = "auto",
        headless: bool = True,
        browser_channel: str = "chrome",
    ):
        self.cookie = cookie
        self.timeout = timeout
        self.defn = defn
        self.headless = headless
        self.browser_channel = browser_channel

        # API 客户端（实验性）
        self._api = YangshipinAPI(cookie=cookie, timeout=min(timeout, 30))
        # 浏览器解析器（推荐，使用系统 Chrome）
        self._browser = BrowserParser(
            headless=headless,
            timeout=timeout,
            wait_time=8.0,
            browser_channel=browser_channel,
        )

    # ============================================================
    # 浏览器模式（推荐）
    # ============================================================

    async def parse_browser(
        self,
        category: str | None = None,
        pids: list[str] | None = None,
    ) -> list[dict]:
        """
        使用浏览器拦截方式解析

        Args:
            category: 频道分类 ("cctv"|"cgtn"|"satellite"|"premium"|None=全部)
            pids: 指定 pid 列表（优先级高于 category）

        Returns:
            解析结果列表
        """
        if pids:
            return await self._browser.parse_pids(pids)
        elif category:
            channels = get_channels_by_category(category)
            return await self._browser.parse_channels(channels)
        else:
            return await self._browser.parse_channels(ALL_CHANNELS)

    def parse_browser_sync(
        self,
        category: str | None = None,
        pids: list[str] | None = None,
    ) -> list[dict]:
        """同步版本的浏览器解析"""
        return asyncio.run(self.parse_browser(category=category, pids=pids))

    # ============================================================
    # API 模式（实验性）
    # ============================================================

    def parse_api(
        self,
        category: str | None = None,
        pids: list[str] | None = None,
    ) -> list[dict]:
        """
        使用 API 直连方式解析（实验性，cKey 可能已过期）

        Args:
            category: 频道分类
            pids: 指定 pid 列表
        """
        if pids:
            channels = [get_channel_by_pid(p) for p in pids]
            channels = [c for c in channels if c is not None]
        elif category:
            channels = get_channels_by_category(category)
        else:
            channels = ALL_CHANNELS

        return self._api.get_all_streams(channels, defn=self.defn)

    # ============================================================
    # 导出工具
    # ============================================================

    def export_m3u(self, results: list[dict], path: str, group: str = "央视频"):
        """导出 M3U 播放列表"""
        BrowserParser.export_m3u(results, path, group)

    def export_json(self, results: list[dict], path: str):
        """导出 JSON 结果"""
        BrowserParser.export_json(results, path)

    def print_summary(self, results: list[dict]):
        """打印结果摘要"""
        BrowserParser.print_summary(results)
