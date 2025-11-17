"""
trading_bot 包：信号驱动实盘交易系统

当前版本：v0.1.0（仅骨架）
- 配置：见 trading_bot.config
- 网络与代理：见 trading_bot.network
- 交易所适配：见 trading_bot.exchange_binance_async
- 领域模型：见 trading_bot.domain
- 风控与出场策略：见 trading_bot.risk_exit
- 信号接入：见 trading_bot.signals
- 应用编排：见 trading_bot.app_runner
"""

# 对外暴露的“官方入口”：
# - 你在任何地方（脚本 / Notebook / VSCode 单文件）都可以：
#       from trading_bot import start_trading_app
# - 这样既不会破坏内部模块之间的导入关系，又方便你快速启动整个系统。
from .app_runner import start_trading_app

__all__ = ["start_trading_app"]