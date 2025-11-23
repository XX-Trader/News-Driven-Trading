#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Twitter 爬取最小流程（脚本版，使用 matplotlib 预览图片）
- 流程：配置 → 获取 → 解析 → 存储(JSON/CSV) + 媒体下载与 matplotlib 预览 → AI 文本分析（Poe OpenAI 兼容）
- 说明：本脚本可直接用 `python twitter_crawler_functional_min.py` 运行；无需 Notebook 视图。
"""

import os
import json
import time
import csv
from datetime import datetime
from typing import List, Dict, Any

import requests

# 仅使用 matplotlib 显示图片（可选）
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.image as mpimg

# -----------------------
# 显示与字体初始化
# -----------------------
matplotlib.rcParams.update({
    "figure.figsize": (6, 4),
    "figure.dpi": 120,
    "savefig.dpi": 120,
    "axes.unicode_minus": False,  # 解决负号显示问题
})
# 中文字体回退（若无会自动回退英文，不报错）
for _f in ["SimHei", "Microsoft YaHei", "Arial Unicode MS"]:
    try:
        matplotlib.rcParams["font.sans-serif"] = [_f]
        break
    except Exception:
        pass

# -----------------------
# 配置（按需修改）
# -----------------------
API_KEY = "new1_58fe956453e744e4844728c68ba187d4"  # Twitter接口密钥，放在请求头X-API-Key中（示例）
# 基础域名，便于后续扩展不同 endpoint，避免在代码中到处硬编码
API_BASE = "https://api.twitterapi.io"
# 用户最近推文API
API_URL = f"{API_BASE}/twitter/user/last_tweets"
# 按推文ID批量获取推文详情 API（get_tweet_by_ids）
API_URL_GET_TWEETS_BY_IDS = f"{API_BASE}/twitter/tweets"

TARGET_USER = "cz_binance"   # 默认抓取用户（不含@）
TWEET_LIMIT = 1              # 每次请求推文条数
REQUEST_INTERVAL_SEC = 5     # 请求间隔（固定5秒）

MEDIA_DIR = os.path.join(os.path.dirname(__file__), "twitter_media")  # 媒体本地目录

# Poe(OpenAI兼容)配置（如需使用 AI 分析）
AI_API_KEY = "bvJrIZp3bug_ZHHvkBTQmN_HanLRg-J6yEpRwAocESw"  # 示例 Key（建议改为环境变量）
AI_BASE_URL = "https://api.poe.com/v1"
AI_MODEL = "gpt-5.1"

# OpenAI 代理开关与配置（按需启用）
USE_OPENAI_PROXY = True  # 开关：True 使用下方代理，False 直连
OPENAI_PROXY = {
    "http": "http://localhost:1080",
    "https": "http://localhost:1080",
}

# 本地调试数据路径（始终指向 latest.json，fetch 后覆盖写入）
LOCAL_JSON_PATH = os.path.join(os.path.dirname(__file__), "twitter_media", "latest.json")

print("[INIT] 配置与显示初始化完成")

# -----------------------
# 工具函数
# -----------------------
def ensure_media_dir(path: str = MEDIA_DIR) -> str:
    """确保媒体保存目录存在，返回绝对路径。"""
    p = os.path.abspath(path)
    os.makedirs(p, exist_ok=True)
    return p



def load_local_json_strict(path: str, page=1) -> List[Dict]:
    """读取 latest.json，并直接返回其中 ['tweets'][0]，以单元素列表[List[Dict]]返回。"""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    first = data["tweets"][page]
    # 确保返回 List[Dict]，若不是 dict 则包为 dict 保持下游签名
    return str(first)


def fetch_last_tweets(username: str, count: int = TWEET_LIMIT) -> List[Dict]:
    """调用 last_tweets 接口获取原始推文列表，不做重试与回退。"""
    params = {"userName": username.lstrip("@"), "count": count}
    headers = {"X-API-Key": API_KEY}
    try:
        resp = requests.get(API_URL, params=params, headers=headers, timeout=30)
    except Exception as e:
        print("[ERR ] 请求异常:", e)
        return []

    if resp.status_code != 200:
        print("[ERR ] 请求失败:", resp.status_code, resp.text[:200])
        return []
    try:
        print("[INFO] 响应:", resp.status_code, resp.text[:200])
        data = resp.json()
        # 兼容两类返回：dict 包裹 或 直接 list
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("data") or data.get("tweets") or data.get("results") or []
        return []
    except Exception as e:
        print("[ERR ] JSON解析失败:", e, resp.text[:200])
        return []




def analyze_each_tweet(text: List[Dict], use_proxy: bool = USE_OPENAI_PROXY) -> List[Dict[str, Any]]:
    """依次分析每一条消息（解析后的每条推文），返回分析结果列表。
    - 输入：parse_tweets 的输出 rows: List[Dict]
    - 输出：List[Dict]，每一项包含 tweet_id、text 以及 ai_summary（字符串）
    - 代理：默认跟随全局 USE_OPENAI_PROXY，可通过参数覆盖
    """
    if text.strip():
        summary = ai_analyze_text(text, proxy=use_proxy)
        print("[INFO] 推文分析结果:", summary)
    else:
        summary = "(空文本，跳过分析)"



def save_json(path: str, data: List[Dict]) -> None:
    """将解析后的列表写入 JSON 文件（UTF-8，带缩进）。"""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def read_text(path: str) -> str:
    """读取文本文件，返回内容。"""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


# -----------------------
# AI 分析（可选）
# -----------------------
def ai_analyze_text(text: str, proxy=False) -> str:
    # 允许通过函数参数或全局 USE_OPENAI_PROXY 控制是否走代理
    if proxy is None:
        proxy = USE_OPENAI_PROXY
    # 提示词.txt 现在位于 trading_bot/ 目录下
    prompt_path = os.path.join(os.path.dirname(__file__), os.pardir, "trading_bot", "提示词.txt")
    promot = read_text(prompt_path)
    promot = promot.replace('{text1}', text)
    try:
        import openai  # 延迟导入
        # 代理支持：优先使用 httpx 客户端方式；失败则回退到环境变量
        if proxy:
            try:
                from httpx import Client as _HttpxClient
                # 修正：httpx 的参数为 proxies（dict 或 str），不是 proxy
                http_client = _HttpxClient(proxies=OPENAI_PROXY, timeout=30.0)
                client = openai.OpenAI(api_key=AI_API_KEY, base_url=AI_BASE_URL, http_client=http_client)
            except Exception:
                import os as _os
                _os.environ["HTTP_PROXY"] = OPENAI_PROXY.get("http", "")
                _os.environ["HTTPS_PROXY"] = OPENAI_PROXY.get("https", "")
                client = openai.OpenAI(api_key=AI_API_KEY, base_url=AI_BASE_URL)
        else:
            client = openai.OpenAI(api_key=AI_API_KEY, base_url=AI_BASE_URL)

        chat = client.chat.completions.create(
            model=AI_MODEL,
            messages=[{"role": "user", "content": promot}],
            temperature=0.2,
            max_tokens=500,
        )
        # 兼容 openai 返回对象的两种可能结构
        content: Any = None
        if chat and getattr(chat, "choices", None):
            choice0 = chat.choices[0]
            msg = getattr(choice0, "message", None)
            if isinstance(msg, dict):
                content = msg.get("content")
            else:
                content = getattr(msg, "content", None)
        return content or "(AI 无内容返回)"
    except Exception as e:
        return f"(AI 跳过：{e})"


def test_all(latest_path):
    # 调试期：一律从本地 strict 读取，保障数据结构健康
    for i in range(0, 1):
        raw_local = ''
        try:
            raw_local = load_local_json_strict(latest_path, page=i)
            print("[INFO] 本地读取条数:", len(raw_local))
        except Exception as e:
            print("[FATAL] 本地JSON不符合严格结构:", e)
            return {"ok": False, "error": str(e), "saved": latest_path}


        try:
            # 解析所有推文并依次分析
            per_tweet = analyze_each_tweet(raw_local, use_proxy=USE_OPENAI_PROXY)
            # 简要打印每条的摘要头部
        except Exception as e:
            print("[WARN] AI 分析失败:", e)


# -----------------------
# 单次运行：fetch → 保存本地 → 严格读取 → 解析 → 存储 → 预览 → AI
# -----------------------
def run_once(username: str = TARGET_USER, count: int = TWEET_LIMIT):
    latest_path = LOCAL_JSON_PATH
    # print("[RUN ] 开始接口获取:", username)
    # raw = fetch_last_tweets(username, count)
    # time.sleep(REQUEST_INTERVAL_SEC)  # 固定5秒，无重试

    # ensure_media_dir()  # 确保目录存在
    
    # try:
    #     with open(latest_path, "w", encoding="utf-8") as f:
    #         json.dump(raw, f, ensure_ascii=False, indent=2)
    #     print("[SAVE] 原始响应已写入:", latest_path)
    # except Exception as e:
    #     print("[ERR ] 写入本地原始JSON失败:", e)
    #     # 即便写失败，也继续尝试解析内存数据

    # test_all(latest_path)
    good_path1 = os.path.join(os.path.dirname(__file__), "twitter_media", "1984992347395141987.json")

    test_all(good_path1)


# -----------------------
# 按 Tweet ID 获取推文并保存
# -----------------------
def fetch_tweets_by_ids(tweet_ids):
    """
    通过 tweetIds 调用 get_tweet_by_ids 接口，返回原始 JSON 数据。
    - tweet_ids: 单个 ID（str/int）或 ID 列表
    - 返回：解析后的 JSON（通常为 dict 或 list），失败时返回 None
    """
    if not tweet_ids:
        print("[ERR ] tweet_ids 为空")
        return None

    # 统一转成 list[str]
    if isinstance(tweet_ids, (str, int)):
        tweet_ids = [str(tweet_ids)]
    else:
        tweet_ids = [str(tid) for tid in tweet_ids]

    params = {"tweet_ids": tweet_ids}
    headers = {"X-API-Key": API_KEY}
    try:
        resp = requests.get(API_URL_GET_TWEETS_BY_IDS, params=params, headers=headers, timeout=30)
    except Exception as e:
        print("[ERR ] get_tweet_by_ids 请求异常:", e)
        return None

    if resp.status_code != 200:
        print("[ERR ] get_tweet_by_ids 请求失败:", resp.status_code, resp.text[:200])
        return None

    try:
        print("[INFO] get_tweet_by_ids 响应:", resp.status_code, resp.text[:200])
        data = resp.json()
        return data
    except Exception as e:
        print("[ERR ] get_tweet_by_ids JSON解析失败:", e, resp.text[:200])
        return None


def fetch_and_save_tweet_by_id(tweet_id: str) -> dict:
    """
    通过单个 tweet_id 获取推文详情，并将完整 JSON 存为 twitter_media/{tweet_id}.json
    返回形如：
    {
        "ok": True/False,
        "tweet_id": tweet_id,
        "path": 保存路径(成功时存在),
        "error": 错误信息(失败时存在)
    }
    """
    tweet_id_str = str(tweet_id)
    data = fetch_tweets_by_ids(tweet_id_str)
    if data is None:
        return {"ok": False, "tweet_id": tweet_id_str, "error": "request_failed_or_parse_error"}

    media_dir = ensure_media_dir()
    save_path = os.path.join(media_dir, f"{tweet_id_str}.json")
    try:
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"[SAVE] 推文 {tweet_id_str} 详情已写入: {save_path}")
        return {"ok": True, "tweet_id": tweet_id_str, "path": save_path}
    except Exception as e:
        print("[ERR ] 写入推文详情JSON失败:", e)
        return {"ok": False, "tweet_id": tweet_id_str, "error": str(e)}


if __name__ == "__main__":
    ensure_media_dir()
    # 示例：按用户名获取最近推文
    # result = run_once()
    # print("[DONE] run_once 运行结束:", result)
    # 示例：按推文 ID 获取并落盘（根据需要自行取消/保留）
    fetch_and_save_tweet_by_id("1987990314997739625")