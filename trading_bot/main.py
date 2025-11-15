"""
trading_bot.main

交易系统启动入口。

用法（在项目根目录执行）：
    python -m trading_bot.main

前提条件：
1. 已在 `推特抢跑/twitter_crawler_functional_min.py` 中实现：
       async def fetch_latest_tweets() -> list[dict]
2. 已准备好提示词文件：
       推特抢跑/提示词.txt
3. 已正确配置 Binance 相关参数（见 trading_bot.config.AppConfig / ExchangeConfig）。
"""

from __future__ import annotations

import asyncio
import signal
from typing import Optional

from .app_runner import start_trading_app


def _run_async(coro) -> None:
    """
    简单的 asyncio 入口封装，兼容 Windows / 非交互环境。
    """
    try:
        asyncio.run(coro)
    except KeyboardInterrupt:
        print("[main] KeyboardInterrupt, exiting...")


def main() -> None:
    """
    程序入口：
    - 注册 Ctrl+C 信号处理；
    - 启动异步交易应用；
    """
    print("[main] starting trading bot...")

    # 在 Windows 上 signal.SIGINT 处理并不总是必要，这里仅做兼容占位
    def handle_sigint(signum, frame):
        print("[main] received SIGINT, stopping soon...")

    try:
        signal.signal(signal.SIGINT, handle_sigint)
    except Exception:
        # 某些环境（如 Windows 部分 Python 实现）可能不支持 signal.signal
        pass

    _run_async(start_trading_app())


if __name__ == "__main__":
    main()