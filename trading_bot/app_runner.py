"""
trading_bot.app_runner

主应用编排逻辑（MVP 版，可运行）：

- 定时从“推特抢跑”侧的爬虫接口获取最新消息（20 条左右）；
- 将原始消息保存为 JSON 文件；
- 用最简单的“已处理 id 列表”避免重复处理（本地 JSON 文件存储 processed_ids）；
- 对未处理的消息可以接 AI 层（当前用 Dummy，它只是打个标签，不做强过滤）；
- 每条未处理消息都转成 TradeSignal，并立刻实盘/模拟下单；
- RiskManager 目前暂时不用（简化为单次下单），后续可一行行接入。

为兼容当前已实现的 domain.py/config.py/risk_exit.py：
- 不再依赖 StrategyConfig.symbol/side/to_strategy_config 等不存在的字段/方法；
- 不依赖 ExchangeConfig.quote_asset/min_qty/step_size 等未定义字段；
- 使用 InMemorySignalSource 接口风格，保证 .stream() 是 async generator（可 async for）。

注意：
- 这里不会直接调用真实的推特 API，而是预期你在
  `推特抢跑/twitter_crawler_functional_min.py` 中提供一个函数接口，例如：
      async def fetch_latest_tweets() -> list[dict]
  本模块通过 import 调用即可。
"""

from __future__ import annotations

import asyncio
import importlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional

from .ai_base import AIInput, AIModelRouter
from .config import AppConfig, load_config
from .domain import TradeSignal
from .exchange_binance_async import BinanceAsyncClient
from .signals import SignalSource, InMemorySignalSource


# ----------------------------
# 类型别名与简单协议定义
# ----------------------------

RawTweet = Dict[str, Any]

# 期望：async def fetch_latest_tweets() -> list[RawTweet]
FetchLatestTweetsFunc = Callable[[], Awaitable[List[RawTweet]]]


@dataclass
class TweetSignalSourceConfig:
    """
    推特信号源相关路径/配置。

    - crawled_json_dir: 爬虫原始 JSON 的输出目录（可选，如果你希望本模块来保存）
    - processed_id_path: 已处理 tweet_id 列表的存储文件（JSON 简单格式）
    - poll_interval_sec: 定时轮询间隔（秒）
    """

    crawled_json_dir: Path
    processed_id_path: Path
    poll_interval_sec: int = 5


