"""
trading_bot.signals

信号源抽象与占位实现。

设计目标：
- 提供统一的异步信号接口，返回 domain.TradeSignal；
- 目前先给出一个简单的占位实现（例如从内存队列 / 手动注入信号）；
- 后续可以在这里对接推特抢跑模块，把推特信号转换为 TradeSignal。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator, Optional, List

from .domain import TradeSignal


class SignalSource(ABC):
    """
    信号源抽象接口。

    约定：
    - 实现类通过异步迭代器不断产出 TradeSignal；
    - 外层可以用 `async for signal in source.stream(): ...` 进行消费。
    """

    @abstractmethod
    async def stream(self) -> AsyncIterator[TradeSignal]:
        """
        异步流式输出 TradeSignal。
        """
        raise NotImplementedError


@dataclass
class InMemorySignalSource(SignalSource):
    """
    简单的内存信号源，占位用：
    - 启动前通过 add_signal 添加若干信号；
    - stream() 会依次产出这些信号，然后结束。

    未来可以删除或保留用于调试。
    """

    _signals: List[TradeSignal]

    def __init__(self) -> None:
        self._signals = []

    def add_signal(self, signal: TradeSignal) -> None:
        self._signals.append(signal)

    async def stream(self) -> AsyncIterator[TradeSignal]:
        for s in self._signals:
            yield s


# TODO: 在后续版本中，这里可以添加 TwitterSignalSource，
# 从推特抢跑模块输出的结果中解析并构造 TradeSignal。