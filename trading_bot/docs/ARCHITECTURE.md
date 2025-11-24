# Trading Bot 架构设计文档

**版本**: v2.0.0  
**最后更新**: 2025-11-22  
**文档状态**: 基于现有代码结构文档化

---

## 1. 项目概述与目标

### 1.1 项目简介
Trading Bot 是一个基于社交媒体信号（主要为Twitter推文）的加密货币自动化交易系统。系统通过实时监控特定KOL（意见领袖）的推文，利用AI分析提取交易信号，并自动执行币安（Binance）合约交易，实现从信息获取到交易执行的完整闭环。

### 1.2 核心目标
- **信息优势**: 第一时间捕捉市场影响者的交易观点
- **自动化执行**: 消除人工干预延迟，实现秒级响应
- **风险控制**: 集成止损止盈机制，保护交易本金
- **可扩展性**: 支持多信号源、多交易所、多策略
- **可追溯性**: 完整的推文处理记录和交易日志

### 1.3 业务价值
在传统量化交易基础上，增加社交媒体情绪维度，通过AI理解自然语言中的交易意图，构建信息差优势，适合高频事件驱动型交易策略。

---

## 2. 整体架构设计

系统采用**分层架构**设计，遵循关注点分离原则，各层职责清晰，便于维护和扩展。

### 2.1 架构分层概览

