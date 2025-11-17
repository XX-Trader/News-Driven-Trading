"""
trading_bot.twitter_source

一个极简的 Twitter 信号源实现，用于开发 / 测试阶段。
这里我们不调用真实 Twitter 接口，也不依赖你之前的大脚本，
而是直接在内存中写几条“假推文”，用来测试 trading_bot 的整体流程。

后续如果要接入真实 Twitter API，只需要改这里的实现，
保持 fetch_latest_tweets 的函数签名不变即可。
"""

from __future__ import annotations  # 允许在类型注解里引用后面才定义的类型（前向引用）

from typing import Any, Dict, List  # 导入常用类型别名：任意类型、字典、列表


# 注意：
# 这里刻意不引入任何网络库（如 requests、aiohttp），
# 只做开发阶段的“内存假数据”实现，避免增加不必要依赖和错误面。


async def fetch_latest_tweets() -> List[Dict[str, Any]]:
    """
    提供给 trading_bot.app_runner 使用的异步接口。

    设计约定：
    - 函数是 async 的（协程），方便之后切换成真正的网络请求；
    - 返回一个列表 List[Dict[str, Any]]，列表里的每一条字典代表一条 tweet；
    - 每条 tweet 至少包含以下字段（满足 app_runner.TwitterCrawlerSignalSource 的需求）：
        - id: 推文 ID，字符串形式（可以是任意唯一标识）；
        - text: 推文内容（英文 / 中文都可以）；
        - user_name: 用户名（不带 @ 符号）。

    当前实现：
    - 直接返回两条写死的假推文；
    - 第一条偏多头（long）；
    - 第二条偏空头（short）；
    方便我们测试 app_runner 里简单的关键字判断逻辑（long/short -> BUY/SELL）。
    """

    # 返回一个包含两个元素的列表，每个元素是一个字典，代表一条 tweet
    return [
        {
            "id": "test-1",  # 第一条假推文的 ID，随便取一个容易辨认的字符串
            # 推文文本内容，包含 "long" 和 "BTC" 等关键字，用于测试做多逻辑
            "text": "Bitcoin looks strong here, I am going long BTC.",
            "user_name": "cz_binance",  # 推文作者用户名，模拟来自 cz_binance 账号
        },
        {
            "id": "test-2",  # 第二条假推文的 ID
            # 推文文本内容，包含 "short" 和 "ETH" 等关键字，用于测试做空逻辑
            "text": "I think we might see some correction on ETH, maybe time to short a bit.",
            "user_name": "realDonaldTrump",  # 推文作者用户名，模拟来自 realDonaldTrump 账号
        },
    ]