"""Shared browser used to capture decrypted media segments from Yangshipin."""

import asyncio
import logging
from typing import Iterable

from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)


class SharedBrowserManager:
    """One browser/page shared by all active local HLS outputs."""

    def __init__(self):
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._current = ""
        self._media_offset = 0
        self._init_cache: dict[str, dict[str, bytes]] = {}
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            channel="chrome",
            args=[
                "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage",
                "--mute-audio", "--autoplay-policy=no-user-gesture-required",
            ],
        )
        self._context = await self._browser.new_context(viewport={"width": 960, "height": 540})
        await self._context.add_init_script("""
            window._yspVideoInit = null;
            window._yspAudioInit = null;
            window._yspMediaChunks = [];
            const original = MediaSource.prototype.addSourceBuffer;
            MediaSource.prototype.addSourceBuffer = function(mime) {
                const sourceBuffer = original.call(this, mime);
                const append = sourceBuffer.appendBuffer;
                let first = true;
                sourceBuffer.appendBuffer = function(data) {
                    const bytes = new Uint8Array(data);
                    if (first) {
                        if (mime.includes('video')) window._yspVideoInit = bytes;
                        else if (mime.includes('audio')) window._yspAudioInit = bytes;
                        first = false;
                    } else {
                        window._yspMediaChunks.push(bytes);
                    }
                    return append.call(this, data);
                };
                return sourceBuffer;
            };
        """)
        self._page = await self._context.new_page()

    async def switch_channel(self, name: str, pid: str) -> None:
        """Navigate to a channel and cache its initial fMP4 boxes."""
        async with self._lock:
            if self._current == name and name in self._init_cache:
                return
            await self._page.goto(
                f"https://www.yangshipin.cn/tv/home?pid={pid}",
                wait_until="commit", timeout=30_000,
            )
            self._current = name
            self._media_offset = 0
            for _ in range(100):
                ready = await self._page.evaluate(
                    "() => !!window._yspVideoInit && !!window._yspAudioInit"
                )
                if ready:
                    break
                await asyncio.sleep(0.2)
            else:
                raise TimeoutError(f"Timed out waiting for media initialization: {name}")

            video, audio = await self._page.evaluate("""() => [
                Array.from(window._yspVideoInit), Array.from(window._yspAudioInit)
            ]""")
            self._init_cache[name] = {"v": bytes(video), "a": bytes(audio)}
            self._media_offset = await self._page.evaluate("() => window._yspMediaChunks.length")
            logger.info("Channel ready: %s (video=%dB, audio=%dB)", name, len(video), len(audio))

    def get_init_data(self) -> tuple[bytes, bytes]:
        cached = self._init_cache.get(self._current, {})
        return cached.get("v", b""), cached.get("a", b"")

    def feed_init_to_ffmpeg(self, process, name: str) -> bool:
        cached = self._init_cache.get(name)
        if not cached or process.stdin is None:
            return False
        process.stdin.write(cached["v"])
        process.stdin.write(cached["a"])
        process.stdin.flush()
        return True

    async def get_media_chunks(self) -> list[bytes]:
        if not self._page or self._page.is_closed():
            return []
        try:
            chunks = await asyncio.wait_for(self._page.evaluate(
                """(offset) => window._yspMediaChunks.slice(offset).map(
                    item => Array.from(item)
                )""", self._media_offset), timeout=2.0)
            self._media_offset += len(chunks)
            return [bytes(chunk) for chunk in chunks]
        except Exception as exc:
            logger.warning("Failed to read media chunks: %s", exc)
            return []

    async def prewarm_channels(self, channels: Iterable[dict]) -> None:
        for channel in channels:
            try:
                await self.switch_channel(channel["name"], channel["pid"])
            except Exception as exc:
                logger.warning("Unable to prewarm %s: %s", channel["name"], exc)

    async def close(self) -> None:
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()


async def get_browser_manager() -> SharedBrowserManager:
    if not hasattr(get_browser_manager, "_instance"):
        manager = SharedBrowserManager()
        await manager.start()
        get_browser_manager._instance = manager
    return get_browser_manager._instance


async def close_browser_manager() -> None:
    """Close the singleton browser during application shutdown."""
    manager = getattr(get_browser_manager, "_instance", None)
    if manager is not None:
        await manager.close()
        delattr(get_browser_manager, "_instance")
