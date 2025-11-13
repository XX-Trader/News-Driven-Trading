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
API_URL = "https://api.twitterapi.io/twitter/user/last_tweets"  # 用户最近推文API

TARGET_USER = "cz_binance"   # 默认抓取用户（不含@）
TWEET_LIMIT = 1              # 每次请求推文条数
REQUEST_INTERVAL_SEC = 5     # 请求间隔（固定5秒）

MEDIA_DIR = os.path.join(os.path.dirname(__file__), "twitter_media")  # 媒体本地目录

# Poe(OpenAI兼容)配置（如需使用 AI 分析）
AI_API_KEY = "lUOtczZXbp6emUFgvqfZC7odtwGEhBdwmIAdTlpLHzs"  # 示例 Key（建议改为环境变量）
AI_BASE_URL = "https://api.poe.com/v1"
AI_MODEL = "gpt-5"

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


def download_file(url: str, local_path: str, timeout: int = 30) -> bool:
    """下载单个媒体文件到 local_path，失败返回 False。"""
    try:
        r = requests.get(url, timeout=timeout, stream=True)
        r.raise_for_status()
        with open(local_path, "wb") as f:
            for c in r.iter_content(8192):
                if c:
                    f.write(c)
        return True
    except Exception as e:
        print("[WARN] 媒体下载失败:", e)
        return False


def load_local_json_strict(path: str) -> List[Dict]:
    """严格从本地 JSON 读取：原设计要求顶层为 list[dict]。
    为增强鲁棒性，这里做向后兼容：
    - 若顶层为 dict，优先尝试提取 data/tweets/results/items 等常见数组键；
      若上述键不存在但存在单推文对象，则包装为单元素列表。
    - 最终仍保证返回 List[Dict]，否则抛出 ValueError。
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 已是标准 list[dict]
    if isinstance(data, list):
        for i, item in enumerate(data):
            if not isinstance(item, dict):
                snippet = str(item)
                if len(snippet) > 120:
                    snippet = snippet[:120] + "..."
                raise ValueError(f"本地JSON第{i}项不是dict，实际类型={type(item)}，片段={snippet}")
        return data

    # 顶层是 dict，做兼容处理
    if isinstance(data, dict):
        # 优先提取常见数组字段
        for key in ("data", "tweets", "results", "items"):
            arr = data.get(key)
            if isinstance(arr, list):
                for i, item in enumerate(arr):
                    if not isinstance(item, dict):
                        snippet = str(item)
                        if len(snippet) > 120:
                            snippet = snippet[:120] + "..."
                        raise ValueError(f"本地JSON.{key}[{i}] 不是dict，实际类型={type(item)}，片段={snippet}")
                return arr

        # 若存在明确的单条推文对象（例如 id/text/url 等），则包一层列表返回
        possible_tweet_like_keys = {"id", "text", "url", "twitterUrl", "createdAt", "author"}
        if any(k in data for k in possible_tweet_like_keys):
            return [data]

        # 若存在 pin_tweet / tweets 组合但 tweets 不是 list（极端场景），尝试忽略非 list 值
        if "pin_tweet" in data and "tweets" in data and isinstance(data.get("tweets"), list):
            arr = data["tweets"]
            for i, item in enumerate(arr):
                if not isinstance(item, dict):
                    snippet = str(item)
                    if len(snippet) > 120:
                        snippet = snippet[:120] + "..."
                    raise ValueError(f"本地JSON.tweets[{i}] 不是dict，实际类型={type(item)}，片段={snippet}")
            return arr

        raise ValueError(f"不支持的本地JSON(dict)布局，未找到数组字段(data/tweets/results/items)，文件={path}")

    raise ValueError(f"本地JSON顶层必须是数组(list)或对象(dict)，当前类型={type(data)}，文件={path}")


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


def parse_tweets(raw: List[Dict]) -> List[Dict]:
    """将原始推文记录解析为结构化字段，并收集媒体列表（entities 和 includes）。
    注意：按你的要求，不在此加入类型守卫，依赖 strict loader 确保 raw 为 List[Dict]。
    """
    out: List[Dict] = []
    for t in raw:
        media = []
        ents = t.get("entities", {})
        if isinstance(ents.get("media"), list):
            for m in ents["media"]:
                url = m.get("media_url") or m.get("url") or m.get("media_url_https")
                if url:
                    media.append({"id": m.get("id"), "type": m.get("type"), "url": url})

        inc = t.get("includes", {})
        if isinstance(inc.get("media"), list):
            for m in inc["media"]:
                url = m.get("url") or m.get("preview_image_url")
                if url:
                    media.append({"id": m.get("media_key") or m.get("id"), "type": m.get("type"), "url": url})

        out.append({
            "tweet_id": t.get("id"),
            "created_at": t.get("created_at"),
            "text": t.get("text", ""),
            "author": t.get("author_username") or t.get("author_id"),
            "permalink": t.get("url") or t.get("permalink"),
            "media": media,
        })
    return out


def save_json(path: str, data: List[Dict]) -> None:
    """将解析后的列表写入 JSON 文件（UTF-8，带缩进）。"""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def save_csv(path: str, rows: List[Dict]) -> None:
    """将核心字段写入 CSV，避免换行与逗号干扰。"""
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["tweet_id", "created_at", "author", "text", "permalink", "media_count"])
        for r in rows:
            w.writerow([
                r["tweet_id"],
                r["created_at"],
                r["author"],
                (r.get("text") or "").replace("\n", " "),
                r["permalink"],
                len(r["media"]),
            ])


def _show_image(path: str) -> None:
    """使用 matplotlib 显示本地图片文件。"""
    try:
        img = mpimg.imread(path)
    except Exception as e:
        print("[WARN] 打开图片失败:", e, " ->", path)
        return
    plt.figure(figsize=(4, 4))
    plt.imshow(img)
    plt.axis("off")
    plt.tight_layout()
    plt.show()


def store_media_and_preview(rows: List[Dict], limit: int = 3) -> None:
    """下载媒体到本地并在脚本中弹出 matplotlib 窗口预览前若干张图片。"""
    ensured = ensure_media_dir()
    shown = 0
    for r in rows:
        for m in r["media"]:
            url = m["url"]
            ext = os.path.splitext(url.split("?")[0])[1] or ".jpg"
            fname = f"{r['tweet_id']}_{m.get('id','m')}{ext}"
            lp = os.path.join(ensured, fname)
            if download_file(url, lp) and ext.lower() in [".jpg", ".jpeg", ".png", ".gif"] and shown < limit:
                _show_image(lp)
                shown += 1


# -----------------------
# AI 分析（可选）
# -----------------------
def ai_analyze_text(text: str, hint: str = "") -> str:
    """调用 Poe(OpenAI兼容) 接口做简要分析；如环境无 openai，返回占位结果。"""
    promot = """
