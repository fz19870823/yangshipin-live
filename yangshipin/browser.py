"""
央视频直播地址浏览器拦截解析器 (Playwright)

这是目前最可靠的解析方式。
通过 Playwright 无头浏览器加载央视频 TV 页面，
自动拦截网络请求中的 m3u8/flv 直播流地址。

原理：
1. 启动 Chromium 浏览器
2. 加载 https://www.yangshipin.cn/tv/home?pid=XXXX
3. 页面的 JavaScript 自动生成有效的 cKey 并请求流地址
4. 我们拦截响应中的 m3u8 URL
"""

import asyncio
import logging
import re
import sys
from typing import Optional

from .channels import Channel, get_channel_by_pid, ALL_CHANNELS

logger = logging.getLogger(__name__)

# 直播流 URL 匹配规则
_STREAM_PATTERNS = [
    re.compile(r"https?://[^\s\"'<>]+\.m3u8[^\s\"'<>]*", re.IGNORECASE),
    re.compile(r"https?://[^\s\"'<>]+\.flv[^\s\"'<>]*", re.IGNORECASE),
    re.compile(r"https?://[^\s\"'<>]+/live/[^\s\"'<>]+\.(?:m3u8|flv)", re.IGNORECASE),
    # als (= apple live streaming) 格式
    re.compile(r"https?://[^\s\"'<>]+\.als[^\s\"'<>]*", re.IGNORECASE),
]


