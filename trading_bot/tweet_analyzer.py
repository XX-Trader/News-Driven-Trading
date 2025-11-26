"""
trading_bot.tweet_analyzer

从 notebook trading_bot/twitter_analysis one.ipynb 抽离的核心分析函数。
职责：AI 分析推文文本 → 提取交易币种、方向、置信度

设计：
- call_ai_for_tweet_async(text, author, introduction, timeout=30) → Dict[str, Any]
  异步调用 Poe API（v1.2.0，用于后台队列处理）
  
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
    base_dir = Path(__file__).resolve().parent
    prompt_path = base_dir / "提示词.txt"
    
    if not prompt_path.exists():
        print(f"[DEBUG] 提示词文件不存在: {prompt_path}")
        return "(提示词文件不存在)"
    
    prompt = read_text(str(prompt_path))
    prompt = prompt.replace('{text1}', text)
    prompt = prompt.replace('{text2}', author)
    prompt = prompt.replace('{text3}', introduction)
    
    # 调试信息：打印配置和提示词
    print(f"[DEBUG] AI配置 - API Key: {config.ai.poe_api_key[:10]}..., Base URL: {config.ai.poe_base_url}, Model: {config.ai.poe_model}")
    print(f"[DEBUG] 代理配置 - 使用代理: {getattr(config.ai, 'use_proxy', None)}")
    print(f"[DEBUG] 提示词长度: {len(prompt)} 字符")
    print(f"[DEBUG] 输入参数 - 作者: {author}, 文本长度: {len(text)} 字符")
    
    try:
        import openai
        
        # v2.1.0: 简化代理逻辑，直接使用配置（移除网络检测依赖）
        # 如果配置中设置了代理，则使用；否则直连
        proxy_config = getattr(config.ai, 'proxy_config', None)
        proxy_con = proxy_config and (proxy_config.get('http') and proxy_config.get('https'))
        use_proxy = getattr(config.ai, 'use_proxy', None)
        
        print(f"[DEBUG] 代理详情 - HTTP: {proxy_config.get('http') if proxy_config else None}, HTTPS: {proxy_config.get('https') if proxy_config else None}")
        
        if use_proxy and proxy_con:
            # 配置中设置了代理，使用代理
            print("[DEBUG] 使用代理连接")
            try:
                from httpx import Client as _HttpxClient
                # httpx 的代理配置
                http_proxy = proxy_config.get('http', '') if proxy_config else ''
                https_proxy = proxy_config.get('https', '') if proxy_config else ''
                print(f"[DEBUG] 创建 httpx 客户端，HTTP代理: {http_proxy}, HTTPS代理: {https_proxy}")
                http_client = _HttpxClient(
                    proxies={
                        'http://': http_proxy,
                        'https://': https_proxy
                    },
                    timeout=30.0
                )
                client = openai.OpenAI(
                    api_key=config.ai.poe_api_key,
                    base_url=config.ai.poe_base_url,
                    http_client=http_client
                )
                print("[DEBUG] OpenAI 客户端创建成功（使用代理）")
            except Exception as proxy_error:
                # 备用方案：使用环境变量
                print(f"[DEBUG] 代理创建失败，回退到环境变量: {proxy_error}")
                import os as _os
                _os.environ["HTTP_PROXY"] = proxy_config.get("http", "") if proxy_config else ""
                _os.environ["HTTPS_PROXY"] = proxy_config.get("https", "") if proxy_config else ""
                client = openai.OpenAI(
                    api_key=config.ai.poe_api_key,
                    base_url=config.ai.poe_base_url
                )
                print("[DEBUG] OpenAI 客户端创建成功（环境变量代理）")
        else:
            # 无代理配置，直连
            print("[DEBUG] 直连模式（无代理）")
            client = openai.OpenAI(
                api_key=config.ai.poe_api_key,
                base_url=config.ai.poe_base_url
            )
            print("[DEBUG] OpenAI 客户端创建成功（直连）")
        
        print("[DEBUG] 发送 API 请求...")
        chat = client.chat.completions.create(
            model=config.ai.poe_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=500,
        )
        print("[DEBUG] API 请求成功")
        
        # 兼容不同的返回结构
        content: Any = None
        if chat and getattr(chat, "choices", None):
            print(f"[DEBUG] 返回选项数量: {len(chat.choices)}")
            choice0 = chat.choices[0]
            msg = getattr(choice0, "message", None)
            if isinstance(msg, dict):
                content = msg.get("content")
            else:
                content = getattr(msg, "content", None)
        else:
            print("[DEBUG] API 返回结构异常: 无 choices 属性")
            print(f"[DEBUG] 完整返回对象: {chat}")
        
        print(f"[DEBUG] 提取的内容: {content}")
        result = content or "(AI 无内容返回)"
        print(f"[DEBUG] 最终返回结果长度: {len(result)} 字符")
        return result
    
    except Exception as e:
        # 修复：标准化错误处理，抛出异常而非返回字符串
        print(f"[DEBUG] AI分析异常: {type(e).__name__}: {e}")
        import traceback
        print(f"[DEBUG] 异常堆栈: {traceback.format_exc()}")
        raise RuntimeError(f"AI分析失败: {e}") from e


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
            print("[AI_ASYNC] raw_result:", raw_result)
            return json.loads(raw_result)
        except json.JSONDecodeError:
            # 如果不是 JSON，返回原始字符串包装
            print(f"不是 JSON，返回原始字符串包装")
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


if __name__ == "__main__":
    # 测试代码
    def test_ai_analyze():
        result = ai_analyze_text(
            text="""tweet_preview": "Full disclosure. I just bought some Aster today, using my own money, on @Binance.  I am not a trader...""",
            author="cz_binance",
            introduction="BINANCE创始人，全球最大加密货币交易所龙头"
        )
        print("AI 分析结果:", result)
        # 尝试解析结果为JSON，然后检测交易对
        try:
            import json
            result_dict = json.loads(result) if isinstance(result, str) else result
            symbol = detect_trade_symbol(result_dict)
        except:
            symbol = None
        print("检测到的交易对:", symbol)

    test_ai_analyze()