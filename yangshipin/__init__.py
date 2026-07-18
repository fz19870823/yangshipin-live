"""
央视频 (yangshipin.cn) 直播流地址自动解析工具

支持全自动解析 https://www.yangshipin.cn/tv/home 中所有频道的直播流地址。
"""

from .parser import YangshipinParser

__version__ = "1.0.0"
__all__ = ["YangshipinParser"]
