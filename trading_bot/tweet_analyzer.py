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
import re
from typing import Any, Dict, Optional
from pathlib import Path

try:
    from config import load_config, AppConfig
    from ai_service import AIServiceFactory
except ImportError:
    from .config import load_config, AppConfig
    from .ai_service import AIServiceFactory


# ==================== 
# 新增：异步 HTTP AI 调用（替换 OpenAI SDK）
# ==================== 

import aiohttp


async def ai_analyze_text_async(
    text: str,
    author: str,
    introduction: str,
    config: AppConfig
) -> str:
    """
    使用 aiohttp 异步调用 Poe API 分析推文文本。
    
    已弃用：v1.4.0+ 请使用 AI 服务层（AIServiceFactory + AIService）
    
    参数：
    - text: 推文原始内容
    - author: 推文作者名称
    - introduction: 作者简介（用于增强 AI 上下文）
    - config: 应用配置，包含 API 密钥和代理设置
    
    返回：AI 返回的原始字符串（通常为 JSON 格式，由提示词.txt 决定）
    """
    print("[DEPRECATED] ai_analyze_text_async 已弃用，将使用 AI 服务层")
    
    # 使用新的AI服务层
    ai_service = AIServiceFactory.create_provider(config)
    prompt = _build_prompt(text, author, introduction)
    
    # 调用AI服务
    result = await ai_service.call_api(prompt)
    
    # 保持向后兼容：如果返回空字符串，转换为异常
    if not result:
        raise RuntimeError("AI 请求失败：返回空结果")
    
    return result


def read_text(path: str) -> str:
    """读取文本文件，返回内容。"""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


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
    config = load_config()
    
    # 创建AI服务实例
    ai_service = AIServiceFactory.create_provider(config)
    
    # 构建prompt
    prompt = _build_prompt(text, author, introduction)
    
    try:
        # 调用AI服务
        raw_result = await asyncio.wait_for(
            ai_service.call_api(prompt),
            timeout=timeout
        )
        
        # 处理空字符串返回情况（AI服务出错时返回空字符串）
        if not raw_result:
            print(f"[AI_ASYNC] AI服务返回空结果 for tweet by {author}")
            return {"raw": ""}
        
        # 尝试解析 AI 返回的 JSON 结果
        try:
            print("[AI_ASYNC] raw_result:", raw_result)
            
            # 先尝试直接解析（处理纯JSON情况）
            return json.loads(raw_result)
        
        except json.JSONDecodeError:
            # 如果失败，尝试从代码块中提取
            json_content = extract_json_from_text(raw_result)
            if json_content:
                try:
                    return json.loads(json_content)
                except json.JSONDecodeError as e:
                    print(f"提取的JSON解析失败: {e}")
                    return {"raw": raw_result}
            else:
                # 如果不是 JSON，返回原始字符串包装
                print(f"未提取到有效JSON，返回原始字符串包装")
                return {"raw": raw_result}
    
    except asyncio.TimeoutError:
        print(f"[AI_ASYNC] timeout after {timeout}s for tweet by {author}")
        raise


def _build_prompt(text: str, author: str, introduction: str) -> str:
    """
    构建AI分析用的prompt
    
    参数：
    - text: 推文原始内容
    - author: 推文作者名称
    - introduction: 作者简介
    
    返回：
    - 格式化后的prompt字符串
    """
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
    
    return prompt


