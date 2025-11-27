"""
AI服务模块

提供统一的AI调用接口抽象
"""

from .base import AIService
from .poe_ai import PoeAIProvider
from .openrouter_ai import OpenRouterAIProvider
from .factory import AIServiceFactory

__all__ = ["AIService", "PoeAIProvider", "OpenRouterAIProvider", "AIServiceFactory"]