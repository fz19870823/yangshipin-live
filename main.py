#!/usr/bin/env python
"""
央视频直播地址全自动解析工具

从 https://www.yangshipin.cn/tv/home 自动提取所有频道的直播流地址。

使用方法:
    # 解析 CCTV 核心频道（推荐首次使用）
    python main.py --category cctv

    # 解析单个频道
    python main.py --pid 600001859

    # 解析卫视频道
    python main.py --category satellite

    # 解析全部频道
    python main.py --category all

    # 导出 M3U 播放列表
    python main.py --category cctv --output-m3u cctv.m3u

    # 导出 JSON
    python main.py --category all --output-json channels.json

    # 显示浏览器窗口（非无头模式，便于调试）
    python main.py --pid 600001859 --visible

    # 查看频道列表
    python main.py --list-channels

    # CI 模式（GitHub Actions 自动更新）
    python main.py --ci
"""

import argparse
import asyncio
import logging
import sys

from yangshipin.browser import BrowserParser
from yangshipin.channels import (
    ALL_CHANNELS,
    CCTV_CHANNELS,
    Channel,
    get_channel_by_pid,
    get_channels_by_category,
)
from yangshipin.parser import YangshipinParser


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def cmd_list_channels():
    """列出所有可用频道"""
    categories = [
        ("CCTV 核心频道", CCTV_CHANNELS),
    ]
    # 简化：只列出 CCTV 频道
    print(f"\n{'─' * 60}")
    print(f"  CCTV 核心频道 ({len(CCTV_CHANNELS)} 个)")
    print(f"{'─' * 60}")
    for ch in CCTV_CHANNELS:
        print(f"  {ch.name:<28s}  pid={ch.pid}")
    print(f"\n  使用 --category cctv 解析以上频道")
    print(f"  使用 --category all  解析所有频道 (CCTV+CGTN+卫视+付费)")
    print(f"{'─' * 60}\n")


def cmd_parse(args):
    """执行解析"""
    parser = YangshipinParser(
        cookie=args.cookie or "",
        timeout=args.timeout,
        headless=not args.visible,
        browser_channel=args.browser,
    )

    # 确定要解析的频道
    if args.pid:
        pids = [args.pid]
        channel = get_channel_by_pid(args.pid)
        name = channel.name if channel else args.pid
        print(f"\n📺 解析频道: {name} (pid={args.pid})")
        category_label = ""
    else:
        pids = None
        category_label = f" (分类: {args.category})"
        if args.category == "all":
            channels = ALL_CHANNELS
        else:
            channels = get_channels_by_category(args.category)

        if args.category == "cctv":
            channels = CCTV_CHANNELS
        elif args.category != "all":
            channels = get_channels_by_category(args.category)

        # 按实际使用的 channels 来显示
        display_channels = (
            CCTV_CHANNELS if args.category == "cctv"
            else get_channels_by_category(args.category) if args.category != "all"
            else ALL_CHANNELS
        )
        print(f"\n📺 解析 {len(display_channels)} 个频道{category_label}")
        print("   (使用 Playwright 浏览器拦截方式)\n")

    # 执行解析
    results = parser.parse_browser_sync(category=args.category, pids=pids)

    # 打印结果
    BrowserParser.print_summary(results)

    # 导出
    if args.output_m3u:
        BrowserParser.export_m3u(results, args.output_m3u)
    if args.output_json:
        BrowserParser.export_json(results, args.output_json)

    # 如果没有输出文件，保存一个默认的 m3u
    if not args.output_m3u and not args.output_json:
        success = [r for r in results if "url" in r]
        if success:
            default_path = "yangshipin_channels.m3u"
            BrowserParser.export_m3u(results, default_path)
            print(f"\n💡 直播源已自动保存到: {default_path}")
            print(f"   可用 VLC、PotPlayer、IINA 等播放器打开此文件")


