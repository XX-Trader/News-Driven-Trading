"""
trading_bot.config

集中管理交易系统的配置，避免在业务逻辑中散落硬编码。

当前仅提供简单配置骨架，后续可以根据需要扩展为从环境变量 / 配置文件加载。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import os


# --------------------
# 数据类定义
# --------------------


@dataclass
class ProxyConfig:
    """网络代理相关配置"""

    google_check_enabled: bool = True
    force_proxy: bool = False
    use_proxy_by_default: bool = False
    proxy_url: str = "http://127.0.0.1:1080"
    google_test_url: str = "https://www.google.com"
    google_timeout_sec: float = 3.0


@dataclass
class ExchangeConfig:
    """交易所相关配置（当前以 Binance 为主）"""

    name: str = "binance"
    api_key_env: str = "BINANCE_API_KEY"
    api_secret_env: str = "BINANCE_API_SECRET"
    base_url: str = "https://api.binance.com"
    recv_window: int = 5000
    request_timeout_sec: float = 10.0
    use_testnet: bool = False  # 虽然当前目标是实盘，但仍保留 testnet 选项
    dry_run: bool = True  # 强烈建议开发/调试阶段保持 True，实盘时显式改为 False

    quote_asset_for_position: str = "USDT"  # 用于计算仓位的计价资产，比如 USDT


@dataclass
class RiskConfig:
    """风控相关全局配置"""

    default_stop_loss_pct: float = 0.01  # 默认止损 1%
    # 默认分批止盈方案：例如 +2% 平 50%，+5% 平剩余 50%
    default_take_profit_scheme: List[Dict[str, float]] = field(
        default_factory=lambda: [
            {"take_profit": 0.02, "size_pct": 0.5},
            {"take_profit": 0.05, "size_pct": 0.5},
        ]
    )
    default_position_pct: float = 0.02  # 默认单次开仓 2% 资金
    exit_strategy_type: str = "basic"  # 当前只有 basic，未来可扩展 demark / ai 等


@dataclass
class AIConfig:
    """AI 模型相关配置（目前先保留占位，后续接入具体模型）"""

    enabled: bool = False
    router_timeout_sec: float = 5.0
    models: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class AppConfig:
    """应用级整体配置"""

    proxy: ProxyConfig = field(default_factory=ProxyConfig)
    exchange: ExchangeConfig = field(default_factory=ExchangeConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    ai: AIConfig = field(default_factory=AIConfig)


# --------------------
# 加载配置入口
# --------------------


def load_env_var(name: str, default: Optional[str] = None) -> Optional[str]:
    """从环境变量中读取值，若不存在则返回 default。"""
    return os.environ.get(name, default)


def load_config() -> AppConfig:
    """
    构建并返回应用配置。

    当前实现为：
    - 绝大多数值使用 dataclass 默认值；
    - 关键敏感信息（如 API KEY）从环境变量中读取；
    - 若未来需要从文件加载，可在此函数中扩展。
    """
    app_config = AppConfig()

    # 从环境变量覆盖部分配置（如有）
    api_key_env_name = app_config.exchange.api_key_env
    api_secret_env_name = app_config.exchange.api_secret_env

    # 实际 key/secret 的具体值不存入 config 对象中，由使用方再次从环境变量读取。
    # 这里只是保留“变量名”，便于统一管理。
    _ = load_env_var(api_key_env_name)
    _ = load_env_var(api_secret_env_name)

    # DRY_RUN 也允许通过环境变量覆盖
    dry_run_env = load_env_var("TRADING_BOT_DRY_RUN")
    if dry_run_env is not None:
        app_config.exchange.dry_run = dry_run_env.lower() in {"1", "true", "yes", "on"}

    return app_config