你是一个专业的加密货币交易分析师。请分析以下Twitter推文内容，判断其对交易的影响。

推文内容：{text}

分析要求：
1. 识别是特定币种消息还是市场整体利好
2. 判断交易方向（做多/做空/观望）
3. 给出具体交易参数

输出格式（必须严格JSON格式，使用中文标注）：
{{
  "分析结果": "特定币种利好"或"市场整体利好"或"观望",
  "交易币种": "BTC"或["BTC","ETH","BNB","SOL"],
  "交易方向": "long"或"short"或"观望",
  "是否基于图片": "是"或"否",
  "分析依据": "明确提及Bitcoin突破关键价位，强烈看涨信号",
  "预期消息对市场行情影响的持续时间":"分钟，小时，天",
  "消息置信度":"0-100"
}}

规则：
- 严格输出JSON格式
- 市场利好时交易主流币种(BTC/ETH/BNB/SOL)
- 信号不明确时选择观望
- 特定币种利好只交易该币种
- 市场整体利好同时交易多个主流币种
- 消息置信度 100 为100%可信
"""

    prompt = hint or ("请基于以下推文文本做交易相关性与情绪的简要分析，并给出要点：\n" + (text or ""))
    try:
        import openai  # 延迟导入
        client = openai.OpenAI(api_key=AI_API_KEY, base_url=AI_BASE_URL)
        chat = client.chat.completions.create(
            model=AI_MODEL,
            messages=[{"role": "user", "content": prompt}],
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



    # 调试期：一律从本地 strict 读取，保障数据结构健康
    # try:
    #     raw_local = load_local_json_strict(latest_path)
    #     print("[INFO] 本地读取条数:", len(raw_local))
    # except Exception as e:
    #     print("[FATAL] 本地JSON不符合严格结构:", e)
    #     return {"ok": False, "error": str(e), "saved": latest_path}




    # rows = parse_tweets(raw_local)
    # ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    # parsed_json_path = os.path.join(MEDIA_DIR, f"parsed_{username}_{ts}.json")
    # parsed_csv_path = os.path.join(MEDIA_DIR, f"parsed_{username}_{ts}.csv")
    # try:
    #     save_json(parsed_json_path, rows)
    #     save_csv(parsed_csv_path, rows)
    #     print("[SAVE] 解析结果 JSON:", parsed_json_path)
    #     print("[SAVE] 解析结果 CSV :", parsed_csv_path)
    # except Exception as e:
    #     print("[ERR ] 保存解析结果失败:", e)

    # # 媒体下载与预览
    # try:
    #     store_media_and_preview(rows, limit=3)
    # except Exception as e:
    #     print("[WARN] 媒体处理出现问题:", e)

    # AI 文本聚合与分析（简单拼接前若干条）
    text = """
{
      "type": "tweet",
      "id": "1988883673144336473",
      "url": "https://x.com/cz_binance/status/1988883673144336473",
      "twitterUrl": "https://twitter.com/cz_binance/status/1988883673144336473",
      "text": "Writing the book made me realize my English is poor, very poor.\n\nReviewing the Chinese translations by my colleagues made me realize my Chinese is non-existent. Had to use the dictionary constantly.\n\nBasically, I don't really speak any language. 😂",
      "source": "Twitter for iPhone",
      "retweetCount": 58,
      "replyCount": 820,
      "likeCount": 1217,
      "quoteCount": 24,
      "viewCount": 125890,
      "createdAt": "Thu Nov 13 08:16:34 +0000 2025",
      "lang": "en",
      "bookmarkCount": 26,
      "isReply": false,
      "inReplyToId": null,
      "conversationId": "1988883673144336473",
      "displayTextRange": [
        0,
        247
      ],
      "inReplyToUserId": null,
      "inReplyToUsername": null,
      "author": {
        "type": "user",
        "userName": "cz_binance",
        "url": "https://x.com/cz_binance",
        "twitterUrl": "https://twitter.com/cz_binance",
        "id": "902926941413453824",
        "name": "CZ 🔶 BNB",
        "isVerified": false,
        "isBlueVerified": true,
        "verifiedType": null,
        "profilePicture": "https://pbs.twimg.com/profile_images/1961440580279336960/PiiIs8Lh_normal.jpg",
        "coverPicture": "https://pbs.twimg.com/profile_banners/902926941413453824/1597864552",
        "description": "",
        "location": "",
        "followers": 10480803,
        "following": 1237,
        "status": "",
        "canDm": false,
        "canMediaTag": true,
        "createdAt": "Wed Aug 30 16:12:13 +0000 2017",
        "entities": {
          "description": {
            "urls": []
          },
          "url": {}
        },
        "fastFollowersCount": 0,
        "favouritesCount": 17541,
        "hasCustomTimelines": true,
        "isTranslator": false,
        "mediaCount": 922,
        "statusesCount": 7364,
        "withheldInCountries": [],
        "affiliatesHighlightedLabel": {},
        "possiblySensitive": false,
        "pinnedTweetIds": [
          "1981404850832494666"
        ],
        "profile_bio": {
          "description": "@BNBchain\n@YZiLabs\n@GiggleAcademy\n@binance",
          "entities": {
            "description": {
              "user_mentions": [
                {
                  "id_str": "0",
                  "indices": [
                    0,
                    9
                  ],
                  "name": "",
                  "screen_name": "BNBchain"
                },
                {
                  "id_str": "0",
                  "indices": [
                    10,
                    18
                  ],
                  "name": "",
                  "screen_name": "YZiLabs"
                },
                {
                  "id_str": "0",
                  "indices": [
                    19,
                    33
                  ],
                  "name": "",
                  "screen_name": "GiggleAcademy"
                },
                {
                  "id_str": "0",
                  "indices": [
                    34,
                    42
                  ],
                  "name": "",
                  "screen_name": "binance"
                }
              ]
            },
            "url": {
              "urls": [
                {
                  "display_url": "binance.com",
                  "expanded_url": "http://www.binance.com",
                  "indices": [
                    0,
                    23
                  ],
                  "url": "https://t.co/zlvCSBIFGA"
                }
              ]
            }
          }
        },
        "isAutomated": false,
        "automatedBy": null
      },
      "extendedEntities": {},
      "card": null,
      "place": {},
      "entities": {},
      "quoted_tweet": {
        "type": "tweet",
        "id": "1988882854378344501",
        "url": "https://x.com/ZiksMeta/status/1988882854378344501",
        "twitterUrl": "https://twitter.com/ZiksMeta/status/1988882854378344501",
        "text": "@cz_binance Will your book be available in both soft and hard copy all over the world?",
        "source": "Twitter for iPhone",
        "retweetCount": 1,
        "replyCount": 6,
        "likeCount": 19,
        "quoteCount": 1,
        "viewCount": 127694,
        "createdAt": "Thu Nov 13 08:13:18 +0000 2025",
        "lang": "en",
        "bookmarkCount": 2,
        "isReply": true,
        "inReplyToId": "1988882745989153243",
        "conversationId": "1988882745989153243",
        "displayTextRange": [
          12,
          86
        ],
        "inReplyToUserId": null,
        "inReplyToUsername": null,
        "author": {
          "type": "user",
          "userName": "ZiksMeta",
          "url": "https://x.com/ZiksMeta",
          "twitterUrl": "https://twitter.com/ZiksMeta",
          "id": "1561355648595533831",
          "name": "Liquid",
          "isVerified": false,
          "isBlueVerified": true,
          "verifiedType": null,
          "profilePicture": "https://pbs.twimg.com/profile_images/1986094531574407168/hx2qB_uW_normal.jpg",
          "coverPicture": "https://pbs.twimg.com/profile_banners/1561355648595533831/1760161471",
          "description": "",
          "location": "In Profit",
          "followers": 2565,
          "following": 2084,
          "status": "",
          "canDm": false,
          "canMediaTag": true,
          "createdAt": "Sun Aug 21 14:13:54 +0000 2022",
          "entities": {
            "description": {
              "urls": []
            },
            "url": {}
          },
          "fastFollowersCount": 0,
          "favouritesCount": 9736,
          "hasCustomTimelines": true,
          "isTranslator": false,
          "mediaCount": 301,
          "statusesCount": 8817,
          "withheldInCountries": [],
          "affiliatesHighlightedLabel": {},
          "possiblySensitive": false,
          "pinnedTweetIds": [
            "1985797692358869052"
          ],
          "profile_bio": {
            "description": "6+ years in Crypto |Web3 |Marketing📊 |Community Builder👷‍♂️ |ReplyGuy👨‍💻 |Degen💹  |Posts are NFA | Always DYOR",
            "entities": {
              "description": {},
              "url": {
                "urls": [
                  {
                    "display_url": "doginaldogs.com",
                    "expanded_url": "http://doginaldogs.com",
                    "indices": [
                      0,
                      23
                    ],
                    "url": "https://t.co/yGyuYFVDT5"
                  }
                ]
              }
            }
          },
          "isAutomated": false,
          "automatedBy": null
        },
        "extendedEntities": {},
        "card": null,
        "place": {},
        "entities": {
          "user_mentions": [
            {
              "id_str": "902926941413453824",
              "indices": [
                0,
                11
              ],
              "name": "CZ 🔶 BNB",
              "screen_name": "cz_binance"
            }
          ]
        },
        "quoted_tweet": null,
        "retweeted_tweet": null,
        "isLimitedReply": false,
        "article": null
      },
      "retweeted_tweet": null,
      "isLimitedReply": false,
      "article": null
    }

"""
    try:
        sample_text = text
        if sample_text.strip():
            ai_summary = ai_analyze_text(sample_text)
            print("[AI  ] 摘要：\n", ai_summary)
        else:
            print("[AI  ] 无文本样本，跳过分析")
    except Exception as e:
        print("[WARN] AI 分析失败:", e)



if __name__ == "__main__":
    ensure_media_dir()
    result = run_once()
    print("[DONE] 运行结束:", result)