def cmd_ci(args):
    """CI 模式：自动运行 CCTV + 卫视，输出到 output/ 目录"""
    import os
    import sys as _sys

    output_dir = args.output_dir or "output"
    os.makedirs(output_dir, exist_ok=True)

    categories = ["cctv", "satellite"]
    all_results = []
    exit_code = 0

    for cat in categories:
        print(f"\n{'=' * 60}")
        print(f"  CI: 正在解析 {cat} 频道...")
        print(f"{'=' * 60}")

        parser = YangshipinParser(
            cookie=args.cookie or "",
            timeout=60,  # CI 环境网络可能较慢，增加超时时间
            headless=True,
            # CI 环境没有系统浏览器，使用 Playwright 内置 Chromium
            browser_channel=None,
        )

        try:
            results = parser.parse_browser_sync(category=cat, pids=None)
            all_results.extend(results)

            # 打印摘要
            success = [r for r in results if "url" in r]
            failed = [r for r in results if "error" in r]
            print(f"  {cat}: 成功 {len(success)} / 失败 {len(failed)}")

            # 导出 M3U
            m3u_path = os.path.join(output_dir, f"{cat}.m3u")
            if success:  # 只有成功的才导出
                BrowserParser.export_m3u(results, m3u_path, group=cat.upper())
                print(f"  ✅ {cat}.m3u 已生成: {len(success)} 个频道")
            else:
                print(f"  ⚠️  {cat} 分类没有成功的频道，跳过 M3U 导出")

            # 导出 JSON
            json_path = os.path.join(output_dir, f"{cat}.json")
            BrowserParser.export_json(results, json_path)
            print(f"  ✅ {cat}.json 已生成")

            if failed:
                exit_code = 1
                
        except Exception as e:
            print(f"  ❌ 解析 {cat} 时出错: {e}")
            import traceback
            traceback.print_exc()
            exit_code = 1

    # 导出合并的汇总 JSON
    import json
    from datetime import datetime
    summary_path = os.path.join(output_dir, "summary.json")
    summary = {
        "generated_at": datetime.now().isoformat(),
        "source": "yangshipin.cn (GitHub Actions CI)",
        "total": len(all_results),
        "success": sum(1 for r in all_results if "url" in r),
        "failed": sum(1 for r in all_results if "error" in r),
    }
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"\n📊 汇总已保存: {summary_path}")
    print(f"   总计 {summary['total']} 个频道，成功 {summary['success']}，失败 {summary['failed']}")
    
    # 即使有失败也不退出报错，只要有成功的就算成功
    if summary['success'] > 0:
        print(f"\n✅ CI 任务完成: {summary['success']}/{summary['total']} 频道成功")
        _sys.exit(0)
    else:
        print(f"\n❌ CI 任务失败: 所有频道均失败")
        _sys.exit(1)


def main():
    ap = argparse.ArgumentParser(
        description="央视频直播地址全自动解析工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py --category cctv              # 解析所有 CCTV 频道（推荐）
  python main.py --pid 600001859              # 解析单个频道
  python main.py --category satellite         # 解析卫视频道
  python main.py --category all               # 解析全部频道
  python main.py --category cctv --output-m3u tv.m3u    # 导出M3U
  python main.py --pid 600001859 --visible    # 显示浏览器窗口调试
  python main.py --list-channels              # 列出可用频道

依赖安装:
  pip install requests pycryptodome playwright
  playwright install chromium
        """,
    )

    ap.add_argument("--category", "-c",
                    choices=["cctv", "cgtn", "satellite", "premium", "all"],
                    default="cctv", help="频道分类 (默认: cctv)")
    ap.add_argument("--pid", help="解析单个频道 (传入 pid，如 600001859)")
    ap.add_argument("--cookie", help="央视频登录 Cookie (可选，登录后可获更高清流)")
    ap.add_argument("--timeout", type=int, default=30, help="页面加载超时秒数 (默认: 30)")
    ap.add_argument("--visible", action="store_true",
                    help="显示浏览器窗口 (调试用)")
    ap.add_argument("--browser", default="chrome",
                    choices=["chrome", "msedge"],
                    help="使用的浏览器 (默认: chrome)")
    ap.add_argument("--output-m3u", help="导出 M3U 播放列表到指定路径")
    ap.add_argument("--output-json", help="导出 JSON 结果到指定路径")
    ap.add_argument("--list-channels", action="store_true", help="列出所有可用频道")
    ap.add_argument("--ci", action="store_true",
                    help="CI 模式：自动解析 CCTV+卫视，输出到 output/ 目录，使用 Playwright 内置 Chromium")
    ap.add_argument("--output-dir", default="output",
                    help="CI 模式输出目录 (默认: output)")
    ap.add_argument("--verbose", "-v", action="store_true", help="详细日志")

    args = ap.parse_args()

    setup_logging(args.verbose)

    if args.list_channels:
        cmd_list_channels()
    elif args.ci:
        cmd_ci(args)
    else:
        cmd_parse(args)


if __name__ == "__main__":
    main()
