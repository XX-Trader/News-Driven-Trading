"""
trading_bot.app_runner

主应用编排逻辑（MVP 版，可运行）：

- 定时从"推特抢跑"侧的爬虫接口获取最新消息（20 条左右）；
- 将原始消息保存为 JSON 文件；
- 用最简单的"已处理 id 列表"避免重复处理（本地 JSON 文件存储 processed_ids）；
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
import time
from typing import Any

import asyncio
import importlib
from dataclasses import dataclass
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, List, Optional

try:
    from ai_base import AIInput, AIModelRouter
    from config import AppConfig, load_config
    from domain import TradeSignal, calculate_order_quantity_from_balance, StrategyConfig, merge_strategy_config, Position
    from exchange_binance_async import BinanceAsyncClient
    from signals import SignalSource, InMemorySignalSource
    from tweet_analyzer import call_ai_for_tweet_async, detect_trade_symbol
    from twitter_source import load_processed_ids, mark_as_processed, fetch_latest_tweets
    from risk_exit import RiskManager

except ImportError:
    from .ai_base import AIInput, AIModelRouter
    from .config import AppConfig, load_config
    from .domain import TradeSignal, calculate_order_quantity_from_balance, StrategyConfig, merge_strategy_config, Position
    from .exchange_binance_async import BinanceAsyncClient
    from .signals import SignalSource, InMemorySignalSource
    from .tweet_analyzer import call_ai_for_tweet_async, detect_trade_symbol
    from .twitter_source import load_processed_ids, mark_as_processed, fetch_latest_tweets
    from .risk_exit import RiskManager

# ----------------------------
# 类型别名与简单协议定义
# ----------------------------

RawTweet = Dict[str, Any]

# 期望：async def fetch_latest_tweets() -> list[RawTweet]
FetchLatestTweetsFunc = Callable[[], Awaitable[List[RawTweet]]]


@dataclass
class TweetSignalSourceConfig:
    """
    推特信号源配置。

    - poll_interval_sec: 定时轮询间隔（秒），默认 10 秒
    """

    poll_interval_sec: int = 10


# ----------------------------
# 推特信号源：基于爬虫接口 + 本地 JSON
# ----------------------------

class TwitterCrawlerSignalSource(SignalSource):
    """
    基于 twitter_crawler_functional_min.py 的信号源：

    - 定期调用 fetch_latest_tweets() 获取最近 N 条消息；
    - 把原始结果保存成 JSON 文件（latest_batch.json）；
    - 使用全局 load_processed_ids() 过滤已经处理过的 tweet_id；
    - 对未处理消息调用 AIModelRouter（当前 Dummy）做文本分析；
    - 将"未处理消息"全部转换为 TradeSignal 输出（你后续可用 AI 分数做过滤）。
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
        
        # 异步 AI 队列与缓存
        self.ai_queue: asyncio.Queue = asyncio.Queue(maxsize=0)  # 无限制队列
        self.ai_results_cache: Dict[str, Any] = {}  # {tweet_id: ai_result}
        self.tweet_status: Dict[str, Dict[str, Any]] = {}  # {tweet_id: {status, retry_count, created_at, ...}}
        
        # 后台 worker 任务
        self.worker_tasks: List[asyncio.Task] = []
        self.cleanup_task: Optional[asyncio.Task] = None

    async def _ai_worker(self) -> None:
        """
        后台 AI worker：从队列消费推文，异步调用 AI，存储结果。

        工作流程：
        1. 从 self.ai_queue 获取推文数据（阻塞等待）
        2. 更新状态为 "processing"
        3. 调用 call_ai_for_tweet_async() 分析（30秒超时）
        4. 将结果存入 self.ai_results_cache
        5. 更新状态为 "done"、"timeout" 或 "error"

        注意：worker 为守护进程，持续运行直到任务取消
        """
        while True:
            try:
                # 从队列取推文数据
                tweet_data = await self.ai_queue.get()
                tweet = tweet_data
                tweet_id = tweet_data.get("id")
                
                if not tweet_id:
                    continue
                
                # 更新状态为处理中
                if tweet_id not in self.tweet_status:
                    self.tweet_status[tweet_id] = {"retry_count": 0}
                self.tweet_status[tweet_id]["status"] = "processing"
                
                text = str(tweet)
                user_name = str(tweet.get("author", {}).get("userName", None))
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
                    # 成功时重置重试计数
                    self.tweet_status[tweet_id]["retry_count"] = 0
                    print(f"[AI_WORKER] completed for tweet {tweet_id}, result: {ai_result}")
                except asyncio.TimeoutError:
                    self.tweet_status[tweet_id]["status"] = "timeout"
                    # 超时时增加重试计数
                    self.tweet_status[tweet_id]["retry_count"] = self.tweet_status[tweet_id].get("retry_count", 0) + 1
                    print(f"[AI_WORKER] timeout after 30s for tweet {tweet_id} (retry {self.tweet_status[tweet_id]['retry_count']}/3)")
                except Exception as e:
                    self.tweet_status[tweet_id]["status"] = "error"
                    # 异常时增加重试计数
                    self.tweet_status[tweet_id]["retry_count"] = self.tweet_status[tweet_id].get("retry_count", 0) + 1
                    print(f"[AI_WORKER] error for tweet {tweet_id}: {e} (retry {self.tweet_status[tweet_id]['retry_count']}/3)")
                    
            except Exception as e:
                print(f"[AI_WORKER] unexpected error: {e}")
                await asyncio.sleep(0.5)

    async def _cleanup_expired_tweets(self) -> None:
        """
        清理过期推文记录（后台守护任务）。

        清理策略：
        - 检查频率：每 5 秒一次
        - 过期时间：超过 60 秒未完成的推文
        - 清理内容：删除 status 记录 + 缓存结果（如果有）

        目的：防止内存泄漏，长期运行不会累积过多无效的推文状态
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

        注意：使用 async for 直接迭代，不要对生成器使用 await
        """
        print("[DEBUG] stream() starting...")
        
        # 启动 3 个后台 worker 任务
        for i in range(3):
            worker_task = asyncio.create_task(self._ai_worker())
            self.worker_tasks.append(worker_task)
            print(f"[AI_QUEUE] worker {i+1} started")
        
        # 启动过期推文清理任务
        self.cleanup_task = asyncio.create_task(self._cleanup_expired_tweets())
        print("[AI_QUEUE] cleanup task started")
        
        loop_count = 0
        
        try:
            while True:
                loop_count += 1
                print(f"[DEBUG] === Loop #{loop_count} start ===")
                
                try:
                    print(f"[DEBUG] Calling fetch_func()...")
                    raw_tweets = await self.fetch_func()
                    print(f"[DEBUG] fetch_func() returned {len(raw_tweets)} tweets")
                    # 输出第一条推文内容查看结构
                    if raw_tweets:
                        print(f"[DEBUG] First tweet structure: {raw_tweets[0]}")
                except Exception as e:
                    print(f"[TwitterCrawlerSignalSource] fetch_latest_tweets error: {e}")
                    import traceback
                    print(f"[DEBUG] traceback: {traceback.format_exc()}")
                    await asyncio.sleep(self.tweet_conf.poll_interval_sec)
                    continue

                if not raw_tweets:
                    print(f"[DEBUG] No tweets returned, will sleep for {self.tweet_conf.poll_interval_sec} seconds")
                
                processed_count = 0
                skipped_count = 0
                
                for tweet in raw_tweets:
                    tweet_id = str(tweet.get("id") or tweet.get("tweet_id") or "")
                    if not tweet_id:
                        continue
                    
                    # 使用全局 processed_ids 检查是否已处理
                    if tweet_id in load_processed_ids():
                        skipped_count += 1
                        continue  # 已处理
                    
                    # 检查重试次数，如果达到3次则跳过
                    if tweet_id in self.tweet_status:
                        retry_count = self.tweet_status[tweet_id].get("retry_count", 0)
                        if retry_count >= 3:
                            print(f"[AI_QUEUE] tweet {tweet_id} skipped (max retries 3 reached)")
                            skipped_count += 1
                            continue  # 已达到最大重试次数，不再处理
                    
                    processed_count += 1

                    # 推文入队（非阻塞），立即返回
                    await self.ai_queue.put({
                        "tweet": tweet,
                        "tweet_id": tweet_id,
                    })
                    
                    # 初始化或更新推文状态
                    if tweet_id not in self.tweet_status:
                        self.tweet_status[tweet_id] = {
                            "retry_count": 0,
                            "status": "pending",
                            "created_at": time.time(),
                        }
                        print(f"[AI_QUEUE] tweet {tweet_id} enqueued for AI analysis (retry 0/3)")
                    else:
                        # 更新状态为pending（重试）
                        self.tweet_status[tweet_id]["status"] = "pending"
                        retry_count = self.tweet_status[tweet_id].get("retry_count", 0)
                        print(f"[AI_QUEUE] tweet {tweet_id} re-enqueued for AI analysis (retry {retry_count}/3)")

                    # 检查缓存中是否已有结果（AI worker 已完成）
                    if tweet_id in self.ai_results_cache:
                        ai_result = self.ai_results_cache.pop(tweet_id)
                        print(f"[DEBUG] AI result for tweet {tweet_id}: {ai_result}")
                        signal = self._to_trade_signal(tweet, ai_result)
                        if signal is not None:
                            # 标记为已处理（仅当生成有效 signal 时）
                            mark_as_processed([tweet_id])
                            yield signal

                print(f"[DEBUG] Loop #{loop_count} finished: processed {processed_count} new tweets, skipped {skipped_count} already processed")
                print(f"[DEBUG] Sleeping for {self.tweet_conf.poll_interval_sec} seconds...")
                await asyncio.sleep(self.tweet_conf.poll_interval_sec)
        
        except asyncio.CancelledError:
            print("[DEBUG] stream() cancelled")
            raise
        except Exception as e:
            print(f"[DEBUG] stream() unexpected error: {e}")
            import traceback
            print(f"[DEBUG] traceback: {traceback.format_exc()}")
            raise
        finally:
            print("[DEBUG] stream() cleaning up...")
            # 清理后台任务
            for task in self.worker_tasks:
                task.cancel()
            if self.cleanup_task:
                self.cleanup_task.cancel()
            print("[DEBUG] stream() finished cleanup")

    def _to_trade_signal(self, tweet: RawTweet, ai_result: Optional[Any]) -> Optional[TradeSignal]:
        """
        转换推文 + AI 结果为 TradeSignal。

        设计原则：
        - ai_result 为 None 时直接跳过（不再同步调用 AI）
        - AI 分析必须在后台 worker 中完成，不能阻塞主循环
        - 仅当检测出有效交易对时才生成信号

        AI 结果格式：
        {
            "交易币种": "BTC" 或 ["BTC", "ETH"],
            "交易方向": "做多" | "做空",
            "消息置信度": 0-100,
            ...
        }
        """
        text = str(tweet.get("text") or "")
        if not text.strip():
            return None

        # ai_result 为 None 时直接返回 None（跳过该推文）
        if ai_result is None:
            return None

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

    # 创建推特信号源配置（仅轮询间隔）
    tweet_conf = TweetSignalSourceConfig(poll_interval_sec=10)

    # 从 twitter_source 导入数据获取函数（支持版本切换）
    # 默认调用 fetch_latest_tweets()，内部可使用：
    # - fetch_latest_tweets_from_local_with_logging()  # 本地测试版
    # - fetch_latest_tweets_from_api_with_logging()    # API 版（需配置 api_key）
    try:
        
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

    注意：使用 async for 直接迭代 signal_source.stream()，不要对生成器使用 await
    """
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
    print("[main] starting risk manager")
    risk_manager = RiskManager(
        risk_conf=app.config.risk,
        price_fetcher=price_fetcher,
        close_executor=close_executor,
        poll_interval_sec=1.0,
    )
    print("[main] starting risk manager...")
    # 追踪所有活跃的风控监控任务
    monitor_tasks: Dict[str, asyncio.Task] = {}
    
    async for signal in app.signal_source.stream():
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
            import traceback
            print(f"[SIGNAL] error processing signal: {e}")
            print(f"[SIGNAL] traceback:\n{traceback.format_exc()}")
            continue


async def start_trading_app() -> None:
    """
    启动整个交易应用：

    - 构建上下文；
    - 启动"信号消费 + 下单"的主任务；
    - 直到被 Ctrl+C 中断。

    资源清理：
    - 关闭交易所客户端的 session（防止连接泄漏）
    - 取消所有后台任务
    """
    app = await build_trading_app_context()
    main_task = asyncio.create_task(_consume_signals_and_trade(app))
    app.tasks.append(main_task)

    print("[trading_app] started. Press Ctrl+C to stop.")

    try:
        await asyncio.gather(*app.tasks, return_exceptions=True)
    except asyncio.CancelledError:
        print("[trading_app] cancelled.")
    finally:
        # 关闭交易所客户端的 session（防止连接泄漏）
        print("[trading_app] closing exchange client session...")
        await app.exchange_client.close()
        print("[trading_app] exchange client closed")


async def stop_trading_app(app: TradingAppContext) -> None:
    """
    预留的停止逻辑：取消所有任务，清理资源。
    """
    for t in app.tasks:
        t.cancel()
    # TODO: 关闭 aiohttp 会话、持久化必要状态等