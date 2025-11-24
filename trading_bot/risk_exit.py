"""
trading_bot.risk_exit

负责：
- 出场策略接口 ExitStrategy
- 默认 BasicExitStrategy：根据止损 + 分批止盈做出场决策
- RiskManager 骨架：持仓价格监控与执行出场

这里先搭骨架和核心数据流，具体行情获取和真实平仓由后续模块对接：
- 行情：通过传入的 get_price 协程函数获取最新价格
- 平仓：通过传入的 close_position 协程函数执行实际平仓
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable, Awaitable


try:
    from config import RiskConfig
except ImportError:
    from .config import RiskConfig

try:
    from domain import Position, StrategyConfig, ExitDecision
except ImportError:
    from .domain import Position, StrategyConfig, ExitDecision

# PositionManager removed - positions now stored in memory only



# --------------------
# ExitStrategy 接口与默认实现
# --------------------


class ExitStrategy:
    """
    出场策略接口类 - 定义了所有出场策略必须遵循的规范
    
    功能说明：
    - 这是一个抽象基类，定义了出场策略的标准接口
    - 具体实现类（如BasicExitStrategy）必须实现on_price方法
    - 负责根据实时价格、持仓信息和风控参数生成出场决策
    
    设计思想：
    - 策略模式：将不同的出场逻辑封装在独立的策略类中
    - 解耦：RiskManager只依赖接口，不依赖具体实现
    - 可扩展：可以轻松添加新的出场策略（如追踪止损、技术指标出场等）
    
    参数：
    - position: Position对象，包含持仓的所有信息（币种、方向、数量、成本价等）
    - risk_conf: RiskConfig对象，包含全局风控参数（止损比例、止盈方案等）
    """

    def __init__(self, position: Position, risk_conf: RiskConfig) -> None:
        # 保存持仓实例，后续计算盈亏和出场决策需要用到
        self.position = position
        # 保存风控配置，包含止损止盈等参数
        self.risk_conf = risk_conf

    async def on_price(
        self,
        latest_price: float,
    ) -> Optional[ExitDecision]:
        """
        核心方法：根据最新价格判断是否需要出场
        
        执行逻辑：
        1. 接收最新市场价格
        2. 计算当前持仓的浮动盈亏
        3. 根据风控规则判断是否需要出场
        4. 返回出场决策或None（不出场）
        
        参数：
        - latest_price: 当前最新价格（从交易所获取的实时价格）
        
        返回值：
        - ExitDecision对象：表示需要执行出场操作（全部平仓或部分平仓）
        - None：表示当前不需要任何操作，继续持有
        
        注意：
        - 这是一个抽象方法，子类必须实现具体的出场逻辑
        - 方法必须是异步的，因为可能涉及IO操作（如查询历史数据、计算指标等）
        """
        raise NotImplementedError


@dataclass
class _TakeProfitLevelState:
    level: Dict[str, float]
    triggered: bool = False


class BasicExitStrategy(ExitStrategy):
    """
    默认出场策略：
    - 止损：浮动亏损超过 stop_loss_pct 时，全部平仓
    - 分批止盈：到达每个 take_profit_level 时，按 size_pct 平部分仓位
    """

    def __init__(self, position: Position, risk_conf: RiskConfig) -> None:
        super().__init__(position, risk_conf)

        strat = position.strategy
        # 将分批止盈配置包装为状态对象，便于标记是否已触发
        self._tp_levels: List[_TakeProfitLevelState] = [
            _TakeProfitLevelState(level=tp) for tp in strat.take_profit_scheme
        ]

    async def on_price(
        self,
        latest_price: float,
    ) -> Optional[ExitDecision]:
        if latest_price <= 0 or self.position.remaining_qty <= 0:
            return None

        entry = self.position.entry_price
        side = self.position.side.upper()

        # 根据方向计算收益率（多头：price/entry-1，空头：entry/price-1）
        if side in ("BUY", "LONG"):
            pnl_ratio = (latest_price / entry) - 1.0
        else:
            pnl_ratio = (entry / latest_price) - 1.0

        # 1. 止损检查
        if pnl_ratio <= -self.position.strategy.stop_loss_pct:
            return ExitDecision(
                action="close_all",
                size_pct=1.0,
                reason=f"stop_loss hit: pnl_ratio={pnl_ratio:.4f}",
            )

        # 2. 分批止盈检查（从低到高扫描，第一个满足的触发）
        for level_state in self._tp_levels:
            if level_state.triggered:
                continue
            tp = level_state.level.get("take_profit", 0.0)
            size_pct = level_state.level.get("size_pct", 0.0)
            if tp <= 0 or size_pct <= 0:
                continue

            if pnl_ratio >= tp:
                level_state.triggered = True
                return ExitDecision(
                    action="close_partial",
                    size_pct=size_pct,
                    reason=f"take_profit hit: tp={tp:.4f}, pnl_ratio={pnl_ratio:.4f}",
                )

        return None


# --------------------
# RiskManager 骨架
# --------------------


# 行情获取函数类型：传入 symbol，返回最新价格
PriceFetcher = Callable[[str], Awaitable[float]]
# 平仓执行函数类型：传入 position + size_pct，执行平仓并返回任意结果/信息
CloseExecutor = Callable[[Position, float, str], Awaitable[Any]]


@dataclass
class PositionMonitor:
    """
    用于追踪单个 Position 的监控状态。
    """

    position: Position
    strategy: StrategyConfig
    exit_strategy: ExitStrategy
    active: bool = True
    extra: Dict[str, Any] = field(default_factory=dict)


class RiskManager:
    """
    风控管理器：
    - 为每个新建 Position 创建一个监控任务（协程）；
    - 周期性获取最新价格，调用 ExitStrategy -> ExitDecision；
    - 根据决策调用 close_executor 执行真实平仓；
    - 集成 PositionManager 实现持仓持久化。

    注意：
    - 这里不负责 actual 下单，只负责决策 + 调用传入的 close_executor。
    - 调度细节（创建任务、关闭任务）由上层 app_runner 统筹。
    - 所有持仓变更都会通过 PositionManager 持久化到磁盘。
    """

    def __init__(
        self,
        risk_conf: RiskConfig,
        price_fetcher: PriceFetcher,
        close_executor: CloseExecutor,
        poll_interval_sec: float = 1.0,
    ) -> None:
        self.risk_conf = risk_conf
        self.price_fetcher = price_fetcher
        self.close_executor = close_executor
        self.poll_interval_sec = poll_interval_sec
        
        # position_id -> PositionMonitor (positions stored in memory only)
        self._monitors: Dict[str, PositionMonitor] = {}

    def _load_active_positions(self) -> None:
        """
        加载活跃持仓并创建监控器（目前为空实现，持仓存储在内存中）。
        在 RiskManager 初始化时自动调用。
        """
        # NOTE: Positions are stored in memory only. Persistence removed as per MVP approach.
        pass

    def _make_position_id(self, position: Position) -> str:
        # 简单实现：symbol + side + entry_price + quantity 组合
        return f"{position.symbol}:{position.side}:{position.entry_price}:{position.quantity}"

    def add_position(self, position: Position) -> str:
        """
        为新建 Position 注册监控并持久化，返回内部的 position_id。
        """
        pid = self._make_position_id(position)
        if pid in self._monitors:
            return pid

        # 当前仅支持 BasicExitStrategy，后续可根据 risk_conf.exit_strategy_type 选择不同策略类
        exit_strategy: ExitStrategy = BasicExitStrategy(position, self.risk_conf)
        monitor = PositionMonitor(
            position=position,
            strategy=position.strategy,
            exit_strategy=exit_strategy,
        )
        self._monitors[pid] = monitor
        
        # NOTE: Position persistence removed. Position stored in memory only.
        
        return pid

    def remove_position(self, position_id: str) -> None:
        """
        取消对某一持仓的监控并从持久化中移除。
        """
        self._monitors.pop(position_id, None)
        # NOTE: Position persistence removed. Position removed from memory only.

    async def monitor_loop(self, position_id: str) -> None:
        """
        针对单一 position 的监控循环。

        上层通常会为每个 position_id 创建一个任务来跑这个 loop。
        """
        import asyncio

        monitor = self._monitors.get(position_id)
        if monitor is None:
            return

        pos = monitor.position

        while monitor.active and pos.remaining_qty > 0:
            try:
                price = await self.price_fetcher(pos.symbol)
            except Exception as e:  # noqa: BLE001
                # 行情获取失败，记录后继续下一轮
                # 具体日志由上层负责，这里不打印
                await asyncio.sleep(self.poll_interval_sec)
                continue

            decision = await monitor.exit_strategy.on_price(price)
            if decision is not None and decision.action in {"close_all", "close_partial"}:
                # 计算本次平仓比例
                size_pct = 1.0 if decision.action == "close_all" else decision.size_pct
                if size_pct > 0:
                    # 执行真实平仓（由外部注入）
                    await self.close_executor(pos, size_pct, decision.reason)

                    # 更新 remaining_qty（简单按比例减少）
                    qty_to_close = pos.remaining_qty * min(max(size_pct, 0.0), 1.0)
                    pos.remaining_qty -= qty_to_close
                    
                    # NOTE: Position persistence removed. Position updated in memory only.
                    
                    if pos.remaining_qty <= 0:
                        pos.remaining_qty = 0
                        monitor.active = False
                        # 完全平仓后从内存中移除
                        # NOTE: Position persistence removed. Position removed from memory only.
                        break

            await asyncio.sleep(self.poll_interval_sec)