"""
trading_bot.signal_filter

信号过滤器：基于黑名单和置信度阈值过滤交易信号

核心功能：
- 黑名单过滤：检查币种代码是否在黑名单中
- 置信度过滤：检查AI返回的置信度是否达到最低阈值
- 过滤结果记录：将过滤结果（通过/拒绝及原因）记录在数据结构中

设计原则：
- 职责单一：只负责信号过滤，不耦合业务逻辑
- 可配置：通过 RiskConfig 获取过滤参数
- 详细记录：每次过滤都记录原因，便于后续分析
"""

from __future__ import annotations

from typing import Dict, Any, Optional

try:
    from config import RiskConfig
    from domain import TradeSignal
except ImportError:
    from .config import RiskConfig
    from .domain import TradeSignal


class SignalFilter:
    """信号过滤器"""
    
    def __init__(self, risk_config: RiskConfig) -> None:
        """
        初始化信号过滤器
        
        参数：
        - risk_config: 风控配置，包含 min_confidence 和 symbol_blacklist
        """
        self.risk_config = risk_config
    
    def extract_base_currency(self, symbol: str) -> str:
        """
        从交易对中提取基础币种代码
        
        示例：
        - "BTCUSDT" → "BTC"
        - "BNBUSDT" → "BNB"
        - "1000SHIBUSDT" → "1000SHIB"
        
        参数：
        - symbol: 交易对字符串
        
        返回：
        - 基础币种代码
        """
        # 移除末尾的 USDT（不区分大小写）
        if symbol.upper().endswith("USDT"):
            return symbol[:-4]
        return symbol
    
    def filter_signal(self, signal: TradeSignal, ai_confidence: Optional[float] = None) -> Dict[str, Any]:
        """
        过滤交易信号
        
        参数：
        - signal: 交易信号
        - ai_confidence: AI返回的置信度（0-100），如果为None则跳过置信度检查
        
        返回：
        - 过滤结果字典：
          {
            "passed": bool,  # 是否通过过滤
            "reason": str,   # 通过/拒绝原因
            "details": {     # 详细信息
              "symbol": str,
              "base_currency": str,
              "confidence": Optional[float],
              "in_blacklist": bool
            }
          }
        """
        result = {
            "passed": False,
            "reason": "",
            "details": {
                "symbol": signal.symbol,
                "base_currency": "",
                "confidence": ai_confidence,
                "in_blacklist": False
            }
        }
        
        # 提取基础币种代码
        base_currency = self.extract_base_currency(signal.symbol)
        result["details"]["base_currency"] = base_currency
        
        # 检查黑名单
        if base_currency.upper() in [b.upper() for b in self.risk_config.symbol_blacklist]:
            result["details"]["in_blacklist"] = True
            result["reason"] = f"拒绝：币种 {base_currency} 在黑名单中"
            return result
        
        # 检查置信度（仅在提供置信度时检查）
        if ai_confidence is not None:
            if ai_confidence < self.risk_config.min_confidence:
                result["reason"] = f"拒绝：置信度 {ai_confidence:.1f} < 最低阈值 {self.risk_config.min_confidence}"
                return result
        
        # 通过所有检查
        result["passed"] = True
        if ai_confidence is not None:
            result["reason"] = f"通过：置信度 {ai_confidence:.1f} >= {self.risk_config.min_confidence}"
        else:
            result["reason"] = "通过：无置信度要求"
        
        return result