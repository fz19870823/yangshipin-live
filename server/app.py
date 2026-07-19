"""
CMG 解密 HLS 推流服务器

架构: 单浏览器多频道共享
- 一个 headless Chrome 实例，CMG 模块初始化一次
- 频道切换通过 DOM 点击，~1秒完成
- 按需启动 ffmpeg 转码 TS
- 每天0点+每6h刷新直播 URL
"""

import asyncio
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

from aiohttp import web

HERE = Path(__file__).parent
PROJECT_ROOT = HERE.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from server.url_store import get_store
from server.shared_browser import close_browser_manager, get_browser_manager

logger = logging.getLogger(__name__)

OUTPUT_ROOT = Path(os.environ.get("CMG_OUTPUT_DIR", PROJECT_ROOT / "live_output"))
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

# 活跃的 ffmpeg 进程: channel_name → subprocess.Popen
_ffmpeg_procs: dict[str, subprocess.Popen] = {}
_ffmpeg_tasks: dict[str, asyncio.Task] = {}
_active_channels: dict[str, float] = {}
IDLE_TIMEOUT = 300  # 5 minute


def _safe(name: str) -> str:
    return name.replace(" ", "_").replace("(", "").replace(")", "").replace("+", "P")


def _find_channel(safe: str) -> str | None:
    for c in get_store().get_channels():
        if _safe(c["name"]) == safe:
            return c["name"]
    return None


# ---- HTTP handlers ----

async def handle_channels(request: web.Request) -> web.Response:
    store = get_store()
    channels = store.get_channels()
    urls = store.get_all()
    last = store.get_last_refresh()

    return web.json_response({
        "total": len(channels),
        "with_url": len(urls),
        "last_refresh": last.isoformat() if last else None,
        "active_workers": len(_active_channels),
        "channels": [
            {
                "name": c["name"],
                "pid": c["pid"],
                "has_url": c["has_url"],
                "active": c["name"] in _active_channels,
                "hls_url": f"/live/{_safe(c['name'])}/index.m3u8",
            }
            for c in channels
        ],
    })


async def handle_live(request: web.Request) -> web.Response:
    safe = request.match_info["channel"]
    filename = request.match_info["filename"]
    name = _find_channel(safe)
    if not name:
        raise web.HTTPNotFound(text=f"Unknown channel: {safe}")

    store = get_store()
    pid = None
    for ch in store.get_channels():
        if ch["name"] == name:
            pid = ch["pid"]
            break
    if not pid:
        raise web.HTTPNotFound(text=f"No PID for: {name}")

    # 确保该频道正在推流
    if name not in _ffmpeg_procs:
        await _start_channel(name, pid)

    _active_channels[name] = time.time()

    # 等待文件出现
    for _ in range(50):
        path = OUTPUT_ROOT / _safe(name) / filename
        if path.exists():
            return web.FileResponse(path)
        await asyncio.sleep(0.2)

    raise web.HTTPNotFound(text=f"File {filename} not ready")


async def handle_health(request: web.Request) -> web.Response:
    return web.json_response({
        "status": "ok",
        "channels": len(_active_channels),
        "ffmpeg": len(_ffmpeg_procs),
    })


# ---- Channel lifecycle ----

async def _start_channel(name: str, pid: str):
    """启动频道：立即用缓存 init 启动 ffmpeg，浏览器并行切换"""
    out_dir = OUTPUT_ROOT / _safe(name)
    out_dir.mkdir(parents=True, exist_ok=True)

    m3u8 = str(out_dir / "index.m3u8")
    seg = str(out_dir / "seg_%03d.ts")

    proc = subprocess.Popen([
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-f", "mp4", "-i", "pipe:0",
        "-c", "copy",
        "-f", "hls", "-hls_time", "3", "-hls_list_size", "6",
        "-hls_flags", "delete_segments+append_list",
        "-hls_segment_filename", seg, m3u8,
    ], stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)

    # 立即用缓存 init 写入 ffmpeg（不等待浏览器）
    bm = await get_browser_manager()
    if not bm.feed_init_to_ffmpeg(proc, name):
        # 缓存未命中：回退到等待浏览器
        await bm.switch_channel(name, pid)
        vi, ai = bm.get_init_data()
        proc.stdin.write(vi)
        proc.stdin.write(ai)
        proc.stdin.flush()
        # 缓存起来
        bm._init_cache[name] = {"v": vi, "a": ai}
    else:
        # 异步切换浏览器（不阻塞客户端请求）
        asyncio.create_task(bm.switch_channel(name, pid))

    _ffmpeg_procs[name] = proc
    _active_channels[name] = time.time()

    async def feed():
        while name in _ffmpeg_procs:
            try:
                chunks = await bm.get_media_chunks()
                for c in chunks:
                    if name in _ffmpeg_procs:
                        try:
                            _ffmpeg_procs[name].stdin.write(c)
                        except Exception:
                            break
                if chunks:
                    try:
                        _ffmpeg_procs[name].stdin.flush()
                    except Exception:
                        break
            except Exception as e:
                logger.error(f"[{name}] feed error: {e}")
            await asyncio.sleep(0.3)

    _ffmpeg_tasks[name] = asyncio.create_task(feed())
    logger.info(f"✅ 频道启动: {name}")


async def _stop_channel(name: str):
    """停止频道：关闭 ffmpeg"""
    proc = _ffmpeg_procs.pop(name, None)
    task = _ffmpeg_tasks.pop(name, None)
    _active_channels.pop(name, None)

    if task:
        task.cancel()
    if proc:
        try:
            proc.stdin.close()
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
    logger.info(f"♻️ 频道回收: {name}")


async def _idle_cleanup():
    while True:
        await asyncio.sleep(60)
        now = time.time()
        for name, at in list(_active_channels.items()):
            if now - at > IDLE_TIMEOUT:
                await _stop_channel(name)


# ---- Startup ----

async def on_startup(app: web.Application):
    """服务器启动：注册 URL 刷新回调 → 预热浏览器 → 启动定时器"""
    def _on_url_refresh(channels):
        """URL 刷新后异步预热所有频道 init"""
        asyncio.ensure_future(_rewarm(channels))

    store = get_store(_on_url_refresh)
    store.start_scheduler(interval_seconds=21600)

    asyncio.create_task(_idle_cleanup())
    asyncio.create_task(_prewarm_browser())

    logger.info("服务器已启动")


async def _rewarm(channels: list):
    """URL 刷新后重新预热"""
    try:
        bm = await get_browser_manager()
        await bm.prewarm_channels(channels)
    except Exception as e:
        logger.warning(f"重新预热失败: {e}")


async def _prewarm_browser():
    """预热：初始化浏览器 + 遍历所有频道缓存 init 段"""
    try:
        store = get_store()
        channels = [
            {"name": c["name"], "pid": c["pid"]}
            for c in store.get_channels()
            if c["has_url"]
        ]
        if channels:
            bm = await get_browser_manager()
            await bm.prewarm_channels(channels)
    except Exception as e:
        logger.warning(f"预热失败: {e}")


async def on_cleanup(app: web.Application):
    for name in list(_ffmpeg_procs):
        await _stop_channel(name)
    await close_browser_manager()


def create_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/api/channels", handle_channels)
    app.router.add_get("/api/health", handle_health)
    app.router.add_get("/live/{channel}/{filename:.*}", handle_live)
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    return app


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    web.run_app(create_app(), host="0.0.0.0", port=8080)