```
┌─────────────────────────────────────────────────────────────┐
│                    应用层 (Application Layer)                │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │   main.py   │  │ app_runner.py│  │  TradingAppContext  │ │
│  │  (入口)     │  │(主编排逻辑)  │  │   (应用上下文)       │ │
│  └─────────────┘  └─────────────┘  └─────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│                    核心层 (Core Layer)                       │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │   domain.py │  │  signals.py │  │   risk_exit.py      │ │
│  │(领域模型)   │  │(信号抽象)   │  │   (风控管理)        │ │
│  └─────────────┘  └─────────────┘  └─────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│                  适配器层 (Adapter Layer)                    │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────┐ │
│  │twitter_src.py│  │exchange_*.py │  │ tweet_analyzer.py  │ │
│  │(数据源适配)  │  │(交易所适配)  │  │   (AI分析适配)      │ │
│  └─────────────┘  └──────────────┘  └────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│                基础设施层 (Infrastructure Layer)             │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────┐ │
│  │   config.py │  │   network.py │  │ tweet_record_mngr.py││
│  │(配置管理)   │  │(网络工具)    │  │   (持久化)          │ │
│  └─────────────┘  └──────────────┘  └────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 架构特点

- **异步优先**: 全链路异步设计，支持高并发处理
- **事件驱动**: 基于推文的实时事件流处理
- **可插拔**: 各层通过接口解耦，支持快速替换实现
- **容错性**: AI调用失败重试、断连重连、异常隔离
- **可观测性**: 全流程日志、推文记录、交易追踪

---

## 3. 各层详细设计

### 3.1 应用层 (Application Layer)

**职责**: 应用编排、生命周期管理、模块组装

**核心组件**:

#### 3.1.1 `main.py` - 系统入口
- **功能**: 程序启动入口，信号处理，CLI接口
- **关键设计**:
  - 兼容多种运行方式（模块运行 vs 直接运行）
  - 注册SIGINT信号处理，支持优雅退出
  - 封装asyncio运行环境
- **接口**: `main()` → 启动整个应用

#### 3.1.2 `app_runner.py` - 主应用编排
- **功能**: 核心业务流程编排，模块协调
- **关键组件**:
  - `TwitterCrawlerSignalSource`: 推文信号源（支持后台AI队列）
  - `TradingAppContext`: 应用上下文容器
  - `_consume_signals_and_trade()`: 信号消费与交易循环
- **核心流程**:
  1. 构建应用上下文（配置、AI路由器、交易所客户端、信号源）
  2. 启动信号流消费
  3. 对每个信号：计算数量 → 下单 → 创建持仓 → 启动风控监控
  4. 资源清理与优雅退出

**设计亮点**:
- **AI队列架构**: 3个后台worker并发处理AI分析，主循环不被阻塞
- **推文记录管理**: 内存+文件双存储，支持断点续传
- **风控集成**: 每个持仓独立监控任务，支持止损止盈

### 3.2 核心层 (Core Layer)

**职责**: 领域模型定义、业务规则、核心算法

#### 3.2.1 `domain.py` - 领域模型
**核心类**:

- **TradeSignal**: 统一的交易信号结构
  ```python
  TradeSignal(
      symbol: str,                    # 交易对（如BTCUSDT）
      side: str,                      # BUY/SELL
      position_pct: Optional[float],  # 仓位百分比
      stop_loss_pct: Optional[float], # 止损百分比
      take_profit_scheme: Optional[List[Dict]], # 分批止盈
      source_id: Optional[str],       # 信号来源
      meta: Dict[str, Any]           # 附加信息（推文ID、AI结果等）
  )
  ```

- **StrategyConfig**: 单笔交易策略配置
  - 合并全局RiskConfig和信号特定参数
  - 提供统一的策略视图

- **Position**: 持仓抽象
  - 追踪开仓价、数量、剩余数量
  - 关联StrategyConfig，支持个性化风控
  - 记录已实现盈亏

- **ExitDecision**: 出场决策
  - 支持全部平仓、部分平仓、保持持仓
  - 包含决策原因，便于审计

**关键函数**:
- `merge_strategy_config()`: 合并全局和信号级策略参数
- `calculate_order_quantity_from_balance()`: 基于可用余额计算下单数量
  - 考虑仓位百分比、价格、最小下单量、步长
  - 向下取整，不足最小下单量返回0

#### 3.2.2 `signals.py` - 信号抽象
**设计哲学**: 所有信号源实现统一接口，便于扩展

- **SignalSource协议**: `async def stream() -> AsyncIterator[TradeSignal]`
- **InMemorySignalSource**: 内存信号源（测试/降级）
- **TwitterCrawlerSignalSource**: 推文爬虫信号源（实际使用）

#### 3.2.3 `risk_exit.py` - 风控管理
**职责**: 持仓监控、止损止盈执行

**核心组件**:
- **RiskManager**: 风控管理器
  - 持仓注册与追踪
  - 价格轮询（每秒）
  - 触发条件时执行平仓
  - 支持止损、分批止盈、时间退出

**关键设计**:
- 依赖注入：`price_fetcher`, `close_executor`接口
- 异步监控：`monitor_loop()`为每个持仓运行独立任务
- 灵活配置：支持配置轮询间隔、默认止损止盈参数

### 3.3 适配器层 (Adapter Layer)

**职责**: 外部系统适配，隔离变化

#### 3.3.1 `twitter_source.py` - 推特数据源适配器
**功能**: 推文获取、本地存储、版本切换

**架构**:
```
┌─────────────────────────────────────────┐
│      Twitter Data Source Adapter       │
├─────────────────────────────────────────┤
│  • fetch_latest_tweets()               │
│    - 统一入口                          │
│  • Local JSON Mode                     │
│    - fetch_latest_tweets_from_local() │
│  • API Mode                            │
│    - fetch_latest_tweets_from_api()   │
│    - 并发抓取多个用户                  │
│  • Logging                             │
│    - JSONL格式持久化                   │
│    - 按用户分文件存储                  │
└─────────────────────────────────────────┘
```

**关键特性**:
- **版本切换**: 本地模式（测试）vs API模式（生产）
- **并发抓取**: aiohttp并发请求多个用户
- **格式兼容**: 支持多种JSON格式（单条/列表/嵌套）
- **容错设计**: 超时处理、异常隔离、部分失败容忍

#### 3.3.2 `exchange_binance_async.py` - 交易所适配器
**职责**: 币安API封装，提供异步接口

**核心功能**:
- 行情查询：`get_latest_price()`, `get_balance()`
- 下单执行：`place_future_market_order()`
- 会话管理：aiohttp客户端生命周期管理
- 错误处理：API异常封装、重试逻辑

**设计原则**:
- 接口抽象：便于切换到其他交易所
- 异步实现：非阻塞IO，支持高并发
- 配置驱动：API密钥、基础URL可配置

#### 3.3.3 `tweet_analyzer.py` - AI分析适配器
**职责**: AI模型调用、结果解析、网络检测

**核心组件**:
- `call_ai_for_tweet_async()`: 异步AI调用（60秒超时）
- `ai_analyze_text()`: 同步AI调用（在线程池执行）
- `detect_trade_symbol()`: 从AI结果提取交易对
- `_check_network_once()`: 网络连通性检测（代理自动切换）

**设计亮点**:
- **网络自适应**: 自动检测直连/代理环境
- **容错机制**: 超时重试、异常分类
- **结果解析**: JSON解析失败时返回原始字符串包装
- **提示词模板**: 动态填充推文、作者、简介

#### 3.3.4 `ai_base.py` - AI基础接口
**职责**: AI路由器、配置抽象

**关键类**:
- **AIModelRouter**: AI模型路由（当前为Dummy实现）
- **AIInput**: AI输入结构
- **AIConfig**: AI配置（API密钥、模型、代理等）

### 3.4 基础设施层 (Infrastructure Layer)

#### 3.4.1 `config.py` - 配置管理
**设计**: 集中式配置管理，分层结构

```python
AppConfig
├── ai: AIConfig                     # AI配置
├── exchange: ExchangeConfig          # 交易所配置
├── risk: RiskConfig                  # 风控配置
├── twitter_api: TwitterAPIConfig     # 推特API配置
└── trading: TradingConfig            # 交易通用配置
```

**特性**:
- 类型安全：dataclass定义，静态检查友好
- 环境变量支持：自动从.env文件加载
- 嵌套结构：按模块分层，避免配置污染
- 单例模式：`load_config()`缓存加载结果

#### 3.4.2 `tweet_record_manager.py` - 推文记录管理
**功能**: 推文处理记录持久化与去重

**核心类**:
- **TweetProcessingRecord**: 单条推文处理记录
  - tweet_id: 推文ID（主键）
  - username: 作者
  - tweet_time: 推文时间
  - tweet_preview: 预览文本
  - ai_success: AI处理状态
  - ai_result: AI分析结果
  - trade_info: 交易执行信息
  - retry_count: 重试次数
  - processed_at: 处理时间

- **TweetRecordManager**: 记录管理器
  - `add_record()`: 添加新记录
  - `is_processed()`: 检查是否已处理（快速去重）
  - `update_ai_result()`: 更新AI结果
  - `update_trade_info()`: 更新交易信息
  - `save_to_file()`: 持久化到JSON文件
  - `load_from_file()`: 从文件加载

**存储格式**: `trading_bot/twitter_media/tweet_records.json`

**设计优势**:
- **双存储**: 内存Set快速判断 + 文件持久化
- **实时持久化**: AI成功或交易完成后立即保存，防数据丢失
- **完整追溯**: 记录全流程状态，便于审计

#### 3.4.3 `network.py` - 网络工具
**预留**: 网络检测、代理管理、连接池等辅助功能

---

## 4. 数据流与控制流

### 4.1 整体数据流

```
┌──────────────────────────────────────────────────────────────┐
│                    数据源层 (Twitter)                        │
│  KOL推文 → API/JSON → 原始推文数据(list[dict])               │
└──────────────────────┬───────────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────────────┐
│              适配器层 (Twitter Adapter)                      │
│  • 数据获取 → fetch_latest_tweets()                          │
│  • 本地存储 → JSONL日志                                      │
│  • 数据格式化 → 统一dict结构                                 │
└──────────────────────┬───────────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────────────┐
│            应用层 (App Runner)                               │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ 主循环（10秒周期）：                                     │  │
│  │ 1. 获取推文 → 去重检查 → 入AI队列                        │  │
│  │ 2. 后台Worker：3个并发处理AI分析（30秒超时）            │  │
│  │ 3. 检查AI结果缓存 → 生成TradeSignal → yield              │  │
│  │ 4. 记录管理：实时持久化推文状态                          │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────┬───────────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────────────┐
│              核心层 (Signal Processing)                      │
│  TradeSignal → merge_strategy_config() → StrategyConfig      │
└──────────────────────┬───────────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────────────┐
│            适配器层 (Exchange Adapter)                       │
│  • 查询余额 → get_balance()                                  │
│  • 查询价格 → get_latest_price()                             │
│  • 计算数量 → calculate_order_quantity_from_balance()        │
│  • 执行下单 → place_future_market_order()                    │
└──────────────────────┬───────────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────────────┐
│              核心层 (Risk Management)                        │
│  Position → RiskManager → 止损/止盈监控                      │
│  └─→ monitor_loop()（每秒轮询）                             │
│  └─→ 触发条件 → close_executor() → 平仓                     │
└──────────────────────────────────────────────────────────────┘
```

### 4.2 控制流详解

#### 4.2.1 主循环控制流

```python
# 伪代码：app_runner.py主循环
async def start_trading_app():
    app = await build_trading_app_context()  # 初始化
    await _consume_signals_and_trade(app)    # 主循环

