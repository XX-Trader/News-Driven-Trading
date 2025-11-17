import asyncio
import trading_bot

# 这里作为项目根目录的启动入口，方便你直接使用：
#   python main.py
# 来运行整个交易系统。
#
# 内部依然复用 trading_bot.main 模块中的 main()，保持包结构清晰。


async def _run_trading_bot() -> None:
    """
    根目录入口的异步封装函数。

    从 trading_bot.main 中导入 main() 并调用，避免在导入阶段就执行逻辑，
    也避免循环导入问题。
    """
    # 延迟导入，确保当前目录已在 sys.path 中，并且 trading_bot 被当成包加载
    from trading_bot.main import main as trading_bot_main  # type: ignore

    await trading_bot_main()


def main() -> None:
    """
    根目录同步入口函数：

    - 打印一行日志，表明从 root main 启动；
    - 直接调用 trading_bot.main.main()，
      由包内部自己负责 asyncio.run(start_trading_app())，
      避免在这里再嵌套一层事件循环。
    """
    print("[root main] starting trading bot via trading_bot.main ...")

    # 延迟导入，确保当前目录已在 sys.path 中，并且 trading_bot 被当成包加载
    from trading_bot.main import main as trading_bot_main  # type: ignore

    # 注意：这里不要再 asyncio.run(...)，否则会嵌套事件循环
    trading_bot_main()


if __name__ == "__main__":
    main()