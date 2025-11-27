"""
OpenRouter AI 服务适配器

实现 OpenRouter API 的 AI 服务调用，遵循统一接口规范
自动启用 reasoning 功能，支持思维链分析
"""

from __future__ import annotations

import json
import asyncio
from typing import Optional

import aiohttp

try:
    from ..config import AppConfig
except ImportError:
    from config import AppConfig


class OpenRouterAIProvider:
    """
    OpenRouter AI 服务提供者
    
    职责：
    - 实现 OpenRouter API 的异步调用
    - 自动启用 reasoning 功能，支持思维链分析
    - 处理代理配置和超时
    - 返回原始 AI 响应字符串
    
    设计原则：
    - 简化：直接发送 prompt，不处理模板
    - 解耦：调用方完全控制 prompt 和结果处理
    - 容错：错误时返回空字符串而非抛出异常
    - 智能：自动启用 reasoning，提供思维链分析
    """
    
    def __init__(self, config: AppConfig):
        """
        初始化 OpenRouter AI 提供者
        
        Args:
            config: 应用配置，包含 API 密钥和代理设置
        """
        self.config = config
    
    async def call_api(self, prompt: str) -> str:
        """
        调用 OpenRouter AI API
        
        Args:
            prompt: 完整的提示词字符串（已处理好）
            
        Returns:
            AI 返回的原始响应字符串，失败时返回空字符串
        """
        # 构建请求数据
        request_data = {
            "model": self.config.ai.openrouter_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            # 自动启用 reasoning 功能
            "reasoning": {
                "generate_summary": {}
            },
            # 配置 provider 参数
            "provider": {
                "order": ["openai"],
                "require_parameters": True
            }
        }
        
        # 构建请求头
        headers = {
            "Authorization": f"Bearer {self.config.ai.openrouter_api_key}",
            "Content-Type": "application/json",
        }
        
        # 构建代理配置
        proxy = None
        if self.config.proxy.use_proxy_by_default:
            proxy = self.config.proxy.proxy_url
        
        # API URL
        api_url = self.config.ai.openrouter_base_url
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    api_url,
                    data=json.dumps(request_data),
                    headers=headers,
                    proxy=proxy,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    
                    if response.status != 200:
                        error_text = await response.text()
                        print(f"[OpenRouterAIProvider] API 错误 (状态码 {response.status}): {error_text}")
                        return ""
                    
                    result = await response.json()
                    
                    # 提取 content
                    content = result.get("choices", [{}])[0].get("message", {}).get("content")
                    
                    if not content:
                        print(f"[OpenRouterAIProvider] 响应结构异常: {result}")
                        return ""
                    
                    return content
        
        except asyncio.TimeoutError:
            print("[OpenRouterAIProvider] AI 请求超时")
            return ""
        
        except Exception as e:
            print(f"[OpenRouterAIProvider] AI 请求异常: {type(e).__name__}: {e}")
            return ""