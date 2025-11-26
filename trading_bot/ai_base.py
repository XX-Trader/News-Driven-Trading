"""
trading_bot.ai_base

AI 模型抽象与路由骨架：

设计目标：
- 提供统一的 BaseAIModel 接口；
- AIModelRouter 支持并行调用多个模型，选择最快且结果合法的一个；
- 当前版本不强依赖具体大模型服务，只提供占位实现，后续可接入真实模型。

说明：
- 目前项目核心逻辑（下单、风控）可以在无 AI 的情况下运行；
- 当配置中启用 AI 时，可以通过本模块接入不同模型做信号过滤/增强。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import asyncio


try:
    from config import AIConfig, AppConfig
except ImportError:
    from .config import AIConfig, AppConfig

@dataclass
class AIInput:
    """
    AI 输入载体，可以是文本、结构化信号等。

    当前最简单设计：
    - text: 文本内容（如推文、新闻等）
    - meta: 任意附加信息（如 symbol、side 候选等）
    """

    text: str
    meta: Dict[str, Any]


@dataclass
class AIResult:
    """
    AI 输出载体，用于辅助交易决策。

    字段示例：
    - score: 置信度或强度（0~1）
    - label: 分类结果（如 "bullish"/"bearish"/"neutral"）
    - meta: 任意额外信息（如模型名称、原始输出等）
    """

    score: float
    label: str
    meta: Dict[str, Any]


class BaseAIModel(ABC):
    """
    AI 模型抽象接口。
    """

    name: str

    def __init__(self, name: str) -> None:
        self.name = name

    @abstractmethod
    async def analyze(self, ai_input: AIInput) -> AIResult:
        """
        对输入进行分析，返回 AIResult。
        """
        raise NotImplementedError


class DummyAIModel(BaseAIModel):
    """
    占位模型，用于在未接真实模型时跑通流程。

    简单策略：
    - 若文本长度 > 0，则 score=0.5，label="neutral"
    """

    async def analyze(self, ai_input: AIInput) -> AIResult:
        text = ai_input.text.strip()
        score = 0.5 if text else 0.0
        return AIResult(
            score=score,
            label="neutral",
            meta={"model": self.name},
        )


class AIModelRouter:
    """
    AI 模型路由器：并行调用多个模型，选择最快且结果合法的一个。

    当前实现：
    - 通过 asyncio.wait, FIRST_COMPLETED 获取最先返回的结果；
    - 简单认为任意非异常返回都合法；
    - 若所有模型失败或超时，则抛出 RuntimeError。
    """

    def __init__(self, config: AppConfig) -> None:
        self.app_config = config           # 完整配置
        self.config = config.ai            # 向后兼容
        self.models: List[BaseAIModel] = []

        if self.config.enabled:
            # 当前仅挂一个 Dummy 模型，后续可根据 config.models 动态创建真实模型
            self.models.append(DummyAIModel(name="dummy"))

    async def analyze(self, ai_input: AIInput) -> Optional[AIResult]:
        """
        使用路由器对输入进行分析。

        返回：
        - AIResult：来自最快成功的模型；
        - None：若未启用 AI 或无可用模型。
        """
        if not self.config.enabled or not self.models:
            return None

        timeout = self.config.router_timeout_sec

        async def _call_model(m: BaseAIModel) -> AIResult:
            return await m.analyze(ai_input)

        tasks = [asyncio.create_task(_call_model(m)) for m in self.models]
        done, pending = await asyncio.wait(
            tasks, timeout=timeout, return_when=asyncio.FIRST_COMPLETED
        )

        # 取消仍在运行的任务
        for p in pending:
            p.cancel()

        for d in done:
            if d.cancelled():
                continue
            exc = d.exception()
            if exc is None:
                return d.result()

        raise RuntimeError("AIModelRouter: all models failed or timed out")