def extract_json_from_text(text: str) -> Optional[str]:
    """
    从文本中提取JSON内容（支持多种格式）。
    
    支持格式：
    1. ```json ... ```
    2. ``` ... ```
    3. 最后的 {} 内容
    4. 纯JSON文本
    
    返回：
    - JSON字符串或None
    """
    if not text:
        return None
    
    json_content = None
    
    # 尝试匹配 ```json ... ```
    match = re.search(r'```json\s*([\s\S]*?)\s*```', text)
    if match:
        json_content = match.group(1).strip()
    
    # 尝试匹配 ``` ... ```
    if not json_content:
        match = re.search(r'```\s*([\s\S]*?)\s*```', text)
        if match:
            content = match.group(1).strip()
            # 检查是否是JSON（简单判断）
            if content.startswith('{') or content.startswith('['):
                json_content = content
    
    # 尝试提取最后的 {} 内容（匹配整个对象，包括大括号）
    if not json_content:
        match = re.search(r'\{[^}]*\}$', text)
        if match:
            json_content = match.group(0)
    
    # 尝试直接作为JSON文本
    if not json_content:
        stripped = text.strip()
        if stripped.startswith('{') or stripped.startswith('['):
            json_content = stripped
    
    if not json_content:
        return None
    
    # 修复JSON字符串中的非法换行符
    # AI 可能在字符串值中包含未转义的换行符，需要修复
    def fix_json_newlines(json_str: str) -> str:
        """
        修复JSON字符串中的未转义换行符。
        这是因为在JSON字符串值中，换行符必须转义为 \n 或 \r\n。
        """
        result = []
        i = 0
        in_string = False
        escaped = False
        
        while i < len(json_str):
            char = json_str[i]
            
            if escaped:
                # 当前字符是转义后的，直接添加
                result.append(char)
                escaped = False
            elif char == '\\':
                # 转义字符，下一个字符需要特殊处理
                result.append(char)
                escaped = True
            elif char == '"':
                # 字符串开始或结束
                in_string = not in_string
                result.append(char)
            elif in_string and (char == '\n' or char == '\r'):
                # 在字符串内部遇到换行符，需要转义
                if char == '\n':
                    result.append('\\n')
                # \r 通常与 \n 一起出现（\r\n），单独处理
                elif char == '\r':
                    # 检查是否是 \r\n
                    if i + 1 < len(json_str) and json_str[i + 1] == '\n':
                        result.append('\\r\\n')
                        i += 1  # 跳过下一个 \n
                    else:
                        result.append('\\r')
            else:
                result.append(char)
            
            i += 1
        
        return ''.join(result)
    
    # 修复JSON中的非法字符
    fixed_json = fix_json_newlines(json_content)
    
    return fixed_json


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
    async def test_ai_analyze():
        config = load_config()

        result = """
> 这个看起来符合所有要求。让我最后检查一遍：
> 1. 分析结果：特定币种利好 ✓
> 2. 交易币种：["Aster/USDT"] ✓（遵循所见即所得原则）
> 3. 交易方向：long ✓（明确买入行为）
> 4. 是否基于图片：否 ✓
> 5. 分析依据：详细说明了事件和判断逻辑 ✓
> 6. 预计涨跌幅：8%-15% ✓
> 7. 持续时间：数小时至1天 ✓
> 8. 影响力强度：92（整数）✓
> 9. 消息利好利空强度：88（整数）✓
> 10. 消息置信度：95（整数）✓
> 11. 消息中文翻译：准确翻译了核心内容 ✓
>
> 所有字段都是标准的JSON格式。没有其他文字。完美。

 ```json
{
  "分析结果": "特定币种利好",
  "交易币种": ["Aster/USDT"],
  "交易方向": "long",
  "是否基于图片": "否",
  "分析依据": "该推文属于顶级KOL喊单行为。Binance创始人CZ明确披露自己刚刚在Binance使用个人资金
购买了Aster代币，属于典型的情绪驱动型利好。作为加密货币行业最具影响力的领袖之一，CZ的个人买入 
行为具有极强的市场示范效应和情绪引导作用，通常会引发社区跟风买入。虽然CZ声明自己不是交易员，但
这反而增强了信息的真实性（个人投资而非项目推广），更易引发市场信任。此消息将直接利好Aster代币 
，预计会带动短线价格上涨。",
  "预计涨跌幅": "8%-15%",
  "预期消息对市场行情影响的持续时间": "数小时至1天",
  "影响力强度": 92,
  "消息利好利空强度": 88,
  "消息置信度": 95,
  "消息中文翻译": "完全披露。我今天刚刚在币安上用自己的钱买了一些Aster。我不是交易员..."      
}
```
"""     
        result = await ai_analyze_text_async(
        text="""tweet_preview": "Full disclosure. I just bought some Aster today, using my own money, on @Binance.  I am not a trader...""",
        author="cz_binance",
        introduction="BINANCE创始人，全球最大加密货币交易所龙头",
        config=config
        )
        print("AI 分析结果:", result)
        # 尝试解析结果为JSON，然后检测交易对
        try:
            print("[AI_ASYNC] raw_result:", result)
            
            # 先尝试直接解析（处理纯JSON情况）
            parsed_result = json.loads(result)
            print(f"[AI_ASYNC] 解析成功，返回结果: {parsed_result}")
            return parsed_result
        
        except json.JSONDecodeError:
            # 如果失败，尝试从代码块中提取
            json_content = extract_json_from_text(result)
            if json_content:
                try:
                    parsed_result = json.loads(json_content)
                    print(f"[AI_ASYNC] 从代码块提取JSON解析成功，返回结果: \n{parsed_result}")
                    return parsed_result
                except json.JSONDecodeError as e:
                    print(f"提取的JSON解析失败: {e}")
                    return {"raw": result}
            else:
                # 如果不是 JSON，返回原始字符串包装
                print(f"未提取到有效JSON，返回原始字符串包装")
                return {"raw": result}
        
    res = asyncio.run(test_ai_analyze())
    print(detect_trade_symbol(res))
