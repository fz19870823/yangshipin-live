# 央视频直播地址解析工具

从 [央视频](https://www.yangshipin.cn/tv/home) 自动提取所有频道的直播流地址，支持导出 M3U 播放列表。

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt
playwright install chromium

# 解析 CCTV 核心频道（推荐首次使用）
python main.py --category cctv

# 解析卫视频道
python main.py --category satellite

# 解析全部频道
python main.py --category all

# 导出 M3U 播放列表
python main.py --category cctv --output-m3u cctv.m3u

# 导出 JSON
python main.py --category all --output-json channels.json
```

## 使用说明

```
python main.py --category {cctv|cgtn|satellite|premium|all}
python main.py --pid 600001859          # 解析单个频道
python main.py --list-channels          # 列出可用频道
python main.py --pid 600001859 --visible  # 显示浏览器窗口（调试用）
```

| 参数 | 说明 |
|------|------|
| `--category, -c` | 频道分类：cctv / cgtn / satellite / premium / all |
| `--pid` | 解析指定频道（传入频道 pid）|
| `--cookie` | 登录 Cookie（可选，登录后可获取更高质量流）|
| `--timeout` | 页面加载超时秒数（默认 30）|
| `--visible` | 显示浏览器窗口，方便调试 |
| `--browser` | 浏览器选择：chrome / msedge |
| `--output-m3u` | 导出 M3U 播放列表 |
| `--output-json` | 导出 JSON 结果 |
| `--list-channels` | 列出所有可用频道 |
| `--verbose, -v` | 详细日志 |

生成的 M3U 文件可用 VLC、PotPlayer、IINA 等播放器直接打开。

## 依赖

- Python 3.8+
- requests
- pycryptodome
- playwright（Chromium 浏览器自动化）

## 许可证

MIT License
