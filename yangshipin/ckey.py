"""
央视频 cKey 签名算法实现

cKey 是央视频 API 的核心鉴权参数，通过 AES-CBC 加密生成。
算法逆向自央视频 Web 前端 JavaScript 代码。

cKey 生成流程：
1. 构造签名字符串 wu: |{cnlid}|{timestamp}|{jc}|{version}|{guid}|{platform}|{referer}|{ua}|
2. 计算 Java 风格 hashcode，拼接到 wu 前面得到 xu
3. 对 xu 做 AES-128-CBC + PKCS7 加密
4. 输出 "--01" + hex_upper 格式
"""

import binascii
import ctypes
import time
import uuid

from Crypto.Cipher import AES

# ============================================================
# AES 密钥 (从央视频 JS 中提取的硬编码值)
# ============================================================
_AES_KEY = binascii.a2b_hex("4E2918885FD98109869D14E0231A0BF4")
_AES_IV  = binascii.a2b_hex("16B17E519DDD0CE5B79D7A63A4DD801C")

# ============================================================
# 固定参数
# ============================================================
_PLATFORM = 4330701        # PC Web 平台标识
_GUID = "ko7djb70_vbjvrg5gcm"  # 设备 GUID
_VERSION = "3.0.37"        # 客户端版本
_JC = "mg3c3b04ba"         # 固定密钥常量
_REFERER = "https://m.yangshipin.cn/"
_USER_AGENT = (
    "mozilla/5.0 (iphone; cpu||Mozilla|Netscape|Win32|"
)


def _aes_encrypt(text: str) -> str:
    """AES-128-CBC + PKCS7 加密，返回 hex 字符串"""
    # PKCS7 填充
    pad_len = 16 - len(text) % 16
    text = text + chr(pad_len) * pad_len

    cipher = AES.new(_AES_KEY, AES.MODE_CBC, _AES_IV)
    encrypted = cipher.encrypt(text.encode())
    return binascii.b2a_hex(encrypted).decode()


def _java_hashcode(s: str) -> int:
    """模拟 Java String.hashCode() 算法 (32位有符号整数)"""
    h = 0
    for ch in s:
        h = ((h << 5) - h + ord(ch)) & 0xFFFFFFFF  # h * 31 + char
    return ctypes.c_int32(h).value


def generate_ckey(cnlid: str, timestamp: int | None = None) -> str:
    """
    生成央视频 API 所需的 cKey 签名

    Args:
        cnlid: 频道 ID (vid)，如 "2024078201"
        timestamp: Unix 时间戳，不传则使用当前时间

    Returns:
        cKey 字符串，格式为 "--01" + AES密文(大写hex)
    """
    if timestamp is None:
        timestamp = int(time.time())

    # Step 1: 构造签名字符串 wu
    wu = (
        f"|{cnlid}|{timestamp}|{_JC}|{_VERSION}"
        f"|{_GUID}|{_PLATFORM}|{_REFERER}|{_USER_AGENT}"
    )

    # Step 2: 计算 Java hashCode 并拼接到前面
    hc = _java_hashcode(wu)
    xu = f"|{hc}{wu}"

    # Step 3: AES 加密并格式化
    ckey = "--01" + _aes_encrypt(xu).upper()

    return ckey


def generate_flowid() -> str:
    """生成随机 flowid"""
    return uuid.uuid4().hex