async def _consume_signals_and_trade(app):
    async for signal in app.signal_source.stream():  # 异步流
        # 1. 接收信号
        print("[SIGNAL] received...")
        
        # 2. 合并策略配置
        strategy_conf = merge_strategy_config(app.config.risk, signal)
        
        # 3. 获取市场数据
        balance = await app.exchange_client.get_balance()
        price = await app.exchange_client.get_latest_price(signal.symbol)
        
        # 4. 计算下单数量
        quantity = calculate_order_quantity_from_balance(...)
        if quantity <= 0: continue
        
        # 5. 执行下单
        order_resp = await app.exchange_client.place_future_market_order(...)
        
        # 6. 更新推文记录
        record_manager.update_trade_info(...)
        
        # 7. 创建持仓并启动风控
        position = Position(...)
        position_id = risk_manager.add_position(position)
        monitor_task = asyncio.create_task(
            risk_manager.monitor_loop(position_id)
        )
```

#### 4.2.2 AI队列控制流

```python
# 伪代码：AI异步处理流程
class TwitterCrawlerSignalSource:
    def __init__(self):
        self.ai_queue = asyncio.Queue()              # AI任务队列
        self.ai_results_cache = {}                   # 结果缓存
        self.tweet_status = {}                       # 状态追踪
        self.worker_tasks = []                       # Worker任务列表
    
    async def stream():
        # 启动3个后台Worker
        for i in range(3):
            worker_task = asyncio.create_task(self._ai_worker())
            self.worker_tasks.append(worker_task)
        
        # 启动清理任务
        cleanup_task = asyncio.create_task(
            self._cleanup_expired_tweets()
        )
        
        while True:
            # 获取推文
            raw_tweets = await self.fetch_func()
            
            for tweet in raw_tweets:
                tweet_id = tweet["id"]
                
                # 去重检查
                if self.record_manager.is_processed(tweet_id):
                    continue
                
                # 入队（非阻塞）
                await self.ai_queue.put({
                    "tweet": tweet,
                    "tweet_id": tweet_id,
                })
                
                # 检查是否有结果
                if tweet_id in self.ai_results_cache:
                    ai_result = self.ai_results_cache.pop(tweet_id)
                    signal = self._to_trade_signal(tweet, ai_result)
                    yield signal
            
            await asyncio.sleep(poll_interval)
    
    async def _ai_worker():
        while True:
            queue_item = await self.ai_queue.get()
            tweet = queue_item["tweet"]
            tweet_id = queue_item["tweet_id"]
            
            try:
                # AI分析（30秒超时）
                ai_result = await call_ai_for_tweet_async(
                    text=tweet["text"],
                    author=tweet["author"],
                    introduction=introduction,
                    timeout=30
                )
                
                self.ai_results_cache[tweet_id] = ai_result
                self.record_manager.update_ai_result(
                    tweet_id=tweet_id,
                    success=True,
                    parsed_result=ai_result
                )
                
            except asyncio.TimeoutError:
                # 超时重试逻辑
                retry_count += 1
                if retry_count < 3:
                    # 重新入队
                    await self.ai_queue.put(queue_item)
                else:
                    # 标记失败
                    self.record_manager.update_ai_result(
                        tweet_id=tweet_id,
                        success=False,
                        error="timeout"
                    )
