"""
央视频直播地址浏览器拦截解析器 V2 (Playwright + 单页面频道切换)

这是目前最可靠的解析方式。
通过 Playwright 无头浏览器加载央视频 TV 页面，
自动拦截网络请求中的 m3u8/flv 直播流地址。

原理：
1. 启动 Chromium 浏览器，创建单个 page 供所有频道复用
2. 加载 https://www.yangshipin.cn/tv/home?pid=XXXX
3. 页面 JavaScript 自动生成有效的 cKey 并请求流地址
4. 全局网络拦截器收集所有频道的直播流 URL
5. 首个频道固定等待；后续频道点击切换后智能检测地址变化

V2 优化:
- 单 page 复用，避免重复创建 context
- 智能地址检测：后续频道循环检测新 URL，一旦变化立即保存并切换
- 防止网络慢导致相邻频道抓到相同地址
"""

import asyncio
import logging
import re
import sys
from typing import Optional

try:
    from .channels import Channel, get_channel_by_pid, ALL_CHANNELS
except ImportError:
    # 独立运行时（测试脚本）的回退导入
    from channels import Channel, get_channel_by_pid, ALL_CHANNELS

logger = logging.getLogger(__name__)

# 直播流 URL 匹配规则
_STREAM_PATTERNS = [
    re.compile(r"https?://[^\s\"'<>]+\.m3u8[^\s\"'<>]*", re.IGNORECASE),
    re.compile(r"https?://[^\s\"'<>]+\.flv[^\s\"'<>]*", re.IGNORECASE),
    re.compile(r"https?://[^\s\"'<>]+/live/[^\s\"'<>]+\.(?:m3u8|flv)", re.IGNORECASE),
    # als (= apple live streaming) 格式
    re.compile(r"https?://[^\s\"'<>]+\.als[^\s\"'<>]*", re.IGNORECASE),
]