class BrowserParser:
    """基于浏览器的直播流拦截解析器

    默认使用系统已安装的 Chrome 浏览器（无需额外下载 Chromium）。
    也支持 Edge 浏览器。
    """

    def __init__(
        self,
        headless: bool = True,
        timeout: int = 30,
        wait_time: float = 8.0,
        browser_channel: str = "chrome",
    ):
        """
        Args:
            headless: 是否无头模式
            timeout: 超时秒数
            wait_time: 等待流加载时间
            browser_channel: 浏览器类型 ("chrome" | "msedge" | None=Playwright内置Chromium)
        """
        self.headless = headless
        self.timeout = timeout
        self.wait_time = wait_time
        self.browser_channel = browser_channel

    # ================================================================
    # 主入口
    # ================================================================

    async def parse_channels(
        self,
        channels: list[Channel],
        concurrency: int = 1,
    ) -> list[dict]:
        """
        解析频道列表的直播流地址（复用浏览器实例）

        Args:
            channels: 要解析的频道列表
            concurrency: 并发数（未实现，保留参数）

        Returns:
            解析结果列表
        """
        results = []

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return [{"channel": c.name, "pid": c.pid, "error": "请安装 playwright"} for c in channels]

        async with async_playwright() as pw:
            # 复用同一个浏览器实例
            launch_args = [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-setuid-sandbox",
                "--disable-infobars",
                "--disable-features=IsolateOrigins,site-per-process",
                "--disable-site-isolation-trials",
                "--autoplay-policy=no-user-gesture-required",
                "--disable-gpu",
                "--disable-software-rasterizer",
                "--single-process",  # CI 环境必需
            ]

            if self.browser_channel:
                browser = await pw.chromium.launch(
                    headless=self.headless,
                    channel=self.browser_channel,
                    args=launch_args,
                )
            else:
                # CI 环境使用 Playwright 内置 Chromium
                browser = await pw.chromium.launch(
                    headless=self.headless,
                    args=launch_args,
                    chromium_sandbox=False,  # 禁用沙箱以兼容 CI
                )

            for i, channel in enumerate(channels):
                logger.info(
                    f"[{i+1}/{len(channels)}] 正在解析 {channel.name} (pid={channel.pid})..."
                )
                result = await self._parse_one_with_browser(channel, browser)
                results.append(result)

                if "url" in result:
                    logger.info(f"  ✅ {channel.name} → {result['url'][:80]}...")
                else:
                    logger.warning(f"  ❌ {channel.name} → {result.get('error', 'unknown')}")

                # 频道间隔短暂休息，避免被 ban
                if i < len(channels) - 1:
                    await asyncio.sleep(0.5)

            await browser.close()

        return results

    async def parse_pids(self, pids: list[str]) -> list[dict]:
        """按 pid 列表解析"""
        channels = []
        for pid in pids:
            ch = get_channel_by_pid(pid)
            if ch:
                channels.append(ch)
            else:
                channels.append(Channel(name=pid, pid=pid, cnlid="", category="unknown"))
        return await self.parse_channels(channels)

    # ================================================================
    # 核心：单频道解析（复用浏览器）
    # ================================================================

    async def _parse_one_with_browser(self, channel: Channel, browser) -> dict:
        """解析单个频道（使用已有 browser 实例）"""
        urls: list[str] = []

        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/132.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
            locale="zh-CN",
            bypass_csp=True,
        )

        # 注入反检测脚本
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
            window.chrome = { runtime: {} };
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
            );
        """)

        page = await context.new_page()

        # playwright-stealth
        try:
            from playwright_stealth import Stealth
            stealth = Stealth()
            await stealth.apply_stealth_async(page)
        except Exception:
            pass

        # 拦截网络响应
        async def on_response(response):
            resp_url = response.url
            for pattern in _STREAM_PATTERNS:
                if pattern.search(resp_url):
                    urls.append(resp_url)
                    logger.debug(f"  📡 拦截: {resp_url[:100]}")
                    break

        page.on("response", on_response)

        # 加载 TV 页面
        tv_url = f"https://www.yangshipin.cn/tv/home?pid={channel.pid}"
        try:
            await page.goto(
                tv_url,
                wait_until="domcontentloaded",
                timeout=self.timeout * 1000,
            )
        except Exception as e:
            logger.debug(f"  页面加载: {e}")

        # 等待视频加载（卫视频道需要更长等待）
        await asyncio.sleep(self.wait_time)

        # 尝试点击播放按钮
        try:
            selectors = [
                'button[class*="play"]',
                '[class*="txp_btn_play"]',
                '[class*="play_btn"]',
                'video',
                '[class*="player"]',
                '.txp_player',
            ]
            for sel in selectors:
                el = await page.query_selector(sel)
                if el:
                    await el.click(timeout=2000)
                    await asyncio.sleep(2)
                    break
        except Exception:
            pass

        # 再等一会儿
        await asyncio.sleep(3)

        await context.close()

        # 处理结果
        if not urls:
            return {
                "channel": channel.name,
                "pid": channel.pid,
                "error": "未拦截到直播流 URL（页面可能要求Cookie或频道不在播放时段）",
            }

        # 去重
        seen = set()
        unique = []
        for u in urls:
            base = u.split("?")[0]
            if base not in seen:
                seen.add(base)
                unique.append(u)

        m3u8 = [u for u in unique if ".m3u8" in u]
        flv = [u for u in unique if ".flv" in u]
        best = (m3u8 or flv or unique)[0]
        protocol = "hls" if ".m3u8" in best else "flv"

        return {
            "channel": channel.name,
            "pid": channel.pid,
            "cnlid": channel.cnlid,
            "url": best,
            "protocol": protocol,
            "all_urls": unique,
        }

    # ================================================================
    # 播放列表导出
    # ================================================================

    @staticmethod
    def export_m3u(results: list[dict], path: str, group: str = "央视频"):
        """导出 M3U 格式"""
        from pathlib import Path

        lines = ["#EXTM3U"]
        for r in results:
            if "url" in r:
                lines.append(
                    f'#EXTINF:-1 group-title="{group}" tvg-name="{r["channel"]}",'
                    f'{r["channel"]}'
                )
                lines.append(r["url"])

        Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
        logger.info(f"📄 M3U 已导出: {path} ({len(lines) // 2} 个频道)")

        # 也保存一个简单的 txt 版本，方便 VLC 等播放器直接打开
        txt_path = path.replace(".m3u8", ".txt").replace(".m3u", ".txt")
        txt_lines = [r["url"] for r in results if "url" in r]
        Path(txt_path).write_text("\n".join(txt_lines), encoding="utf-8")

    @staticmethod
    def export_json(results: list[dict], path: str):
        """导出 JSON 格式"""
        import json
        from datetime import datetime
        from pathlib import Path

        output = {
            "generated_at": datetime.now().isoformat(),
            "source": "yangshipin.cn (Playwright browser interception)",
            "total": len(results),
            "success": sum(1 for r in results if "url" in r),
            "failed": sum(1 for r in results if "error" in r),
            "channels": results,
        }
        Path(path).write_text(
            json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.info(f"📄 JSON 已导出: {path}")

    @staticmethod
    def print_summary(results: list[dict]):
        """打印摘要"""
        success = [r for r in results if "url" in r]
        failed = [r for r in results if "error" in r]

        print("\n" + "=" * 70)
        print(f"  央视频直播地址解析结果  (成功: {len(success)}, 失败: {len(failed)})")
        print("=" * 70)

        if success:
            print(f"\n  ✅ 成功获取 {len(success)} 个频道:\n")
            for r in success:
                proto = r.get("protocol", "?").upper()
                url = r["url"]
                print(f"  {r['channel']:<24s} [{proto:4s}]  {url}")

        if failed:
            print(f"\n  ❌ 失败 {len(failed)} 个频道:\n")
            for r in failed:
                print(f"  {r['channel']:<24s}  {r['error']}")

        print("\n" + "=" * 70)