class ProcessedIdStore:
    """
    最简单的“已处理 ID 存储”，用本地 JSON 文件记录。

    文件格式：
    {
        "processed_ids": ["1234567890", "1234567891", ...]
    }
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.ids: set[str] = set()
        self._loaded = False

    def load(self) -> None:
        if self._loaded:
            return
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                ids = data.get("processed_ids", [])
                if isinstance(ids, list):
                    self.ids = set(str(i) for i in ids)
            except Exception:
                self.ids = set()
        self._loaded = True

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {"processed_ids": sorted(self.ids)}
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def has(self, tweet_id: str) -> bool:
        self.load()
        return tweet_id in self.ids

    def add_many(self, tweet_ids: List[str]) -> None:
        self.load()
        for tid in tweet_ids:
            self.ids.add(str(tid))
        self.save()


# ----------------------------
# 推特信号源：基于爬虫接口 + 本地 JSON
# ----------------------------

class TwitterCrawlerSignalSource(SignalSource):
    """
    基于 twitter_crawler_functional_min.py 的信号源：

    - 定期调用 fetch_latest_tweets() 获取最近 N 条消息；
    - 把原始结果保存成 JSON 文件（latest_batch.json）；
    - 使用 ProcessedIdStore 过滤已经处理过的 tweet_id；
    - 对未处理消息调用 AIModelRouter（当前 Dummy）做文本分析；
    - 将“未处理消息”全部转换为 TradeSignal 输出（你后续可用 AI 分数做过滤）。
    """

    def __init__(
        self,
        fetch_func: FetchLatestTweetsFunc,
        tweet_conf: TweetSignalSourceConfig,
        ai_router: AIModelRouter,
    ) -> None:
        self.fetch_func = fetch_func
        self.tweet_conf = tweet_conf
        self.ai_router = ai_router
        self.processed_store = ProcessedIdStore(tweet_conf.processed_id_path)

    async def stream(self):
        """
        异步信号流：while True 循环 + 定时 sleep。
        """
        while True:
            try:
                raw_tweets = await self.fetch_func()
            except Exception as e:
                print(f"[TwitterCrawlerSignalSource] fetch_latest_tweets error: {e}")
                await asyncio.sleep(self.tweet_conf.poll_interval_sec)
                continue

            try:
                self._save_raw_batch(raw_tweets)
            except Exception as e:
                print(f"[TwitterCrawlerSignalSource] save raw batch error: {e}")

            new_ids: List[str] = []
            for tweet in raw_tweets:
                tweet_id = str(tweet.get("id") or tweet.get("tweet_id") or "")
                if not tweet_id:
                    continue
                if self.processed_store.has(tweet_id):
                    continue  # 已处理

                text = str(tweet.get("text") or "")
                user_name = str(tweet.get("user_name") or tweet.get("screen_name") or "")

                ai_input = AIInput(
                    text=text,
                    meta={
                        "tweet_id": tweet_id,
                        "user_name": user_name,
                    },
                )
                ai_result = None
                try:
                    ai_result = await self.ai_router.analyze(ai_input)
                except Exception as e:
                    print(f"[TwitterCrawlerSignalSource] AI analyze error: {e}")

                signal = self._to_trade_signal(tweet, ai_result)
                if signal is not None:
                    new_ids.append(tweet_id)
                    yield signal

            if new_ids:
                self.processed_store.add_many(new_ids)

            await asyncio.sleep(self.tweet_conf.poll_interval_sec)

    def _save_raw_batch(self, tweets: List[RawTweet]) -> None:
        """
        将当前批次的原始推文写入 JSON 文件（latest_batch.json）。
        """
        self.tweet_conf.crawled_json_dir.mkdir(parents=True, exist_ok=True)
        path = self.tweet_conf.crawled_json_dir / "latest_batch.json"
        path.write_text(json.dumps(tweets, ensure_ascii=False, indent=2), encoding="utf-8")

    def _to_trade_signal(self, tweet: RawTweet, ai_result: Optional[Any]) -> Optional[TradeSignal]:
        """
        将推文 + AI 结果转换为 TradeSignal。

        当前简化逻辑：
        - 文本为空则忽略；
        - side 通过简单关键词判断（long/多 → BUY；short/空 → SELL），否则默认 BUY；
        - symbol 从 tweet.symbol 或默认 "BTCUSDT"；
        - 止损/分批止盈/仓位大小全部走全局 RiskConfig（由下单侧合并）。
        """
        text = str(tweet.get("text") or "")
        if not text.strip():
            return None

        lowered = text.lower()
        side: str
        if ("short" in lowered) or ("做空" in text) or ("空单" in text):
            side = "SELL"
        elif ("long" in lowered) or ("做多" in text) or ("多单" in text):
            side = "BUY"
        else:
            side = "BUY"

        symbol = str(tweet.get("symbol") or "BTCUSDT")

        return TradeSignal(
            symbol=symbol,
            side=side,
            position_pct=None,
            stop_loss_pct=None,
            take_profit_scheme=None,
            source_id=str(tweet.get("user_name") or tweet.get("screen_name") or ""),
            meta={
                "tweet_id": str(tweet.get("id") or tweet.get("tweet_id") or ""),
                "raw_text": text,
                "ai_result": (
                    {"score": ai_result.score, "label": ai_result.label, "meta": ai_result.meta}
                    if ai_result is not None
                    else None
                ),
            },
        )


# ----------------------------
# 主应用：组装各模块
# ----------------------------

@dataclass
class TradingAppContext:
    config: AppConfig
    ai_router: AIModelRouter
    exchange_client: BinanceAsyncClient
    signal_source: SignalSource
    tasks: List[asyncio.Task]


async def _load_twitter_fetch_func() -> FetchLatestTweetsFunc:
    """
    从 '推特抢跑/twitter_crawler_functional_min.py' 导入获取最近消息的函数。

    你需要在该文件中提供一个协程函数，例如：
        async def fetch_latest_tweets() -> list[dict]:
            ...

    若不存在，则抛异常。
    """
    module = importlib.import_module("推特抢跑.twitter_crawler_functional_min".replace("/", "."))
    func = getattr(module, "fetch_latest_tweets", None)
    if func is None:
        raise RuntimeError(
            "在 '推特抢跑/twitter_crawler_functional_min.py' 中找不到 fetch_latest_tweets 函数，"
            "请实现：async def fetch_latest_tweets() -> list[dict]"
        )
    return func


async def build_trading_app_context() -> TradingAppContext:
    """
    初始化整个交易应用的上下文：
    - 加载配置
    - 创建 AIModelRouter
    - 创建 BinanceAsyncClient
    - 创建 TwitterCrawlerSignalSource（如果导入失败，则使用 InMemorySignalSource）
    """
    config = load_config()
    ai_router = AIModelRouter(config.ai)
    exchange_client = BinanceAsyncClient(config=config)

    base_dir = Path(__file__).resolve().parent.parent
    tweet_conf = TweetSignalSourceConfig(
        crawled_json_dir=base_dir / "推特抢跑" / "twitter_media",
        processed_id_path=base_dir / "推特抢跑" / "twitter_media" / "processed_ids.json",
        poll_interval_sec=5,
    )

    try:
        fetch_func = await _load_twitter_fetch_func()
        signal_source: SignalSource = TwitterCrawlerSignalSource(
            fetch_func=fetch_func,
            tweet_conf=tweet_conf,
            ai_router=ai_router,
        )
    except Exception as e:
        print(f"[build_trading_app_context] fallback to InMemorySignalSource because: {e}")
        signal_source = InMemorySignalSource()

    return TradingAppContext(
        config=config,
        ai_router=ai_router,
        exchange_client=exchange_client,
        signal_source=signal_source,
        tasks=[],
    )


async def _consume_signals_and_trade(app: TradingAppContext) -> None:
    """
    从 SignalSource 消费 TradeSignal，计算下单数量，并提交给交易所。

    风控部分当前版本先不接 RiskManager，只做“一进一出”的最小可运行链路：
    - 每个信号 → 计算数量 → 市价单 BUY/SELL。
    """
    from .domain import calculate_order_quantity_from_balance, StrategyConfig, merge_strategy_config

    async for signal in app.signal_source.stream():
        try:
            # 把全局 RiskConfig 和 signal 合并成 StrategyConfig（只用仓位/止损/止盈配置）
            strategy_conf: StrategyConfig = merge_strategy_config(app.config.risk, signal)

            # 假定 quote 资产为 USDT（你可在 config 里增加字段再来改这里）
            quote_asset = "USDT"
            balance = await app.exchange_client.get_balance(asset=quote_asset)
            price = await app.exchange_client.get_latest_price(symbol=signal.symbol)

            # 这里用简单的默认 min_qty/step_size，你可以写到 config.ExchangeConfig 里
            min_qty = 0.001
            step_size = 0.0001

            quantity = calculate_order_quantity_from_balance(
                balance=balance,
                price=price,
                strategy=strategy_conf,
                exchange_conf=app.config.exchange,
                min_qty=min_qty,
                step_size=step_size,
            )
            if quantity <= 0:
                print(
                    f"[trade] calculated quantity <= 0 for signal {signal}, "
                    f"balance={balance}, price={price}"
                )
                continue

            print(
                f"[trade] placing order: symbol={signal.symbol}, side={signal.side}, "
                f"qty={quantity}, price~{price}"
            )
            order_resp = await app.exchange_client.place_market_order(
                symbol=signal.symbol,
                side=signal.side,
                quantity=quantity,
            )
            print(f"[trade] order_resp={order_resp}")

        except Exception as e:
            print(f"[trade] error while handling signal {signal}: {e}")


async def start_trading_app() -> None:
    """
    启动整个交易应用：

    - 构建上下文；
    - 启动“信号消费 + 下单”的主任务；
    - 直到被 Ctrl+C 中断。
    """
    app = await build_trading_app_context()
    main_task = asyncio.create_task(_consume_signals_and_trade(app))
    app.tasks.append(main_task)

    print("[trading_app] started. Press Ctrl+C to stop.")

    try:
        await asyncio.gather(*app.tasks)
    except asyncio.CancelledError:
        print("[trading_app] cancelled.")
    finally:
        # TODO: 关闭 aiohttp session 等资源
        pass


async def stop_trading_app(app: TradingAppContext) -> None:
    """
    预留的停止逻辑：取消所有任务，清理资源。
    """
    for t in app.tasks:
        t.cancel()
    # TODO: 关闭 aiohttp 会话、持久化必要状态等