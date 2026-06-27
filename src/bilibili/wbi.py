"""
B站 WBI 签名算法实现

WBI 签名用于 B站 /wbi/v2 系列 API，防止未授权访问。
算法核心：从 nav 接口获取每日轮换的 img_key 和 sub_key，
组合后通过固定置换表生成 mixin_key，再对请求参数进行 MD5 签名。
"""

import time
import hashlib
import urllib.parse
from functools import lru_cache
from typing import Optional

import httpx

# WBI 密钥置换表（固定，来自 B站前端）
MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52
]

# 通用请求头
COMMON_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com",
}


def get_mixin_key(img_key: str, sub_key: str) -> str:
    """使用固定置换表组合 img_key 和 sub_key，截取前 32 位作为 mixin_key。"""
    raw = img_key + sub_key
    return ''.join(raw[i] for i in MIXIN_KEY_ENC_TAB)[:32]


@lru_cache(maxsize=1)
def _cached_wbi_keys(sessdata: str = "") -> tuple[str, str]:
    """
    获取 WBI 密钥对，结果缓存直到进程重启或手动清除缓存。
    密钥每日轮换，长期运行建议配合定时刷新。
    """
    url = "https://api.bilibili.com/x/web-interface/nav"
    cookies = {}
    if sessdata:
        cookies["SESSDATA"] = sessdata

    with httpx.Client(timeout=15, headers=COMMON_HEADERS, cookies=cookies) as client:
        resp = client.get(url)
        resp.raise_for_status()
        data = resp.json()

    if data.get("code") != 0:
        raise RuntimeError(f"获取 WBI 密钥失败: {data.get('message', '未知错误')}")

    wbi_img = data["data"]["wbi_img"]
    img_url = wbi_img["img_url"]
    sub_url = wbi_img["sub_url"]

    # 从 URL 的文件名提取 key（去掉扩展名）
    img_key = img_url.split("/")[-1].split(".")[0]
    sub_key = sub_url.split("/")[-1].split(".")[0]

    return img_key, sub_key


def clear_wbi_cache():
    """清除 WBI 密钥缓存（用于强制刷新）。"""
    _cached_wbi_keys.cache_clear()


def enc_wbi(params: dict, img_key: Optional[str] = None, sub_key: Optional[str] = None, sessdata: str = "") -> dict:
    """
    对请求参数进行 WBI 签名。

    Args:
        params: 待签名的参数字典
        img_key: WBI img_key（可选，不传则自动获取）
        sub_key: WBI sub_key（可选，不传则自动获取）
        sessdata: B站 SESSDATA cookie（用于获取 WBI 密钥）

    Returns:
        添加了 w_rid 和 wts 的参数字典
    """
    # 获取密钥
    if img_key is None or sub_key is None:
        img_key, sub_key = _cached_wbi_keys(sessdata)

    mixin_key = get_mixin_key(img_key, sub_key)

    # 添加时间戳
    params = dict(params)
    params["wts"] = int(time.time())

    # 按键排序
    params = dict(sorted(params.items()))

    # 过滤特殊字符 '!()* 并编码
    filtered = {
        k: ''.join(ch for ch in str(v) if ch not in "!'()*")
        for k, v in params.items()
    }
    query = urllib.parse.urlencode(filtered)

    # MD5 签名
    sign_str = query + mixin_key
    w_rid = hashlib.md5(sign_str.encode()).hexdigest()

    params["w_rid"] = w_rid
    return params
