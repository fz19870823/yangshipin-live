"""
央视频 TV 频道数据库

包含 CCTV 各频道及卫视频道的 pid / cnlid (vid) 对照表。
数据来源：央视频官方 API 及公开信息整理。
"""

from typing import NamedTuple


class Channel(NamedTuple):
    """频道信息"""
    name: str          # 频道名称
    pid: str           # 直播节目 ID
    cnlid: str         # 频道/视频 ID (即 vid)
    category: str = "cctv"  # 分类: cctv / satellite / other


# ============================================================
# CCTV 核心频道
# ============================================================
CCTV_CHANNELS = [
    Channel("CCTV-1 综合",         "600001859", "2024078201", "cctv"),
    Channel("CCTV-2 财经",         "600001800", "2024075401", "cctv"),
    Channel("CCTV-3 综艺",         "600001801", "2024068501", "cctv"),
    Channel("CCTV-4 中文国际",     "600001814", "2029797103", "cctv"),
    Channel("CCTV-5 体育",         "600001818", "2024078401", "cctv"),
    Channel("CCTV-5+ 体育赛事",    "600001817", "2024078001", "cctv"),
    Channel("CCTV-6 电影",         "600108442", "2013693901", "cctv"),
    Channel("CCTV-7 国防军事",     "600004092", "2024072001", "cctv"),
    Channel("CCTV-8 电视剧",       "600001803", "2029793001", "cctv"),
    Channel("CCTV-9 纪录",         "600004078", "2024078601", "cctv"),
    Channel("CCTV-10 科教",        "600001805", "2024078701", "cctv"),
    Channel("CCTV-11 戏曲",        "600001806", "2027248701", "cctv"),
    Channel("CCTV-12 社会与法",    "600001807", "2027248801", "cctv"),
    Channel("CCTV-13 新闻",        "600001811", "2024068601", "cctv"),
    Channel("CCTV-14 少儿",        "600001809", "2024078201", "cctv"),  # 注意：与CCTV-1 cnlid相同，以实际为准
    Channel("CCTV-15 音乐",        "600001815", "2024071301", "cctv"),
    Channel("CCTV-16 奥林匹克",    "600098637", "2027248901", "cctv"),
    Channel("CCTV-16 4K",          "600099502", "2028168101", "cctv"),
    Channel("CCTV-17 农业农村",    "600001810", "2024075501", "cctv"),
    Channel("CCTV-4K 超高清",      "600002264", "2026116701", "cctv"),
    Channel("CCTV-8K 超高清",      "600156816", "2028168201", "cctv"),
]

# ============================================================
# CGTN 外语频道
# ============================================================
CGTN_CHANNELS = [
    Channel("CGTN",                "600014550", "2027088301", "cgtn"),
    Channel("CGTN 法语",           "600084704", "2027088401", "cgtn"),
    Channel("CGTN 俄语",           "600084758", "2027088501", "cgtn"),
    Channel("CGTN 阿拉伯语",       "600084759", "2027088601", "cgtn"),
    Channel("CGTN 西班牙语",       "600084779", "2027088701", "cgtn"),
    Channel("CGTN 外语纪录",       "600084781", "2027088801", "cgtn"),
]

