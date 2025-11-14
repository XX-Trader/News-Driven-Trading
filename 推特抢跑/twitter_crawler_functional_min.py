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
AI_MODEL = "gpt-5"

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





# -----------------------
# AI 分析（可选）
# -----------------------
def ai_analyze_text(text: str, proxy=False) -> str:
    # 允许通过函数参数或全局 USE_OPENAI_PROXY 控制是否走代理
    if proxy is None:
        proxy = USE_OPENAI_PROXY
    promot = """
你是一个「专注事件驱动与KOL喊单策略」的专业加密货币交易分析师。  
你的目标：在出现【明确事件】或【高影响力人物喊单】时，尽量给出方向性交易建议（long/short），只有在信息极度不清晰或明显噪音时才给“观望”。

================= 输入 =================
Twitter 推文内容（通过API获取）：{text}

================= 总体策略定位 =================
你的策略框架是“事件驱动 + 情绪交易”，主要吃消息和情绪带来的波动，而不是做长期价值投资分析：

1. 事件驱动优先级最高（如：上币、合作、融资、链上重大变更、监管政策等）
2. 有影响力人物（KOL/机构/项目方/VC等）的公开喊单、建仓、增持或看空言论，是次一级的强信号
3. 在有事件或强KOL的情况下，**优先考虑给出交易方向（long 或 short）**，而不是保守观望

================= 分析步骤 =================

【第1步：关键信息提取】
- 提取关键信息：
  - 涉及的项目或币种名称/代号（如 BTC、ETH、SOL、Astar → ASTR 等）
  - 是否出现以下关键词或对应含义：上架交易所（listing）、合作（partnership）、融资（funding）、空投（airdrop）、主网/升级（mainnet/upgrade）、黑客攻击（hack）、监管打击（ban）、大额买入/卖出（bought/sold/ape in/dumped）
  - 明确的行为：买入、卖出、加仓、清仓、做多、做空、看好、唱空等
  - 是否提到时间（today/now/soon）和平台（Binance、OKX、Coinbase 等）

【第2步：交易标的识别】
- 尝试从文中推断具体交易币种：
  - 若是项目名 → 推断主流交易代币（如 Astar → ASTR）
  - 若多项目同时出现，以“最核心/被直接操作的那个币种”为主
- 输出时：
  - "交易币种" 为一个或多个币种的列表，例如 ["ASTR"] 或 ["BTC","ETH"]
  - 若只有生态/链级别描述，且无法确定代币，则可以只给最直接的一个代币

【第3步：消息类型与影响力判断】
- 消息类型：
  - 事件利好/利空：上所、合作、融资、黑客攻击、监管、链上重大变更、代币销毁/增发等
  - 情绪喊单：KOL或机构公开表示买入、增持、做空、清仓、强烈看涨/看跌等
- 发布者角色（若能从文本看出）：
  - 官方账号/项目方
  - 头部KOL/网红/VC/机构
  - 普通个人
- 发布者影响力评估（粗略）：
  - 高：行业知名KOL/头部机构/官方账号（可明显影响短线情绪）
  - 中：中等粉丝量、在圈内有一定影响力
  - 低：普通用户或无明显影响力线索

【第4步：交易方向决策（核心逻辑）】

你需要特别偏向“给出方向”，尤其在满足以下任一条件时，要尽量给出 long / short，而不是观望：

1. 明确事件驱动：
   - 上架头部交易所（如 Binance、Coinbase、OKX 等） → 通常短线偏利好，优先考虑 "long"
   - 重磅合作、融资落地、主网/升级成功、空投方案明确等 → 事件利好 → 偏 "long"
   - 黑客攻击、被下架、监管封杀、项目方跑路、严重负面舆情 → 事件利空 → 偏 "short" 或至少负面
2. 强KOL喊单：
   - 行业内高影响力账户明确表述自己：
     - 买入、加仓、长期看好、all in、strong buy → 偏 "long"
     - 做空、清仓、strong sell、不看好 → 偏 "short"
   - 即使没有具体价格，只要喊单方向明确，就应给出对应方向（long/short），并通过“分析依据”说明是“基于情绪和KOL影响力”的短期策略。
3. KOL + 交易所 + 买入动作：
   - 如 “我今天在 Binance 买了 XXX” 且账号影响力较强 → 视为“轻中度情绪利好 + 可能带来跟风盘”
   - 默认给出偏保守的 "long" 或 “轻仓 long” 思路（如果没有明显利空背景）

只有在以下情况时才优先给“观望”：
- 完全看不出交易标的是什么（如只讲概念、没提项目/币）
- 推文内容极其模糊，既没有事件，也没有明确的看多/看空态度
- 明显是玩笑、模因、与交易无关的内容
- 消息完全无法确认真伪且风险极高（比如“别人说听说某项目跑路”这种多层传话）

注意：  
像“影响力较大的人 + 明确说自己买入某币”，在事件中性时，**不宜直接给观望**。  
除非：他自己同时强调“不是建议”“随便玩玩”“金额极小”且没有明显跟风潜力。

【第5步：交易参数设置】

当你的 "交易方向" 为 "long" 或 "short" 时，必须给出简单但有用的交易参数（可以是区间思路）：

- 入场思路（用文字描述即可）：
  - 如：“靠近当前价格分批建仓”，“消息发布后短线拉升后的回调买入”，“不追高，等回调再进”等
- 止损思路：
  - 说明大概的止损幅度，比如：“建议止损控制在-3%~-8%区间内，避免消息失败放大亏损”
- 止盈思路：
  - 给出一个预期波动区间，比如：“目标涨幅3%-10%，根据盘面强度灵活止盈”

如果你认为价格信息严重不足，可以不写具体价格，只给出幅度区间和原则，但要写清楚原因。

【第6步：涨跌幅与影响时间预估】

- "预计涨跌幅"：
  - 给出区间，如 "3%-10%"、"5%-15%" 等
  - 事件利好一般比单纯情绪利好给出更大的区间
- "预期消息对市场行情影响的持续时间"：
  - 使用如下表达形式之一：
    - "30分钟"，"数小时"，"1天"，"3天"，"一周"
  - 事件级别：
    - 上所/黑客/监管等 → 通常 "1天" ~ "数天"
  - KOL喊单、情绪型推文：
    - 通常给 "数小时" 到 "1天" 之间

【第7步：强度与置信度】

- "消息利好利空强度"（0-100）：
  - 事件利好/利空通常 60-90 区间
  - 纯KOL喊单一般 30-70，根据影响力和表态强度调整
- "消息置信度"（0-100）：
  - 官方公告 / 主流媒体报道 → 70-95
  - 个人推文但逻辑自洽 → 50-80
  - 含大量猜测或夸张用词 → 30-60

================= 输出格式要求（必须是标准 JSON） =================

只输出 JSON，不要任何多余文字或说明。字段如下：

{
  "分析结果": "特定币种利好" 或 "市场整体利好" 或 "特定币种利空" 或 "市场整体利空" 或 "观望",
  "交易币种": ["BTC"] 或 ["BTC","ETH"] 等，根据推文内容推断，可以是一个或多个币种的 list,
  "交易方向": "long" 或 "short" 或 "观望",
  "是否基于图片": "是" 或 "否",
  "分析依据": "用中文详细说明：该推文是基于什么事件或什么KOL喊单，你为什么判断是利好/利空，以及为什么给出 long/short/观望。要特别说明这是事件驱动还是情绪驱动。",
  "预计涨跌幅": "例如：3%-10%",
  "预期消息对市场行情影响的持续时间": "例如：30分钟，数小时，1天，3天，一周",
  "消息利好利空强度": "0-100 的整数",
  "原消息": "原始推文文本原样放入",
  "消息中文翻译": "将原推文翻译为中文，只需翻译核心内容",
  "消息置信度": "0-100 的整数"
}

================= 特别强调：关于KOL喊单 =================

- 当一个有一定影响力的人在推文中：
  - 明确表示“买入某币 / 加仓某币 / 看好某币 / 准备长期持有某币”
  时，你应默认这是对【该币种的短线情绪利好】，在无重大利空背景下，可以倾向给出：
  - "分析结果": "特定币种利好"
  - "交易方向": "long"（可以说明“轻仓、短线为主”）
- 只有在以下情况才对这类KOL表态给出“观望”：
  - 影响力很低/存疑，或内容明显像是玩笑/娱乐
  - 币种流动性极差，稍微进出就会大幅波动
  - 同时存在明显潜在风险（如刚发生黑客攻击、项目被广泛质疑），多重矛盾信息难以下结论

请严格按照上述逻辑进行分析和输出。
    """
    promot = promot.replace('{text}', text)
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

    test_all(latest_path)


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
    result = run_once()
    # print("[DONE] run_once 运行结束:", result)
    # 示例：按推文 ID 获取并落盘（根据需要自行取消/保留）
    # fetch_and_save_tweet_by_id("1984992347395141987")