class BrowserParserV2:
    """基于浏览器的直播流拦截解析器 V2 (单页面切换频道)

    默认使用系统已安装的 Chrome 浏览器（无需额外下载 Chromium）。
    也支持 Edge 浏览器。

    V2 核心优化:
    - 单 page 复用所有频道
    - 智能地址检测：后续频道循环检测新 URL 变化
    - 防止重复地址
    """

    def __init__(
        self,
        headless: bool = True,
        timeout: int = 30,
        wait_time: float = 8.0,
        browser_channel: str = "chrome",
        single_process: bool = False,
    ):
        """
        Args:
            headless: 是否无头模式
            timeout: 超时秒数
            wait_time: 等待流加载时间
            browser_channel: 浏览器类型 ("chrome" | "msedge" | None=Playwright内置Chromium)
            single_process: 是否使用单进程模式（CI 环境可能需要，但会降低稳定性）
        """
        self.headless = headless
        self.timeout = timeout
        self.wait_time = wait_time
        self.browser_channel = browser_channel
        self.single_process = single_process

    # ================================================================
    # 主入口
    # ================================================================

    async def parse_channels(
        self,
        channels: list[Channel],
        concurrency: int = 1,
    ) -> list[dict]:
        """
        解析频道列表的直播流地址（单页面切换频道 + 智能地址检测）

        核心优化：
        - 单个 page 复用，通过点击频道按钮切换，避免每次新建 context
        - 首个频道固定等待 wait_time 秒
        - 后续频道点击后循环检测，一旦拦截到与上一频道不同的新地址，立即保存并切换
        - 防止网络慢导致重复地址

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
            ]
            if self.single_process:
                launch_args.append("--single-process")

            if self.browser_channel:
                browser = await pw.chromium.launch(
                    headless=self.headless,
                    channel=self.browser_channel,
                    args=launch_args,
                )
            else:
                browser = await pw.chromium.launch(
                    headless=self.headless,
                    args=launch_args,
                    chromium_sandbox=False,
                )

            # 创建单个 context 和 page，所有频道复用
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

            try:
                from playwright_stealth import Stealth
                stealth = Stealth()
                await stealth.apply_stealth_async(page)
            except Exception:
                pass

            # 全局拦截器：收集所有频道的直播流 URL
            all_intercepted_urls: list[str] = []

            async def on_response(response):
                resp_url = response.url
                for pattern in _STREAM_PATTERNS:
                    if pattern.search(resp_url):
                        all_intercepted_urls.append(resp_url)
                        logger.info(f"  🎯 拦截到流URL: {resp_url[:120]}")
                        break

            page.on("response", on_response)

            # 加载首个频道页面
            if channels:
                first_url = f"https://www.yangshipin.cn/tv/home?pid={channels[0].pid}"
                try:
                    await page.goto(
                        first_url,
                        wait_until="load",
                        timeout=self.timeout * 1000,
                    )
                    # 等待 Vue 渲染频道列表
                    await asyncio.sleep(2)
                    logger.info(f"  🌐 页面已加载: {first_url}")
                except Exception as e:
                    logger.warning(f"  ⚠️ 页面加载异常: {e}")

            # 首个频道的 stream URL 在 page.goto 期间已被拦截
            logger.info(f"  📡 全局拦截器已就绪，开始解析 {len(channels)} 个频道")

            previous_url = None

            for i, channel in enumerate(channels):
                logger.info(
                    f"[{i+1}/{len(channels)}] 正在解析 {channel.name} (pid={channel.pid})..."
                )

                # 首个频道：page.goto 期间拦截到的 URL 就是它的，start_count=0
                # 后续频道：用当前 len 作基线，排除前面所有频道的 URL
                start_count = 0 if i == 0 else len(all_intercepted_urls)
                is_first = (i == 0)

                result = await self._parse_one_channel(
                    page, channel, previous_url,
                    all_intercepted_urls, start_count, is_first,
                )
                results.append(result)

                if "url" in result:
                    logger.info(
                        f"  ✅ {channel.name} → {result['url'][:80]}..."
                    )
                    previous_url = result["url"]
                else:
                    logger.warning(
                        f"  ❌ {channel.name} → {result.get('error', 'unknown')}"
                    )

                # 频道间隔短暂休息
                if i < len(channels) - 1:
                    await asyncio.sleep(0.3)

            await context.close()
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
    # 核心：单频道解析（复用 page，通过点击频道按钮切换）
    # ================================================================

    async def _parse_one_channel(
        self,
        page,
        channel: Channel,
        previous_url: str | None,
        all_intercepted_urls: list[str],
        start_count: int,
        is_first: bool,
    ) -> dict:
        """解析单个频道（复用已有 page，点击频道按钮切换）

        优化逻辑：
        - 首个频道 (is_first=True): 页面已加载，固定等待 wait_time
        - 后续频道: 点击频道按钮后循环检测地址变化，一旦拦截到新地址立即返回

        Args:
            page: 复用的浏览器页面
            channel: 要解析的频道
            previous_url: 上一个频道的 URL（首个为 None）
            all_intercepted_urls: 全局拦截到的所有 URL 列表
            start_count: 本次点击前 all_intercepted_urls 的长度
            is_first: 是否第一个频道
        """

        if not is_first:
            # 点击频道切换按钮
            await self._click_channel_btn(page, channel)

        if is_first:
            # 第一个频道：固定等待
            logger.debug(f"  首个频道，固定等待 {self.wait_time}s...")
            logger.info(f"  ⏳ 首个频道等待 {self.wait_time}s...")
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

            await asyncio.sleep(2)
        else:
            # 后续频道：智能等待，检测到新地址立即返回
            max_wait = 15.0   # 最多等 15 秒
            check_interval = 0.2   # 每 200ms 检查一次
            waited = 0.0

            logger.info(
                f"  ⏳ 智能等待 (max={max_wait}s), "
                f"对比上一频道 URL: {previous_url[:60] if previous_url else 'N/A'}..."
            )
            prev_base = previous_url.split("?")[0] if previous_url else ""

            new_url_found = False
            while waited < max_wait:
                await asyncio.sleep(check_interval)
                waited += check_interval

                # 检查本次点击后新拦截到的 URL
                for url in all_intercepted_urls[start_count:]:
                    base_url = url.split("?")[0]
                    if base_url != prev_base:
                        new_url_found = True
                        break

                if new_url_found:
                    logger.debug(f"  检测到新地址，耗时 {waited:.1f}s")
                    break

            if not new_url_found:
                logger.info(f"  ⏱️ 等待 {max_wait}s 未检测到新地址（当前总流URL={len(all_intercepted_urls)}）")

        # 从全局列表中提取本次频道的 URL
        channel_urls = all_intercepted_urls[start_count:]

        # 去重 + 提取结果
        return self._extract_result(channel, channel_urls, previous_url)

    async def _click_channel_btn(self, page, channel: Channel):
        """点击频道列表按钮切换频道（SPA 内部跳转）

        频道名在 span 中（如 <span>CCTV1</span>），位于横向滚动列表
        .tv-main-con-r-list-left 内。点击父 DIV 触发 Vue SPA 切换。
        """
        short_name = channel.name.split()[0].replace("-", "")
        logger.info(f"  🔄 切换 → {channel.name} (匹配: {short_name})")

        # 策略1: Playwright get_by_text（自动处理滚动，最推荐）
        try:
            el = page.get_by_text(short_name, exact=True).first
            if await el.is_visible():
                await el.click(timeout=3000)
                await asyncio.sleep(0.8)
                logger.info(f"  ✅ get_by_text({short_name})")
                return
        except Exception:
            pass

        # 策略2: 标准文本选择器
        selectors = [
            f'text="{short_name}"',
            f'span:text-is("{short_name}")',
            f'span:has-text("{short_name}")',
            f'div:text-is("{short_name}")',
        ]
        for sel in selectors:
            try:
                el = await page.wait_for_selector(sel, timeout=2000)
                if el:
                    await el.scroll_into_view_if_needed()
                    await el.click(timeout=3000)
                    await asyncio.sleep(0.8)
                    logger.info(f"  ✅ 选择器({sel})")
                    return
            except Exception:
                continue

        # 策略3: JS 遍历 + 滚动到可见
        clicked = await page.evaluate("""
            (short) => {
                const norm = short.replace(/[\\s-]/g, '').toLowerCase();
                const divs = document.querySelectorAll(
                    '.tv-main-con-r-list-left-imga'
                );
                for (const d of divs) {
                    const text = (d.textContent || '').trim().replace(/[\\s-]/g, '').toLowerCase();
                    if (text === norm || text.includes(norm)) {
                        d.scrollIntoView({ behavior: 'instant', block: 'nearest' });
                        d.click();
                        return 'clicked:' + d.textContent.trim().substring(0, 20);
                    }
                }
                // 后备：搜索所有 span
                const spans = document.querySelectorAll('span');
                for (const s of spans) {
                    const t = (s.textContent || '').trim().replace(/[\\s-]/g, '').toLowerCase();
                    if (t === norm) {
                        s.scrollIntoView({ behavior: 'instant', block: 'nearest' });
                        s.click();
                        return 'span:' + s.textContent.trim().substring(0, 20);
                    }
                }
                return 'not_found';
            }
        """, short_name)

        if clicked and clicked != "not_found":
            logger.info(f"  ✅ JS点击({clicked})")
            await asyncio.sleep(0.8)
            return

        logger.warning(f"  ⚠️ 未找到 {short_name} 按钮")

    def _extract_result(
        self, channel: Channel, urls: list[str], previous_url: str | None
    ) -> dict:
        """从拦截到的 URL 列表中提取最佳结果

        如果 previous_url 不为 None，优先选择与上一频道不同的地址
        """
        if not urls:
            return {
                "channel": channel.name,
                "pid": channel.pid,
                "error": "未拦截到直播流 URL（页面可能要求Cookie或频道不在播放时段）",
            }

        # 去重（基于基础 URL）
        seen = set()
        unique = []
        for u in urls:
            base = u.split("?")[0]
            if base not in seen:
                seen.add(base)
                unique.append(u)

        # 如果有上一频道地址，优先选不同的
        prev_base = previous_url.split("?")[0] if previous_url else ""
        different = [u for u in unique if u.split("?")[0] != prev_base]

        candidates = different if different else unique

        m3u8 = [u for u in candidates if ".m3u8" in u]
        flv = [u for u in candidates if ".flv" in u]
        best = (m3u8 or flv or candidates)[0]
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
