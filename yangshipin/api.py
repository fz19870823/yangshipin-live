"""
央视频直播流 API 解析器 (实验性)

通过模拟央视频 API 请求，获取直播流的真实播放地址。
注意：cKey 算法可能随时变化，建议使用浏览器模式获得更可靠的解析结果。

API 端点: GET https://liveinfo.yangshipin.cn/
鉴权方式: cKey 签名
"""

import logging
import time

import requests

from .channels import Channel
from .ckey import generate_ckey, generate_flowid

logger = logging.getLogger(__name__)

_API_URL = "https://liveinfo.yangshipin.cn/"
_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/16.0 Mobile/15E148 Safari/604.1"
)

_DEFN_MAP = {
    "auto": "auto", "hd": "hd", "sd": "sd",
    "fhd": "fhd", "uhd": "uhd",
}


class YangshipinAPI:
    """央视频直播流 API 客户端 (实验性)"""

    def __init__(self, cookie: str = "", timeout: int = 15):
        self.cookie = cookie
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": _USER_AGENT,
            "Referer": "https://m.yangshipin.cn/",
        })

    def _build_params(self, channel: Channel, defn: str = "auto") -> dict:
        ts = int(time.time())
        return {
            "cmd": 2, "cnlid": channel.cnlid, "pla": 0, "stream": 2,
            "system": 1, "appVer": "3.0.37", "encryptVer": "8.1",
            "qq": 0, "device": "PC", "guid": "ko7djb70_vbjvrg5gcm",
            "defn": _DEFN_MAP.get(defn, defn), "host": "yangshipin.cn",
            "livepid": channel.pid, "logintype": 1, "vip_status": 1,
            "livequeue": 1, "fntick": ts, "tm": ts,
            "sdtfrom": 113, "platform": 4330701,
            "cKey": generate_ckey(channel.cnlid, ts),
            "queueStatus": 0, "uhd_flag": 4,
            "flowid": generate_flowid(), "sphttps": 1,
        }

    def get_stream_url(self, channel: Channel, defn: str = "auto") -> dict:
        """获取单个频道的直播流地址"""
        params = self._build_params(channel, defn)
        headers = {"Cookie": self.cookie} if self.cookie else {}

        try:
            resp = self.session.get(
                _API_URL, params=params, headers=headers, timeout=self.timeout
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            return {"channel": channel.name, "pid": channel.pid, "error": str(e)}

        # 新 API 可能返回多种格式
        play_url = data.get("playurl")
        if play_url:
            return {
                "channel": channel.name, "pid": channel.pid,
                "cnlid": channel.cnlid, "url": play_url,
                "defn": defn,
                "protocol": "hls" if ".m3u8" in play_url else "flv",
            }

        # 兼容新格式: iretcode / errinfo
        iretcode = data.get("iretcode")
        errinfo = data.get("errinfo", data.get("message", "未知错误"))
        if iretcode is not None:
            logger.warning(
                f"[{channel.name}] API 返回 iretcode={iretcode}, errinfo={errinfo}"
            )
            return {
                "channel": channel.name, "pid": channel.pid,
                "cnlid": channel.cnlid,
                "error": f"iretcode={iretcode}: {errinfo}",
            }

        # 兼容旧格式
        code = data.get("code", data.get("ret"))
        msg = data.get("msg", data.get("message", str(data)[:100]))
        return {
            "channel": channel.name, "pid": channel.pid,
            "cnlid": channel.cnlid,
            "error": f"code={code}: {msg}",
        }

    def get_all_streams(
        self, channels: list[Channel], defn: str = "auto"
    ) -> list[dict]:
        results = []
        for ch in channels:
            logger.info(f"正在获取 [{ch.name}] ...")
            results.append(self.get_stream_url(ch, defn))
        return results
