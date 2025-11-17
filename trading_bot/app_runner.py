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
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, List, Optional

try:
    from ai_base import AIInput, AIModelRouter
    from config import AppConfig, load_config
    from domain import TradeSignal
    from exchange_binance_async import BinanceAsyncClient
    from signals import SignalSource, InMemorySignalSource
    from tweet_analyzer import call_ai_for_tweet, call_ai_for_tweet_async, detect_trade_symbol
    from twitter_source import mark_as_processed
except ImportError:
    from .ai_base import AIInput, AIModelRouter
    from .config import AppConfig, load_config
    from .domain import TradeSignal
    from .exchange_binance_async import BinanceAsyncClient
    from .signals import SignalSource, InMemorySignalSource
    from .tweet_analyzer import call_ai_for_tweet, call_ai_for_tweet_async, detect_trade_symbol
    from .twitter_source import mark_as_processed


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
    - poll_interval_sec: 定时轮询间隔（秒），默认 10 秒
    """

    crawled_json_dir: Path
    processed_id_path: Path
    poll_interval_sec: int = 10


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
        
        # 异步 AI 队列与缓存
        self.ai_queue: asyncio.Queue = asyncio.Queue(maxsize=0)  # 无限制队列
        self.ai_results_cache: Dict[str, Any] = {}  # {tweet_id: ai_result}
        self.tweet_status: Dict[str, Dict[str, Any]] = {}  # {tweet_id: {status, created_at, ...}}
        
        # 后台 worker 任务
        self.worker_tasks: List[asyncio.Task] = []
        self.cleanup_task: Optional[asyncio.Task] = None

    async def _ai_worker(self) -> None:
        """
        后台 AI worker：从队列取推文，调用异步 AI，存储结果。
        
        - 从 self.ai_queue 取推文
        - 调用 call_ai_for_tweet_async() 进行异步分析（30 秒超时）
        - 将结果存储到 self.ai_results_cache
        - 标记推文状态为 "done" 或 "timeout"
        """
        while True:
            try:
                # 从队列取推文数据
                tweet_data = await self.ai_queue.get()
                tweet = tweet_data.get("tweet")
                tweet_id = tweet_data.get("tweet_id")
                
                if not tweet_id:
                    continue
                
                # 更新状态为处理中
                self.tweet_status[tweet_id]["status"] = "processing"
                
                text = str(tweet.get("text") or "")
                user_name = str(tweet.get("user_name") or tweet.get("screen_name") or "")
                user_intro_mapping = getattr(
                    self.ai_router.config, "user_intro_mapping", {}
                ) if hasattr(self.ai_router, "config") else {}
                introduction = user_intro_mapping.get(user_name, "unknown author")
                
                try:
                    # 异步调用 AI，30 秒超时
                    ai_result = await call_ai_for_tweet_async(
                        text=text,
                        author=user_name,
                        introduction=introduction,
                        timeout=30
                    )
                    self.ai_results_cache[tweet_id] = ai_result
                    self.tweet_status[tweet_id]["status"] = "done"
                    print(f"[AI_WORKER] completed for tweet {tweet_id}")
                except asyncio.TimeoutError:
                    self.tweet_status[tweet_id]["status"] = "timeout"
                    print(f"[AI_WORKER] timeout after 30s for tweet {tweet_id}")
                except Exception as e:
                    self.tweet_status[tweet_id]["status"] = "error"
                    print(f"[AI_WORKER] error for tweet {tweet_id}: {e}")
                    
            except Exception as e:
                print(f"[AI_WORKER] unexpected error: {e}")
                await asyncio.sleep(0.5)

    async def _cleanup_expired_tweets(self) -> None:
        """
        定期清理 60 秒未完成的推文。
        
        - 每 5 秒检查一次
        - 对于超过 60 秒还未完成的推文：删除状态记录 + 删除缓存结果
        - 日志输出清理操作
        """
        while True:
            try:
                await asyncio.sleep(5)  # 每 5 秒检查一次
                now = time.time()
                expired_ids = []
                
                for tweet_id, status_info in self.tweet_status.items():
                    created_at = status_info.get("created_at", now)
                    if now - created_at > 60:  # 60 秒未完成
                        expired_ids.append(tweet_id)
                
                for tweet_id in expired_ids:
                    del self.tweet_status[tweet_id]
                    self.ai_results_cache.pop(tweet_id, None)
                    print(f"[CLEANUP] expired tweet {tweet_id} removed after 60s")
                    
            except Exception as e:
                print(f"[CLEANUP] error: {e}")

    async def stream(self) -> AsyncIterator[TradeSignal]:
        """
        异步信号流（异步队列版）：
        
        1. 启动 3 个后台 AI worker 任务
        2. 启动过期推文清理任务
        3. 主循环：读推文 → 入队（非阻塞）→ 检查缓存中的结果 → yield Signal
        4. 主循环保持 10 秒周期，不被 AI 阻塞
        """
        # 启动 3 个后台 worker 任务
        for i in range(3):
            worker_task = asyncio.create_task(self._ai_worker())
            self.worker_tasks.append(worker_task)
            print(f"[AI_QUEUE] worker {i+1} started")
        
        # 启动过期推文清理任务
        self.cleanup_task = asyncio.create_task(self._cleanup_expired_tweets())
        print("[AI_QUEUE] cleanup task started")
        
        try:
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

                    # 推文入队（非阻塞），立即返回
                    await self.ai_queue.put({
                        "tweet": tweet,
                        "tweet_id": tweet_id,
                    })
                    self.tweet_status[tweet_id] = {
                        "status": "pending",
                        "created_at": time.time(),
                    }
                    print(f"[AI_QUEUE] tweet {tweet_id} enqueued for AI analysis")

                    # 检查缓存中是否已有结果（AI worker 已完成）
                    if tweet_id in self.ai_results_cache:
                        ai_result = self.ai_results_cache.pop(tweet_id)
                        signal = self._to_trade_signal(tweet, ai_result)
                        if signal is not None:
                            new_ids.append(tweet_id)
                            # 标记为已处理（仅当生成有效 signal 时）
                            mark_as_processed([tweet_id])
                            yield signal

                if new_ids:
                    self.processed_store.add_many(new_ids)

                await asyncio.sleep(self.tweet_conf.poll_interval_sec)
        
        finally:
            # 清理后台任务
            for task in self.worker_tasks:
                task.cancel()
            if self.cleanup_task:
                self.cleanup_task.cancel()

    def _save_raw_batch(self, tweets: List[RawTweet]) -> None:
        """
        将当前批次的原始推文写入 JSON 文件（latest_batch.json）。
        """
        self.tweet_conf.crawled_json_dir.mkdir(parents=True, exist_ok=True)
        path = self.tweet_conf.crawled_json_dir / "latest_batch.json"
        path.write_text(json.dumps(tweets, ensure_ascii=False, indent=2), encoding="utf-8")

    def _to_trade_signal(self, tweet: RawTweet, ai_result: Optional[Any]) -> Optional[TradeSignal]:
        """
        将推文 + AI 分析结果转换为 TradeSignal。

        流程：
        1. 调用 call_ai_for_tweet() 分析推文文本（如果还没分析过）
        2. 从 AI 结果提取交易币种（symbol）、方向（direction）、置信度
        3. 转换为 TradeSignal 返回

        AI 分析结果格式（来自 Poe API）：
        {
            "交易币种": "BTC" | ["BTC", "ETH"],
            "交易方向": "做多" | "做空",
            "消息置信度": 0-100,
            ...其他字段
        }
        """
        text = str(tweet.get("text") or "")
        if not text.strip():
            return None

        # 若 ai_result 为 None，则现场调用 AI 分析
        if ai_result is None:
            user_name = str(tweet.get("user_name") or tweet.get("screen_name") or "")
            # 从配置读取用户简介，如果没有则用默认值
            user_intro_mapping = getattr(
                self.ai_router.config, "user_intro_mapping",
                {}
            ) if hasattr(self.ai_router, "config") else {}
            introduction = user_intro_mapping.get(user_name, "unknown author")
            
            try:
                ai_result = call_ai_for_tweet(text, user_name, introduction)
                print(f"[_to_trade_signal] AI result: {ai_result}")
            except Exception as e:
                print(f"[_to_trade_signal] AI analyze failed: {e}")
                ai_result = {}

        # 从 AI 结果提取交易信息
        symbol = detect_trade_symbol(ai_result)
        if symbol is None:
            print(f"[_to_trade_signal] no valid symbol detected, skipping tweet {tweet.get('id')}")
            return None

        # 提取交易方向（AI 返回中文）
        direction = ai_result.get("交易方向") or ai_result.get("direction") or "做多"
        side: str = "BUY" if ("做多" in str(direction)) else "SELL"

        # 提取置信度
        confidence = ai_result.get("消息置信度") or ai_result.get("confidence") or 50

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
                "ai_result": ai_result,
                "confidence": confidence,
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


async def build_trading_app_context() -> TradingAppContext:
    """
    初始化整个交易应用的上下文：
    - 加载配置
    - 创建 AIModelRouter
    - 创建 BinanceAsyncClient
    - 创建 TwitterCrawlerSignalSource（数据来自 trading_bot/twitter_source.py）
    """
    config = load_config()
    ai_router = AIModelRouter(config.ai)
    exchange_client = BinanceAsyncClient(config=config)

    base_dir = Path(__file__).resolve().parent.parent
    tweet_conf = TweetSignalSourceConfig(
        crawled_json_dir=base_dir / "推特抢跑" / "twitter_media",
        processed_id_path=base_dir / "推特抢跑" / "twitter_media" / "processed_ids.json",
        poll_interval_sec=10,  # 每 10 秒执行一次：推特查询 → AI 分析 → 下单
    )

    # 从 twitter_source 导入数据获取函数（支持版本切换）
    # 默认调用 fetch_latest_tweets()，内部可使用：
    # - fetch_latest_tweets_from_local_with_logging()  # 本地测试版
    # - fetch_latest_tweets_from_api_with_logging()    # API 版（需配置 api_key）
    try:
        from .twitter_source import fetch_latest_tweets
        signal_source: SignalSource = TwitterCrawlerSignalSource(
            fetch_func=fetch_latest_tweets,
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
    从 SignalSource 消费 TradeSignal，计算下单数量，执行下单，并启动风控监控。

    改进：
    1. 集成 RiskManager 进行止损止盈监控
    2. 为每个下单创建对应的 Position，注册风控监控
    3. 增加详细的日志输出（[SIGNAL]、[ORDER]、[STOP_LOSS]、[TAKE_PROFIT]）
    4. 支持多持仓并发监控
    """
    from .domain import calculate_order_quantity_from_balance, StrategyConfig, merge_strategy_config, Position
    from .risk_exit import RiskManager

    # 初始化风控管理器
    # 注：这里简化了 price_fetcher 和 close_executor，实际应从 exchange_client 抽离
    async def price_fetcher(symbol: str) -> float:
        """获取指定 symbol 的最新价格"""
        try:
            return await app.exchange_client.get_latest_price(symbol=symbol)
        except Exception as e:
            print(f"[PRICE_FETCH] error for {symbol}: {e}")
            return 0.0

    async def close_executor(position: Position, size_pct: float, reason: str) -> Any:
        """执行平仓操作"""
        try:
            qty_to_close = position.remaining_qty * size_pct
            side = "SELL" if position.side.upper() in ("BUY", "LONG") else "BUY"
            
            print(f"[EXIT] {reason}: closing {qty_to_close:.8f} of {position.symbol} (side={side})")
            
            result = await app.exchange_client.place_future_market_order(
                symbol=position.symbol,
                side=side,
                quantity=qty_to_close,
            )
            print(f"[EXIT] order result: {result}")
            return result
        except Exception as e:
            print(f"[EXIT] error closing position: {e}")
            return None

    risk_manager = RiskManager(
        risk_conf=app.config.risk,
        price_fetcher=price_fetcher,
        close_executor=close_executor,
        poll_interval_sec=1.0,
    )

    # 追踪所有活跃的风控监控任务
    monitor_tasks: Dict[str, asyncio.Task] = {}

    async for signal in await app.signal_source.stream():
        try:
            tweet_id = signal.meta.get("tweet_id", "unknown")
            
            # [SIGNAL] 日志
            print(
                f"[SIGNAL] received: tweet_id={tweet_id}, symbol={signal.symbol}, side={signal.side}, "
                f"confidence={signal.meta.get('confidence', 'N/A')}"
            )

            # 把全局 RiskConfig 和 signal 合并成 StrategyConfig
            strategy_conf: StrategyConfig = merge_strategy_config(app.config.risk, signal)

            # 获取账户信息与市价
            quote_asset = "USDT"
            balance = await app.exchange_client.get_balance(asset=quote_asset)
            price = await app.exchange_client.get_latest_price(symbol=signal.symbol)

            # 简单的交易规格参数
            min_qty = 0.001
            step_size = 0.0001

            # 计算下单数量
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
                    f"[SIGNAL] calculated quantity <= 0, skipping. "
                    f"(balance={balance}, price={price}, pos_pct={strategy_conf.position_pct})"
                )
                continue

            # [ORDER] 日志 - 下单前
            print(
                f"[ORDER] placing market order: symbol={signal.symbol}, side={signal.side}, "
                f"qty={quantity:.8f}, price~{price:.8f}"
            )

            # 执行下单
            order_resp = await app.exchange_client.place_future_market_order(
                symbol=signal.symbol,
                side=signal.side,
                quantity=quantity,
            )

            # [ORDER] 日志 - 下单后
            print(f"[ORDER] response: {order_resp}")
            
            # 标记推文为已处理（下单成功后）
            mark_as_processed([tweet_id])
            print(f"[TWITTER_API] marked tweet {tweet_id} as processed")

            # 创建 Position 对象并注册风控监控
            position = Position(
                symbol=signal.symbol,
                side=signal.side,
                entry_price=price,
                quantity=quantity,
                strategy=strategy_conf,
            )
            position_id = risk_manager.add_position(position)

            # 为这个 position 启动监控任务
            monitor_task = asyncio.create_task(risk_manager.monitor_loop(position_id))
            monitor_tasks[position_id] = monitor_task

            print(f"[RISK_MANAGER] registered position {position_id}, monitoring started")

        except Exception as e:
            print(f"[SIGNAL] error processing signal: {e}")
            continue


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