> # IMPLEMENTATION_v1.3.2.md
> 
> **版本**：v1.3.2（清理旧代码：删除废弃的 _load_twitter_fetch_func()）  
> **日期**：2025-11-17 18:07 (北京时间)
> 
> ---
> 
> ## 核心变更概述
> 
> ### 改动清单
> 
> | 文件 | 变更 | 说明 |
> |------|------|------|
> | `trading_bot/app_runner.py` | ❌ 删除 `_load_twitter_fetch_func()` | 废弃函数，不再需要 |
> | `trading_bot/app_runner.py` | ✅ 更新 `build_trading_app_context()` | 直接导入 `twitter_source.fetch_latest_tweets` |
> 
> ---
> 
> ## 变更原因
> 
> ### 背景
> 
> 在 v1.3.1 版本中，我们将所有推特数据获取逻辑集中在 `trading_bot/twitter_source.py` 中，并提供了两个版本：
> 
> 1. `fetch_latest_tweets_from_api_with_logging()` - API 版（真实数据源）
> 2. `fetch_latest_tweets_from_local_with_logging()` - 本地版（测试用）
> 
> 同时，主入口函数 `fetch_latest_tweets()` 已经实现了版本切换逻辑。
> 
> ### 问题
> 
> `app_runner.py` 中仍保留旧的导入机制：
> 
> ```python
> async def _load_twitter_fetch_func() -> FetchLatestTweetsFunc:
>     """
>     从 'trading_bot/twitter_crawler_functional_min.py' 导入获取最近消息的函数。
>     """
>     module = importlib.import_module("trading_bot.twitter_crawler_functional_min".replace("/", "."))
>     func = getattr(module, "fetch_latest_tweets", None)
>     # ...
> ```
> 
> 这个函数：
> - 尝试从 `trading_bot/twitter_crawler_functional_min.py` 导入
> - 使用 `importlib.import_module` 动态导入
> - 与新架构不兼容（数据获取逻辑已在 `twitter_source.py`）
> 
> ---
> 
> ## 修改方案
> 
> ### 删除废弃函数
> 
> **原代码（第 397-414 行）**：
> ```python
> async def _load_twitter_fetch_func() -> FetchLatestTweetsFunc:
>     """
>     从 'trading_bot/twitter_crawler_functional_min.py' 导入获取最近消息的函数。
> 
>     你需要在该文件中提供一个协程函数，例如：
>         async def fetch_latest_tweets() -> list[dict]:
>             ...
> 
>     若不存在，则抛异常。
>     """
>     module = importlib.import_module("trading_bot.twitter_crawler_functional_min".replace("/", "."))
>     func = getattr(module, "fetch_latest_tweets", None)
>     if func is None:
>         raise RuntimeError(
>             "在 'trading_bot/twitter_crawler_functional_min.py' 中找不到 fetch_latest_tweets 函数，"
>             "请实现：async def fetch_latest_tweets() -> list[dict]"
>         )
>     return func
> ```
> 
> **已删除** ✓
> 
> ---
> 
> ### 更新 build_trading_app_context()
> 
> **原代码（第 417-453 行）**：
> ```python
> async def build_trading_app_context() -> TradingAppContext:
>     """
>     初始化整个交易应用的上下文：
>     - 加载配置
>     - 创建 AIModelRouter
>     - 创建 BinanceAsyncClient
>     - 创建 TwitterCrawlerSignalSource（如果导入失败，则使用 InMemorySignalSource）
>     """
>     config = load_config()
>     ai_router = AIModelRouter(config.ai)
>     exchange_client = BinanceAsyncClient(config=config)
> 
>     base_dir = Path(__file__).resolve().parent.parent
>     tweet_conf = TweetSignalSourceConfig(
>         crawled_json_dir=base_dir / "trading_bot" / "twitter_media",
>         processed_id_path=base_dir / "trading_bot" / "twitter_media" / "processed_ids.json",
>         poll_interval_sec=10,  # 改为 10 秒，每 10 秒执行一次推特爬虫 → AI 分析 → 下单
>     )
> 
>     try:
>         fetch_func = await _load_twitter_fetch_func()  # ← 调用废弃函数
>         signal_source: SignalSource = TwitterCrawlerSignalSource(
>             fetch_func=fetch_func,
>             tweet_conf=tweet_conf,
>             ai_router=ai_router,
>         )
>     except Exception as e:
>         print(f"[build_trading_app_context] fallback to InMemorySignalSource because: {e}")
>         signal_source = InMemorySignalSource()
> 
>     return TradingAppContext(...)
> ```
> 
> **新代码**：
> ```python
> async def build_trading_app_context() -> TradingAppContext:
>     """
>     初始化整个交易应用的上下文：
>     - 加载配置
>     - 创建 AIModelRouter
>     - 创建 BinanceAsyncClient
>     - 创建 TwitterCrawlerSignalSource（数据来自 trading_bot/twitter_source.py）
>     """
>     config = load_config()
>     ai_router = AIModelRouter(config.ai)
>     exchange_client = BinanceAsyncClient(config=config)
> 
>     base_dir = Path(__file__).resolve().parent.parent
>     tweet_conf = TweetSignalSourceConfig(
>         crawled_json_dir=base_dir / "trading_bot" / "twitter_media",
>         processed_id_path=base_dir / "trading_bot" / "twitter_media" / "processed_ids.json",
>         poll_interval_sec=10,  # 每 10 秒执行一次：推特查询 → AI 分析 → 下单
>     )
> 
>     # 从 twitter_source 导入数据获取函数（支持版本切换）
>     # 默认调用 fetch_latest_tweets()，内部可使用：
>     # - fetch_latest_tweets_from_local_with_logging()  # 本地测试版
>     # - fetch_latest_tweets_from_api_with_logging()    # API 版（需配置 api_key）
>     try:
>         from .twitter_source import fetch_latest_tweets
>         signal_source: SignalSource = TwitterCrawlerSignalSource(
>             fetch_func=fetch_latest_tweets,
>             tweet_conf=tweet_conf,
>             ai_router=ai_router,
>         )
>     except Exception as e:
>         print(f"[build_trading_app_context] fallback to InMemorySignalSource because: {e}")
>         signal_source = InMemorySignalSource()
> 
>     return TradingAppContext(...)
> ```
> 
> **主要变更**：
> - 直接 `from .twitter_source import fetch_latest_tweets`
> - 注释说明支持版本切换（本地版/API 版）
> - 删除动态导入和旧文件依赖
> 
> ---
> 
> ## 数据获取架构
> 
> ### 当前架构
> 
> ```
> app_runner.py
>     ↓ 导入
> twitter_source.py
>     ↓ 调用
> ┌─────────────────────────────────────┐
> │  fetch_latest_tweets()              │
> │  （主入口，可切换版本）               │
> └─────────────────────────────────────┘
>     ↓ 默认调用
> ┌─────────────────────────────────────┐
> │  fetch_latest_tweets_from_local_with_logging()  │
> │  或                                   │
> │  fetch_latest_tweets_from_api_with_logging()    │
> └─────────────────────────────────────┘
>     ↓
> 本地 JSON 或真实 API
> ```
> 
> ### 版本切换
> 
> 在 `twitter_source.py` 第 300-322 行：
> 
> ```python
> async def fetch_latest_tweets() -> List[Dict[str, Any]]:
>     """
>     获取最新推文的异步接口（推荐方法）。
>     
>     版本切换说明：
>     - 初期测试：使用本地版本
>     - 后期集成：使用 API 版本
>     
>     在 app_runner.py 中的调用处选择其中一个：
>       # return await fetch_latest_tweets_from_api_with_logging()     # 后期：真实 API
>       # return await fetch_latest_tweets_from_local_with_logging()   # 初期：本地测试
>     
>     返回：推文列表，每条至少包含 id、text 字段
>     """
>     # 【初期开发推荐】使用本地版本测试
>     return await fetch_latest_tweets_from_local_with_logging()
>     
>     # 【后期集成可改为】使用 API 版本
>     # return await fetch_latest_tweets_from_api_with_logging()
> ```
> 
> **切换方法**：
> - 修改第 322 行的 return 语句即可
> - 无需改动 `app_runner.py`
> 
> ---
> 
> ## 验证要点
> 
> ### 测试本地版本
> 
> ```bash
> # 确保本地 JSON 文件存在
> ls trading_bot/twitter_media/*.json
> 
> # 运行应用
> python trading_bot/main.py
> 
> # 期望输出：
> # [build_trading_app_context] using fetch_latest_tweets from twitter_source
> # [AI_QUEUE] worker 1 started
> # [AI_QUEUE] cleanup task started
> # [TwitterCrawlerSignalSource] fetch_latest_tweets error: ...
> ```
> 
> ### 测试 API 版本
> 
> ```python
> # 1. 修改 twitter_source.py 第 322 行
> return await fetch_latest_tweets_from_api_with_logging()
> 
> # 2. 配置 config.py
> twitter_api:
>   api_key: "your-api-key"
>   user_intro_mapping:
>     "elonmusk": "Elon Musk"
>     "vitalikbuterin": "Vitalik Buterin"
> 
> # 3. 运行并检查日志
> # [TWITTER_API] 并发抓取 2 个用户的推文...
> ```
> 
> ---
> 
> ## 注意事项
> 
> ### 兼容性与清理
> 
> - ✅ **已删除**：`importlib` 导入语句（不再需要动态导入）
> - ✅ **已删除**：`"trading_bot/twitter_crawler_functional_min.py"` 的文档引用
> - ✅ **保留**：`FetchLatestTweetsFunc` 类型别名（用于类型提示）
> - ✅ **保留**：异常处理机制（失败时回退到 `InMemorySignalSource`）
> 
> ### 遗留文件
> 
> 如果存在以下文件，可以安全删除（不再使用）：
> - `trading_bot/twitter_crawler_functional_min.py`
> 
> ---
> 
> ## 完成定义 (DoD)
> 
> - [x] 删除 `_load_twitter_fetch_func()` 函数
> - [x] 在 `build_trading_app_context()` 中直接导入 `fetch_latest_tweets`
> - [x] 更新文档说明，指明数据来源为 `twitter_source.py`
> - [x] 保留类型别名 `FetchLatestTweetsFunc`
> - [x] 保留异常处理和回退机制
> - [x] 代码无类型检查错误
> 
> ---
> 
> ## 快速参考
> 
> ### 调试命令
> 
> ```bash
> # 查看已删除的函数是否还有引用
> grep -r "_load_twitter_fetch_func" trading_bot/
> 
> # 期望输出：无结果
> ```
> 
> ### 快速验证
> 
> ```python
> # 在 Python REPL 中测试
> import asyncio
> from trading_bot.twitter_source import fetch_latest_tweets
> 
> async def test():
>     tweets = await fetch_latest_tweets()
>     print(f"获取 {len(tweets)} 条推文")
> 
> asyncio.run(test())
> ```
> 
> ---
> 
> ## 后续行动
> 
> 1. 本地验证：运行 `python trading_bot/main.py`，确认信号源正常工作
> 2. API 集成：配置 `config.py` 中的 `twitter_api.api_key`
> 3. 清理旧文件：删除 `trading_bot/twitter_crawler_functional_min.py`（如果存在）
> 