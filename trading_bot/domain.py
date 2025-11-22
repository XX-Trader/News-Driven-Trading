"""
trading_bot.domain

领域模型与基础计算逻辑：
- TradeSignal：统一的信号输入结构
- StrategyConfig：单笔交易的策略参数（止损、分批止盈、仓位等）
- Order / Position：订单与持仓的抽象
- ExitDecision：出场决策（给 RiskManager 和 ExitStrategy 使用）
- 计算下单数量的辅助函数
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

try:
    from config import RiskConfig, ExchangeConfig
except ImportError:
    from .config import RiskConfig, ExchangeConfig


# --------------------
# 信号与策略配置
# --------------------


@dataclass
class TradeSignal:
    """
    统一的交易信号结构，由各个信号源（推特、新闻等）输出。

    字段说明：
    - symbol: 交易对，例如 BTCUSDT
    - side: BUY / SELL 或 LONG / SHORT（这里只存字符串，由上层约定）
    - position_pct: 建议仓位百分比（0~1），None 表示使用全局默认
    - stop_loss_pct: 建议止损百分比（0~1），None 表示使用全局默认
    - take_profit_scheme: 建议分批止盈方案，格式如：
        [{"take_profit": 0.02, "size_pct": 0.5}, {"take_profit": 0.05, "size_pct": 0.5}]
      None 表示使用全局默认
    - source_id: 信号来源标识（策略名、数据源名等）
    - meta: 任意附加信息（推特链接、原文、AI 评分等）
    """

    symbol: str
    side: str
    position_pct: Optional[float] = None
    stop_loss_pct: Optional[float] = None
    take_profit_scheme: Optional[List[Dict[str, float]]] = None
    source_id: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StrategyConfig:
    """
    某一笔交易实际生效的策略参数。

    由全局 RiskConfig 与 TradeSignal 合并而来：
    - position_pct: 实际使用的仓位百分比
    - stop_loss_pct: 实际使用的止损百分比
    - take_profit_scheme: 实际使用的分批止盈配置
    """

    position_pct: float
    stop_loss_pct: float
    take_profit_scheme: List[Dict[str, float]]


def merge_strategy_config(
    risk_conf: RiskConfig,
    signal: TradeSignal,
) -> StrategyConfig:
    """
    将全局 RiskConfig 与信号上的覆盖参数合并，得到具体一笔交易的策略配置。
    """
    position_pct = (
        signal.position_pct
        if signal.position_pct is not None
        else risk_conf.default_position_pct
    )
    stop_loss_pct = (
        signal.stop_loss_pct
        if signal.stop_loss_pct is not None
        else risk_conf.default_stop_loss_pct
    )
    take_profit_scheme = (
        signal.take_profit_scheme
        if signal.take_profit_scheme is not None
        else list(risk_conf.default_take_profit_scheme)
    )

    return StrategyConfig(
        position_pct=position_pct,
        stop_loss_pct=stop_loss_pct,
        take_profit_scheme=take_profit_scheme,
    )


# --------------------
# 订单与持仓
# --------------------


@dataclass
class Order:
    """
    订单抽象（简化版），主要用于追踪下单结果。

    对接交易所返回时，可以填充额外字段（比如实际成交量、成交价格等）。
    """

    order_id: Optional[str]
    symbol: str
    side: str
    quantity: float
    status: str = "NEW"
    avg_price: Optional[float] = None
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Position:
    """
    持仓抽象，一笔信号驱动的交易对应一个 Position。

    字段说明：
    - symbol / side: 与下单方向一致
    - entry_price: 开仓均价
    - quantity: 当前持仓数量
    - remaining_qty: 尚未平掉的数量（初始等于 quantity）
    - strategy: 本持仓使用的策略参数（止损、分批止盈等）
    - realized_pnl: 已实现盈亏
    - extra: 预留扩展字段（例如关联的订单列表等）
    """

    symbol: str
    side: str
    entry_price: float
    quantity: float
    strategy: StrategyConfig

    remaining_qty: float = 0.0
    realized_pnl: float = 0.0
    extra: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.remaining_qty <= 0:
            self.remaining_qty = self.quantity


# --------------------
# 出场决策（给 ExitStrategy / RiskManager 使用）
# --------------------


@dataclass
class ExitDecision:
    """
    出场决策结果，由 ExitStrategy 生成，RiskManager 执行。

    - action:
        - "close_all": 平掉全部 remaining_qty
        - "close_partial": 部分平仓
        - "do_nothing": 不操作
    - size_pct: 对 remaining_qty 的平仓比例（仅在 close_partial 时有效）
    - reason: 文本原因（方便日志和后续分析）
    """

    action: str
    size_pct: float = 0.0
    reason: str = ""


# --------------------
# 数量计算辅助函数
# --------------------


def calculate_order_quantity_from_balance(
    balance: float,
    price: float,
    strategy: StrategyConfig,
    exchange_conf: ExchangeConfig,
    min_qty: float = 0.0,
    step_size: float = 0.0,
) -> float:
    """
    根据余额、价格和策略计算下单数量。

    计算过程：
    1. 使用 balance * position_pct 得到本次交易使用的资金量（以 quote_asset 计价，例如 USDT）。
    2. 用 资金量 / 价格 ≈ 数量。
    3. 按交易所的 step_size、min_qty 进行向下取整处理。

    参数：
    - balance: 指定计价资产的可用余额（例如 USDT 可用余额）
    - price: 当前市价
    - strategy: 已合并的 StrategyConfig（包含 position_pct）
    - exchange_conf: 交易所配置（目前主要用于 future 扩展，此处不直接使用）
    - min_qty: 交易所要求的最小下单数量（可从交易规则获取）
    - step_size: 交易所要求的最小变动单位（步长）

    返回：
    - 调整后的数量，若不足最小数量则返回 0.0。
    """
    if price <= 0 or balance <= 0 or strategy.position_pct <= 0:
        return 0.0

    # 1. 资金量（quote）
    quote_to_use = balance * strategy.position_pct

    # 2. 理论数量
    raw_qty = quote_to_use / price

    # 3. 按 step_size 向下取整（修复：当 qty < step_size 时返回0的错误）
    qty = raw_qty
    if step_size > 0:
        # 使用 math.floor 确保正确处理小数
        steps = math.floor(qty / step_size)
        qty = steps * step_size

    # 4. 检查最小下单数量
    if min_qty > 0 and qty < min_qty:
        # 如果计算后的数量小于最小下单量，返回0（不下单）
        return 0.0

    return float(qty)