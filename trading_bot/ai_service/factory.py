"""
AI服务工厂模块

提供统一的AI服务实例创建接口，支持根据配置动态选择提供者
"""

try:
    from ..config import AppConfig
    from .base import AIService
    from .poe_ai import PoeAIProvider
    from .openrouter_ai import OpenRouterAIProvider
except ImportError:
    from config import AppConfig
    from ai_service.base import AIService
    from ai_service.poe_ai import PoeAIProvider
    from ai_service.openrouter_ai import OpenRouterAIProvider


class AIServiceFactory:
    """
    AI服务工厂类
    
    职责：
    - 根据配置创建AI服务提供者实例
    - 支持动态选择提供者类型
    - 不包含降级逻辑，只负责实例创建
    
    设计原则：
    - 简化：使用简单的if/elif逻辑
    - 明确：不支持的服务名称抛ValueError
    - 解耦：调用方完全控制使用哪个提供者
    """
    
    @staticmethod
    def create_provider(config: AppConfig, provider_name: str = None) -> AIService:
        """
        创建AI服务提供者实例
        
        Args:
            config: 应用配置对象
            provider_name: 提供者名称（"poe"或"openrouter"），为None时使用配置中的默认值
            
        Returns:
            AIService: AI服务提供者实例
            
        Raises:
            ValueError: 如果provider_name不支持
        """
        # 如果未指定提供者名称，使用配置中的默认值
        if provider_name is None:
            provider_name = config.ai.default_provider
        
        # 根据提供者名称创建相应实例
        if provider_name == "poe":
            return PoeAIProvider(config)
        elif provider_name == "openrouter":
            return OpenRouterAIProvider(config)
        else:
            # 不支持的服务名称，抛出明确错误
            raise ValueError(f"不支持的AI提供者: '{provider_name}'。支持的提供者: 'poe', 'openrouter'")