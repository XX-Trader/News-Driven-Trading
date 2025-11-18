"""
trading_bot.twitter_source

推特数据源抽象层。支持多种推文获取方式：
1. 并发 API 抓取多个用户的推文（twitterapi.io）
2. 本地 JSON 文件扫描（降级方案）
3. 推文 ID 去重缓存（避免重复 AI 分析）

设计理念：
- fetch_latest_tweets() 作为唯一数据入口
- 支持"测试→生产"无缝切换
- 已处理推文 ID 存储在 processed_ids.json，下次无需重复 AI 分析
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

def safe_unicode_str(text: Any) -> str:
    """
    安全的 Unicode 字符串处理，移除或替换可能在 Windows GBK 终端引起问题的字符。
    
    处理策略：
    1. 转换为字符串
    2. 替换表情符号和特殊 Unicode 字符为空格
    3. 确保最终字符串可以在 GBK 环境中安全输出
    """
    if text is None:
        return ""
    
    str_text = str(text)
    
    # 替换可能导致 GBK 编码问题的 Unicode 字符
    # 这里包括一些常见的表情符号和特殊字符范围
    safe_text = ""
    for char in str_text:
        # 检查字符是否在基本 ASCII 和中文字符范围内
        if (ord(char) < 128) or (0x4e00 <= ord(char) <= 0x9fff):
            safe_text += char
        else:
            # 其他 Unicode 字符替换为空格
            safe_text += " "
    
    return safe_text.strip()

try:
    import aiohttp
except ImportError:
    aiohttp = None

if TYPE_CHECKING:
    import aiohttp as aiohttp_typing

try:
    from config import TwitterAPIConfig, load_config
except ImportError:
    from .config import TwitterAPIConfig, load_config


# ==================== 日志存储 ====================

def _get_user_logs_path(username: str) -> Path:
    """获取用户推文日志文件路径（JSONL 格式）"""
    base_dir = Path(__file__).resolve().parent.parent
    logs_dir = base_dir / "推特抢跑" / "twitter_media" / "user_logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir / f"{username}.jsonl"


def _append_tweet_to_jsonl(username: str, tweet: Dict[str, Any]) -> None:
    """
    将单条推文追加写入 JSONL 日志文件。
    
    设计考虑：
    - 使用 JSONL 格式（每行一个 JSON 对象），支持高效追加和流式读取
    - 文件名基于用户名，便于按用户分析
    - 使用 UTF-8 编码和 ensure_ascii=True 确保 Windows 兼容（避免 GBK 编码错误）
    
    参数：
    - username: 推文作者的用户名
    - tweet: 推文数据字典，必须包含 id、text 等字段
    """
    try:
        # 确保用户名是安全的字符串
        safe_username = safe_unicode_str(username)
        if not safe_username or safe_username == "unknown":
            safe_username = "anonymous"
        
        # 移除可能的文件系统危险字符
        safe_username = safe_username.replace("/", "_").replace("\\", "_").replace(":", "_")
        
        log_path = _get_user_logs_path(safe_username)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(tweet, ensure_ascii=True) + "\n")
    except Exception as e:
        print(f"[TWITTER_API] 写入推文日志失败: {safe_unicode_str(e)}")


# ==================== 缓存管理 ====================

def _get_processed_ids_path() -> Path:
    """获取已处理推文 ID 缓存文件路径"""
    base_dir = Path(__file__).resolve().parent.parent
    media_dir = base_dir / "推特抢跑" / "twitter_media"
    media_dir.mkdir(parents=True, exist_ok=True)
    return media_dir / "processed_ids.json"


def load_processed_ids() -> Set[str]:
    """从本地 JSON 加载已处理的推文 ID"""
    path = _get_processed_ids_path()
    if not path.exists():
        return set()
    
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # data 可能是 list 或 dict{"ids": [...]}
        if isinstance(data, dict):
            return set(str(id_) for id_ in data.get("ids", []))
        elif isinstance(data, list):
            return set(str(id_) for id_ in data)
        return set()
    except Exception as e:
        print(f"[TWITTER_API] 读取 processed_ids 失败: {safe_unicode_str(e)}")
        return set()


def save_processed_ids(ids: Set[str]) -> None:
    """将已处理的推文 ID 保存到本地 JSON"""
    path = _get_processed_ids_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"ids": sorted(list(ids))}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[TWITTER_API] 保存 processed_ids 失败: {safe_unicode_str(e)}")


def mark_as_processed(tweet_ids: List[str]) -> None:
    """标记推文 ID 为已处理（追加到缓存）"""
    processed = load_processed_ids()
    processed.update(str(id_) for id_ in tweet_ids)
    save_processed_ids(processed)


# ==================== 本地 JSON 读取 ====================

def fetch_latest_tweets_from_local_json() -> List[Dict[str, Any]]:
    """
    从 推特抢跑/twitter_media/ 目录扫描所有 JSON 文件，
    合并为推文列表返回。
    
    支持两种 JSON 格式：
    1. 单条推文：{"id": "xxx", "text": "...", "user_name": "..."}
    2. 推文列表：[{"id": "..."}, {"id": "..."}, ...]
    
    返回：
    - 去重后的推文列表，每条至少包含 id、text、user_name 字段
    """
    base_dir = Path(__file__).resolve().parent.parent
    media_dir = base_dir / "推特抢跑" / "twitter_media"
    
    if not media_dir.exists():
        print(f"[TWITTER_API] media_dir not found: {media_dir}")
        return []
    
    tweets: List[Dict[str, Any]] = []
    seen_ids: set = set()
    
    # 扫描所有 .json 文件
    for json_file in sorted(media_dir.glob("*.json")):
        # 跳过处理文件
        if json_file.name in ("processed_ids.json",):
            continue
        
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # 处理单条推文 or 推文列表
            items = []
            if isinstance(data, dict):
                # 检查是否是单条推文（有 id、text 字段）
                if "id" in data and "text" in data:
                    items = [data]
                else:
                    # 可能是 {"tweets": [...]} 格式
                    items = data.get("tweets", [])
            elif isinstance(data, list):
                items = data
            
            # 添加到结果，去重
            for item in items:
                if isinstance(item, dict):
                    item_id = str(item.get("id", ""))
                    if item_id and item_id not in seen_ids:
                        seen_ids.add(item_id)
                        tweets.append(item)
        
        except Exception as e:
            print(f"[TWITTER_API] 读取 {safe_unicode_str(json_file.name)} 失败: {safe_unicode_str(e)}")
    
    return tweets


# ==================== API 并发抓取 ====================

async def _fetch_for_user_async(
    session: Any,
    username: str,
    config: TwitterAPIConfig,
    timeout: float = 30.0
) -> List[Dict[str, Any]]:
    """
    异步调用 API 获取单个用户的推文。
    
    参数：
    - session: aiohttp ClientSession
    - username: 推特用户名（不含@）
    - config: TwitterAPIConfig 配置
    - timeout: 请求超时（秒）
    
    返回：推文列表（支持多格式兼容）
    """
    params = {
        "userName": username.lstrip("@"),
        "count": 10,  # 单次获取 10 条
    }
    headers = {"X-API-Key": config.api_key}
    
    try:
        async with session.get(
            config.user_last_tweets_url,
            params=params,
            headers=headers,
            timeout=timeout
        ) as resp:
            if resp.status != 200:
                print(f"[TWITTER_API] {username} 请求失败: {resp.status}")
                return []
            
            data = await resp.json()
            
            # 多格式兼容：dict 或 list
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                # 尝试多个常见字段
                return data.get("data") or data.get("tweets") or data.get("results") or []
            return []
    
    except asyncio.TimeoutError:
        print(f"[TWITTER_API] {username} 请求超时（{timeout}s）")
        return []
    except Exception as e:
        print(f"[TWITTER_API] {username} 请求异常: {safe_unicode_str(e)}")
        return []


async def fetch_latest_tweets_from_api() -> List[Dict[str, Any]]:
    """
    并发抓取多个用户的推文，支持 ID 去重与缓存。
    
    流程：
    1. 从 config.twitter_api.user_intro_mapping 获取用户列表
    2. 并发调用 API 获取所有用户的推文
    3. 去除已在 processed_ids.json 中的推文，输出跳过日志
    4. 返回新推文列表
    
    注意：API 失败时输出警告，不自动降级
    """
    if aiohttp is None:
        print("[TWITTER_API] ⚠️ aiohttp 未安装，无法调用 API。建议：pip install aiohttp")
        return []
    
    config = load_config()
    usernames = list(config.twitter_api.user_intro_mapping.keys())
    
    if not usernames:
        print("[TWITTER_API] ⚠️ 用户列表为空，无法抓取推文")
        return []
    
    print(f"[TWITTER_API] 并发抓取 {len(usernames)} 个用户的推文...")
    
    try:
        # 并发调用 API
        async with aiohttp.ClientSession() as session:
            tasks = [
                _fetch_for_user_async(session, username, config.twitter_api)
                for username in usernames
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 合并结果 + 去重
        all_tweets: List[Dict[str, Any]] = []
        seen_ids: Set[str] = set()
        processed_ids = load_processed_ids()
        skipped_count = 0
        
        for result in results:
            if isinstance(result, Exception):
                continue
            if isinstance(result, list):
                for tweet in result:
                    if isinstance(tweet, dict):
                        tweet_id = str(tweet.get("id", ""))
                        if not tweet_id:
                            continue
                        
                        # 检查是否已处理（历史缓存）- 直接跳过，无日志
                        if tweet_id in processed_ids:
                            skipped_count += 1
                            continue
                        
                        # 检查本次会话是否重复
                        if tweet_id in seen_ids:
                            continue
                        
                        seen_ids.add(tweet_id)
                        all_tweets.append(tweet)
                        
                        # 记录推文到 JSONL（获取用户名）
                        user_name = tweet.get("user_name") or tweet.get("author") or "unknown"
                        if isinstance(user_name, dict):
                            # 如果用户名是字典对象，从中提取实际的用户名
                            user_name = user_name.get("userName") or user_name.get("name") or "unknown"
                        # 先转换为字符串，再进行安全清理
                        username = safe_unicode_str(str(user_name))
                        _append_tweet_to_jsonl(username, tweet)  # 修复参数顺序
        
        if all_tweets:
            print(f"[TWITTER_API] 获取 {len(all_tweets)} 条新推文，跳过 {skipped_count} 条已处理推文")
        else:
            if skipped_count > 0:
                print(f"[TWITTER_API] 无新推文（全部 {skipped_count} 条已处理）")
            else:
                print("[TWITTER_API] 无新推文")
        
        return all_tweets
    
    except Exception as e:
        print(f"[TWITTER_API] API抓取失败: {safe_unicode_str(e)}。建议检查网络连接或API配置")
        return []


# ==================== 异步入口 ====================

async def fetch_latest_tweets() -> List[Dict[str, Any]]:
    """
    获取最新推文的异步接口（推荐方法）。
    
    版本切换说明：
    - 初期测试：使用本地版本
    - 后期集成：使用 API 版本
    
    在 app_runner.py 中的调用处选择其中一个：
      # return await fetch_latest_tweets_from_api_with_logging()     # 后期：真实 API
      # return await fetch_latest_tweets_from_local_with_logging()   # 初期：本地测试
    
    返回：推文列表，每条至少包含 id、text 字段
    """
    # 【初期开发推荐】使用本地版本测试
    return await fetch_latest_tweets_from_local_with_logging()
    # return await fetch_latest_tweets_from_api_with_logging() 

async def fetch_latest_tweets_from_api_with_logging() -> List[Dict[str, Any]]:
    """
    【版本 A - API 版】并发抓取多个用户的推文（后期集成）
    
    配置项：需要设置 TwitterAPIConfig 中的 api_key 和其他参数
    推荐用途：生产环境，真实推特数据
    
    流程同 fetch_latest_tweets_from_api()，支持 JSONL 日志记录
    """
    return await fetch_latest_tweets_from_api()


async def fetch_latest_tweets_from_local_with_logging() -> List[Dict[str, Any]]:
    """
    【版本 B - 本地版】从本地 JSON 读取推文并记录到 JSONL（初期测试推荐）
    
    配置项：无需 API 密钥，直接读取 推特抢跑/twitter_media/*.json
    推荐用途：初期开发、功能验证、快速迭代
    
    特性：
    - 支持与 API 版本相同的 JSONL 日志记录
    - 无网络依赖，速度快
    - 适合全流程功能验证
    """
    tweets = fetch_latest_tweets_from_local_json()
    print(f"[TWITTER_API] 获取 {len(tweets)} 条本地推文")
    # 记录到 JSONL
    for tweet in tweets:
        # 确保用户名是简单的字符串，避免包含完整用户对象
        user_name = tweet.get("user_name") or tweet.get("author") or "unknown"
        if isinstance(user_name, dict):
            # 如果用户名是字典对象，从中提取实际的用户名
            user_name = user_name.get("userName") or user_name.get("name") or "unknown"
        # 先转换为字符串，再进行安全清理
        username = safe_unicode_str(str(user_name))
        _append_tweet_to_jsonl(username, tweet)
    
    return tweets


# ==================== v1.4.0 动态触发框架说明（仅框架，待后期实现）====================
#
# 背景：目前推特查询是定时固定执行的。后期需要根据 K 线信号（如成交量异动）动态启动。
#
# 框架设计思路：
# 1. 监听 K 线成交量异动信号（来自 signals.py）
# 2. 触发条件满足时启动 10 分钟的查询周期
# 3. 查询间隔：每 5 秒查询一次
# 4. 支持动态用户列表切换（根据异动币种切换查询的意见领袖）
#
# 伪代码框架（待实现）：
#
#   class TwitterTrigger:
#       def __init__(self, duration_seconds: int = 600, interval_seconds: float = 5):
#           self.duration = duration_seconds
#           self.interval = interval_seconds
#           self.trigger_start_time: Optional[float] = None
#           self.active_usernames: List[str] = []
#       
#       def is_triggered(self, signal: Dict[str, Any]) -> bool:
#           """检查成交量异动信号"""
#           pass
#       
#       def get_active_users(self, signal: Dict[str, Any]) -> List[str]:
#           """根据异动币种返回相关意见领袖列表"""
#           pass
#       
#       async def run_trigger_window(self, fetch_func, signal):
#           """执行 10 分钟查询窗口（5 秒间隔）"""
#           pass
#
# 集成方案（待实现）：
# - 在 app_runner.py 中监听信号流
# - 当检测到成交量异动时，启动 TwitterTrigger 实例
# - 10 分钟后自动停止，恢复定时查询模式