"""
trading_bot.tweet_analyzer

从 notebook 推特抢跑/twitter_analysis one.ipynb 抽离的核心分析函数。
职责：AI 分析推文文本 → 提取交易币种、方向、置信度

设计：
- call_ai_for_tweet(text, author, introduction) → Dict[str, Any]
  同步调用 Poe API 分析推文（v1.0.0，已弃用）
  
- call_ai_for_tweet_async(text, author, introduction, timeout=30) → Dict[str, Any]
  异步调用 Poe API（v1.2.0，新增，用于后台队列处理）
  
- detect_trade_symbol(ai_res) → Optional[str]
  从 AI 结果提取交易币种，转换为 Binance symbol 格式 (e.g., "BTCUSDT")
"""

from __future__ import annotations

import json
import asyncio
from typing import Any, Dict, Optional
from pathlib import Path

try:
    from config import load_config
except ImportError:
    from .config import load_config


def read_text(path: str) -> str:
    """读取文本文件，返回内容。"""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def ai_analyze_text(text: str, author: str, introduction: str) -> str:
    """
    调用 Poe(OpenAI 兼容) API 分析推文文本。
    
    参数：
    - text: 推文原始内容
    - author: 推文作者名称
    - introduction: 作者简介（用于增强 AI 上下文）
    
    返回：AI 返回的原始字符串（通常为 JSON 格式，由提示词.txt 决定）
    """
    config = load_config()
    
    # 读取系统提示词并填充占位符
    base_dir = Path(__file__).resolve().parent.parent
    prompt_path = base_dir / "推特抢跑" / "提示词.txt"
    
    if not prompt_path.exists():
        return "(提示词文件不存在)"
    
    prompt = read_text(str(prompt_path))
    prompt = prompt.replace('{text1}', text)
    prompt = prompt.replace('{text2}', author)
    prompt = prompt.replace('{text3}', introduction)
    
    try:
        import openai
        
        # 根据代理配置选择连接方式
        proxy_config = config.proxy
        client = openai.OpenAI(
            api_key=config.ai.poe_api_key,
            base_url=config.ai.poe_base_url
        )
        
        chat = client.chat.completions.create(
            model=config.ai.poe_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=500,
        )
        
        # 兼容不同的返回结构
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
        return f"(AI 错误：{e})"




def normalize_symbol_from_ai(ai_res: Dict[str, Any]) -> Optional[str]:
    """
    从 AI 结果中提取交易币种并映射为 Binance 现货 symbol。
    
    AI 返回示例：
    {
        "交易币种": "BTC" 或 ["BTC", "ETH"],
        "交易方向": "做多",
        "消息置信度": 85,
        ...
    }
    
    返回：格式化的 symbol，如 "BTCUSDT" 或 None
    """
    raw_symbol = ai_res.get("交易币种")
    
    if isinstance(raw_symbol, list) and raw_symbol:
        first = str(raw_symbol[0]).upper()
    elif isinstance(raw_symbol, str) and raw_symbol.strip():
        first = raw_symbol.strip().upper()
    else:
        return None
    
    # 清理格式：移除 USDT、/ 等
    base = first.replace("USDT", "").replace("/", "").upper()
    
    return base + "USDT" if base else None


async def call_ai_for_tweet_async(
    text: str,
    author: str,
    introduction: str,
    timeout: int = 30
) -> Dict[str, Any]:
    """
    异步调用 AI 分析推文（v1.2.0 新增）。
    
    参数：
    - text: 推文原始内容
    - author: 推文作者名称
    - introduction: 作者简介
    - timeout: 超时时间（秒），默认 30 秒
    
    返回：
    - AI 分析结果（dict）
    
    异常：
    - asyncio.TimeoutError: 超过 timeout 时间
    
    用途：
    - 在后台异步队列中使用，不阻塞主循环
    - 由 worker 任务调用，处理来自队列的推文
    """
    loop = asyncio.get_event_loop()
    
    # 在线程池中运行同步 AI 调用，避免阻塞
    try:
        raw_result = await asyncio.wait_for(
            loop.run_in_executor(None, ai_analyze_text, text, author, introduction),
            timeout=timeout
        )
        
        # 尝试解析 AI 返回的 JSON 结果
        try:
            import json
            return json.loads(raw_result)
        except json.JSONDecodeError:
            # 如果不是 JSON，返回原始字符串包装
            return {"raw": raw_result}
    except asyncio.TimeoutError:
        print(f"[AI_ASYNC] timeout after {timeout}s for tweet by {author}")
        raise


def detect_trade_symbol(ai_res: Dict[str, Any]) -> Optional[str]:
    """
    综合 AI 输出，推断最终可交易 symbol。
    
    参数：
    - ai_res: AI 分析结果（dict）
    
    返回：
    - 有效的 symbol（如 "BTCUSDT"）
    - 或 None（无法确定交易对）
    """
    # 若是原始字符串包装，先解包
    if "raw" in ai_res and len(ai_res) == 1:
        return None  # 无法从原始字符串解析
    
    return normalize_symbol_from_ai(ai_res)