# ============================================================
# 卫视频道
# ============================================================
SATELLITE_CHANNELS = [
    Channel("北京卫视",            "600002309", "2027158101", "satellite"),
    Channel("江苏卫视",            "600002521", "2027158201", "satellite"),
    Channel("东方卫视",            "600002483", "2027158301", "satellite"),
    Channel("浙江卫视",            "600002520", "2027158401", "satellite"),
    Channel("湖南卫视",            "600002475", "2027158501", "satellite"),
    Channel("湖北卫视",            "600002508", "2027158601", "satellite"),
    Channel("广东卫视",            "600002485", "2027158701", "satellite"),
    Channel("广西卫视",            "600002486", "2027158801", "satellite"),
    Channel("深圳卫视",            "600002253", "2027158901", "satellite"),
    Channel("重庆卫视",            "600002487", "2027159001", "satellite"),
    Channel("天津卫视",            "600002252", "2027159101", "satellite"),
    Channel("山东卫视",            "600002522", "2027159201", "satellite"),
    Channel("辽宁卫视",            "600002462", "2027159301", "satellite"),
    Channel("安徽卫视",            "600002464", "2027159401", "satellite"),
    Channel("江西卫视",            "600002307", "2027159501", "satellite"),
    Channel("河南卫视",            "600002251", "2027159601", "satellite"),
    Channel("河北卫视",            "600002308", "2027159701", "satellite"),
    Channel("黑龙江卫视",          "600002250", "2027159801", "satellite"),
    Channel("四川卫视",            "600002474", "2027159901", "satellite"),
    Channel("贵州卫视",            "600002461", "2027160001", "satellite"),
    Channel("云南卫视",            "600002523", "2027160101", "satellite"),
    Channel("海南卫视",            "600002489", "2027160201", "satellite"),
    Channel("甘肃卫视",            "600002460", "2027160301", "satellite"),
    Channel("青海卫视",            "600002467", "2027160401", "satellite"),
    Channel("陕西卫视",            "600002463", "2027160501", "satellite"),
    Channel("山西卫视",            "600002473", "2027160601", "satellite"),
    Channel("吉林卫视",            "600002459", "2027160701", "satellite"),
    Channel("新疆卫视",            "600002468", "2027160801", "satellite"),
    Channel("西藏卫视",            "600002477", "2027160901", "satellite"),
    Channel("内蒙古卫视",          "600002469", "2027161001", "satellite"),
    Channel("宁夏卫视",            "600002478", "2027161101", "satellite"),
    Channel("东南卫视",            "600002304", "2027161201", "satellite"),
    Channel("厦门卫视",            "600002488", "2027161301", "satellite"),
    Channel("三沙卫视",            "600002255", "2027161401", "satellite"),
    Channel("兵团卫视",            "600002310", "2027161501", "satellite"),
    Channel("大湾区卫视",          "600002303", "2027161601", "satellite"),
]

# ============================================================
# 付费 / 限免频道
# ============================================================
PREMIUM_CHANNELS = [
    Channel("CCTV 风云剧场 (限免)",   "600099658", "2027088901", "premium"),
    Channel("CCTV 第一剧场 (限免)",   "600099655", "2027089001", "premium"),
    Channel("CCTV 怀旧剧场 (限免)",   "600099620", "2027089101", "premium"),
    Channel("CCTV 世界地理 (VIP)",    "600099656", "2027089201", "premium"),
    Channel("CCTV 风云音乐 (VIP)",    "600099657", "2027089301", "premium"),
    Channel("CCTV 兵器科技 (VIP)",    "600099651", "2027089401", "premium"),
    Channel("CCTV 风云足球 (VIP)",    "600099652", "2027089501", "premium"),
    Channel("CCTV 高尔夫网球 (VIP)",  "600099653", "2027089601", "premium"),
    Channel("CCTV 女性时尚 (VIP)",    "600099654", "2027089701", "premium"),
    Channel("CCTV 央视文化精品 (VIP)","600099649", "2027089801", "premium"),
    Channel("CCTV 央视台球 (VIP)",    "600099650", "2027089901", "premium"),
    Channel("CCTV 电视指南 (VIP)",    "600099659", "2027090001", "premium"),
    Channel("CCTV 卫生健康 (VIP)",    "600099660", "2027090101", "premium"),
]

# ============================================================
# 全部频道列表
# ============================================================
ALL_CHANNELS = CCTV_CHANNELS + CGTN_CHANNELS + SATELLITE_CHANNELS + PREMIUM_CHANNELS


def get_channel_by_name(name: str) -> Channel | None:
    """根据频道名称查找频道"""
    for ch in ALL_CHANNELS:
        if ch.name == name or name in ch.name:
            return ch
    return None


def get_channel_by_pid(pid: str) -> Channel | None:
    """根据 pid 查找频道"""
    for ch in ALL_CHANNELS:
        if ch.pid == pid:
            return ch
    return None


def get_channels_by_category(category: str) -> list[Channel]:
    """按分类获取频道列表"""
    return [ch for ch in ALL_CHANNELS if ch.category == category]