```

---

## 5. 关键设计决策与权衡

### 5.1 异步架构 vs 同步架构

**决策**: 全链路异步实现（async/await）

**理由**:
- **性能**: IO密集型场景（网络请求、API调用）下，异步可大幅提升吞吐量
- **响应性**: 主循环不会被AI调用阻塞，保持10秒固定周期
- **并发性**: 支持多个持仓并行监控，多个推文并发AI分析

**权衡**:
- ❌ 调试复杂度增加（需理解异步执行顺序）
- ❌ 异常处理更复杂（需考虑协程取消）
- ✅ 性能提升显著（实测可支持50+并发任务）

### 5.2 AI队列架构 vs 同步调用

**决策**: 后台队列 + 多Worker并发处理

**理由**:
- **解耦**: AI调用与主循环解耦，互不影响
- **容错**: 超时/失败可重试，不影响后续推文处理
- **资源控制**: 限制并发AI调用数（3个Worker），避免API限流
- **实时性**: 主循环持续运行，不等待AI结果

**权衡**:
- ❌ 实现复杂度增加（需管理队列、缓存、状态）
- ❌ 内存占用增加（缓存未处理推文）
- ✅ 系统稳定性提升（AI故障不会导致系统卡死）

### 5.3 推文记录管理 vs 简单去重

**决策**: 完整的推文记录管理（TweetRecordManager）

**理由**:
- **可追溯性**: 全流程状态记录（AI分析、交易执行）
- **断点续传**: 程序重启后可恢复处理状态
- **审计能力**: 支持事后分析AI准确率、交易效果
- **调试友好**: 可查看每条推文的完整处理链路

**权衡**:
- ❌ 存储开销（每条推文约1KB）
- ❌ 实现复杂度（需维护内存+文件一致性）
- ✅ 运维价值高（可监控、可排查问题）

### 5.4 配置驱动 vs 硬编码

**决策**: 全面配置化（config.py）

**理由**:
- **灵活性**: 无需改代码即可调整策略参数
- **环境适配**: 开发/测试/生产环境切换方便
- **版本控制**: 配置变更可追踪、可回滚

**权衡**:
- ❌ 运行时类型检查不足（dataclass无法覆盖所有场景）
- ✅ 维护成本低（集中管理，避免散落在代码中）

### 5.5 适配器模式 vs 直接依赖

**决策**: 适配器层隔离外部系统

**理由**:
- **可替换性**: 切换交易所（Binance → OKX）只需重写适配器
- **可测试性**: 可Mock适配器，单元测试无需真实API
- **领域纯净**: 核心业务逻辑不受外部API变更影响

**权衡**:
- ❌ 增加一层抽象，开发成本略高
- ✅ 长期维护成本低，扩展性强

---

## 6. 技术栈与依赖

### 6.1 核心语言与运行时
- **Python**: 3.10+（利用dataclass、async/await语法）
- **asyncio**: 异步编程框架

### 6.2 关键依赖库

| 库 | 版本 | 用途 | 替代方案 |
|---|---|---|---|
| **aiohttp** | 3.8+ | 异步HTTP客户端（推特API、交易所API） | httpx |
| **openai** | 1.0+ | Poe API调用（AI分析） | 原生requests |
| **python-dotenv** | 1.0+ | 环境变量管理 | 手动加载 |
| **aiofiles** | 23.0+ | 异步文件操作（可选，目前用同步） | - |

### 6.3 外部服务
- **Twitter API**: twitterapi.io（推文获取）
- **Poe API**: OpenAI兼容接口（AI分析）
- **Binance API**: 合约交易API（下单、查询）

### 6.4 开发工具
- **mypy**: 类型检查
- **black**: 代码格式化
- **isort**: 导入排序

---

## 7. 部署与运行方式

### 7.1 环境要求
- **操作系统**: Windows 10+ / Linux / macOS
- **Python版本**: 3.10+
- **网络**: 可访问外网（或配置代理）

### 7.2 配置准备

1. **安装依赖**:
```bash
pip install aiohttp openai python-dotenv
```

2. **配置文件**:
   - 复制 `.env.example` 到 `.env`
   - 填写以下关键配置：
     ```env
     # AI配置
     POE_API_KEY=your_poe_api_key
     POE_MODEL=your_model_name
     
     # 币安配置
     BINANCE_API_KEY=your_binance_api_key
     BINANCE_API_SECRET=your_binance_secret
     
     # 推特API配置
     TWITTER_API_KEY=your_twitter_api_key
     
     # 代理配置（如需）
     HTTP_PROXY=http://proxy:port
     HTTPS_PROXY=http://proxy:port
     ```

3. **提示词文件**:
   - 确保 `trading_bot/提示词.txt` 存在
   - 包含 `{text1}`, `{text2}`, `{text3}` 占位符

### 7.3 运行方式

#### 7.3.1 开发模式（本地测试）
```bash
# 使用本地JSON文件作为数据源
python -m trading_bot.main
```

**特点**:
- 读取 `trading_bot/twitter_media/*.json`
- 不依赖外部API
- 适合功能验证和调试

#### 7.3.2 生产模式（真实API）
```bash
# 确保 .env 配置正确
python -m trading_bot.main
```

**特点**:
- 调用真实Twitter API
- 实盘交易（注意风险）
- 完整的日志和记录

### 7.4 监控与运维

#### 7.4.1 日志查看
```bash
# 实时查看运行日志
tail -f trading_bot.log

# 查看推文处理记录
cat trading_bot/twitter_media/tweet_records.json
```

#### 7.4.2 关键指标
- **AI处理成功率**: `ai_success` 为 true 的比例
- **交易执行率**: 有 `trade_info` 的记录比例
- **平均响应时间**: 从推文发布到下单的时间
- **风控触发率**: 止损止盈触发次数

#### 7.4.3 异常处理
- **AI调用超时**: 自动重试3次，超过则标记失败
- **交易所API故障**: 异常捕获，记录日志，继续运行
- **网络中断**: 异步重试，不阻塞主循环



## 8. 扩展性设计

**当前实现**: 系统已预留扩展接口，但暂未实现复杂扩展功能。

- **信号源扩展**: 已实现 `SignalSource` 协议，可通过实现该接口添加新的信号源
- **交易所扩展**: 交易所适配器接口已抽象，可支持其他交易所
- **策略扩展**: `ExitStrategy` 接口已定义，可添加新的出场策略

**后续可扩展方向**（根据实际需求逐步实现）：
- 多信号源并行处理
- 多交易所同时运行
- 复合出场策略

---

## 9. 当前局限性

1. **内存持仓**: 持仓信息仅存在于内存，重启后风控任务丢失（后续版本增加持仓持久化）
2. **固定周期**: 10秒轮询，无法动态调整（后续可根据市场活跃度优化）
3. **无回测能力**: 无法基于历史数据验证策略效果（后续版本考虑）

---

## 10. 演进路线

### 10.1 短期优化（v2.1 - v2.2）
- [ ] 持仓持久化（必须功能）
- [ ] CSV读取影响人群（必须功能）
- [ ] 代码结构简化

### 10.2 中期规划（v3.0）
- [ ] 动态策略选择（基于置信度和持续时间）
- [ ] 贝叶斯置信度计算
- [ ] WebSocket触发机制

---

## 10. 附录

### 10.1 术语表

| 术语 | 解释 |
|---|---|
| **KOL** | Key Opinion Leader，意见领袖 |
| **Signal** | 交易信号，包含币种、方向、策略参数 |
| **Position** | 持仓，一笔信号驱动的交易仓位 |
| **RiskManager** | 风控管理器，监控持仓并执行止损止盈 |
| **AI Queue** | AI任务队列，异步处理推文分析 |
| **JSONL** | JSON Lines格式，每行一个JSON对象 |

### 10.2 配置文件示例

```python
# trading_bot/config.py 核心配置结构
@dataclass
class AppConfig:
    ai: AIConfig
    exchange: ExchangeConfig
    risk: RiskConfig
    twitter_api: TwitterAPIConfig
    trading: TradingConfig

@dataclass
class AIConfig:
    poe_api_key: str
    poe_base_url: str
    poe_model: str
    proxy_config: Dict[str, str]

@dataclass
class RiskConfig:
    default_position_pct: float
    default_stop_loss_pct: float
    default_take_profit_scheme: List[Dict[str, float]]
    max_positions: int
```

### 10.3 核心流程时序图

```
时间线: T0 → T10 → T20 → T30 (秒)

T0:  主循环启动 → fetch_latest_tweets()
T2:  推文入队 → ai_queue.put()
T3:  Worker1 开始AI分析
T5:  Worker2 开始AI分析
T7:  Worker3 开始AI分析
T8:  Worker1 AI完成 → 结果存入缓存
T10: 主循环检查缓存 → 发现结果 → 生成Signal → 下单
T12: 下单完成 → 创建Position → RiskManager开始监控
T13: RiskManager: 价格轮询（每秒）
...
T30: 价格触发止盈 → RiskManager执行平仓 → 更新Position
```

---

## 11. 总结

Trading Bot架构采用**清晰的分层设计**、**异步优先的并发模型**、**完善的容错机制**，实现了从社交媒体监控到自动交易的完整闭环。核心优势包括：

1. **解耦**: 各层职责清晰，依赖倒置
2. **容错**: AI失败、网络中断不影响主流程
3. **可观测**: 全流程记录，便于调试和审计
4. **可扩展**: 接口抽象良好，支持快速扩展

该架构支持事件驱动的高频交易场景，适合捕捉市场突发事件，同时通过风控模块保护交易本金。未来可通过插件化、持久化、分布式等演进方向，进一步提升系统性能和可靠性。

---

**文档维护者**: 技术团队  
**最后审查**: 2025-11-22  
**文档版本**: v2.0.0 (基于代码版本v1.4.0+)