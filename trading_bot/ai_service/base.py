"""
AI服务抽象基类

定义统一的AI调用接口，遵循极简MVP原则：
- 只定义接口契约，不实现具体逻辑
- 返回原始字符串，调用方负责解析
- 不处理降级、重试等复杂逻辑
"""

from abc import ABC, abstractmethod


class AIService(ABC):
    """
    AI服务抽象基类
    
    职责：
    - 定义统一的AI调用接口
    - 不实现具体逻辑，只定义契约
    - 返回原始字符串，调用方负责解析
    
    设计原则：
    - 简化：只定义一个核心接口
    - 解耦：不依赖任何具体实现
    - 灵活：调用方完全控制prompt和结果处理
    """
    
    @abstractmethod
    async def call_api(self, prompt: str) -> str:
        """
        调用AI API
        
        Args:
            prompt: 完整的提示词字符串（外部已处理好）
            
        Returns:
            AI返回的原始响应字符串（JSON或其他格式）
            
        注意：
            - 不处理降级逻辑
            - 不处理重试逻辑
            - 不解析返回结果
            - 调用方需自行处理异常
        """
        pass