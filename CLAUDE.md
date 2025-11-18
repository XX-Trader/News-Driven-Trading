# News-Driven-Trading 完整实现文档

## 版本信息
- **版本号**：v1.3.3
- **日期**：2025-11-17 北京时间
- **更新内容**：
  - ✨ 代码架构清理（删除冗余代码，统一数据源管理）
  - ✅ 删除 ProcessedIdStore 类（统一使用全局 processed_ids 管理）
  - ✅ 删除同步 AI 调用（保持异步架构一致性）
  - ✅ 删除占位实现和孤立代码（简化网络模块）
  - ✅ 修复引用错误（call_ai_for_tweet_async 直接调用核心函数）

---

## 项目概述

**目标**：构建一个**定时执行的推特驱动交易机器人**，周期性地：
1. 从推特 API（或本地 JSON 测试数据）获取最新推文
2. 用 AI（Poe OpenAI 兼容）分析推文内容，提取交易币种、方向、置信度
3. 生成交易信号并下单（FakeExchange 或 Binance 实盘）
4. 每 10 秒循环执行一次

**核心创新**：
- 推特数据源**抽象化**，支持从本地 JSON 文件、真实 Twitter API、自定义数据接口等多种来源读取
- AI 分析与下单逻辑**解耦**，便于后续灵活替换 AI 模型或下单策略
- 配置**集中管理**，所有 API Key、参数从 `config.py` 读取

---

## 详细需求与范围

### 需求背景
- Notebook `推特抢跑/twitter_analysis one.ipynb` 里已有完整的推特爬虫、AI 分析、K 线展示逻辑
- 当前框架 `trading_bot/app_runner.py` 有信号源、下单的架构，但缺少推特爬虫与 AI 分析的真实实现
- 目标：**在保持现有框架不变的前提下，集成 notebook 的核心函数，实现可运行的完整链路**

### 核心模块分工

| 模块 | 职责 | 数据流 |
|------|------|--------|
| **twitter_source.py** | 推特数据源（适配层） | 外部数据 → JSON 格式 |
| **tweet_analyzer.py** | AI 分析 + 信号提取 | 推文文本 → {symbol, direction, confidence} |
| **app_runner.py** | 信号消费 + 下单编排 | TradeSignal → 下单请求 |
| **config.py** | 配置管理 | （无数据流，纯配置） |

### 数据源抽象设计（可复用）

**推特数据源需要支持多种来源**：

```python
# 1. 本地 JSON 文件模式（当前测试用）
async def fetch_latest_tweets_from_local_json():
    """从 推特抢跑/twitter_media/ 读取 JSON 文件列表"""
    # 读取文件目录 → 合并成推文列表 → 返回

# 2. 真实 Twitter API 模式（后续接入）
async def fetch_latest_tweets_from_twitter_api():
    """调用 twitterapi.io 或官方 API 获取推文"""
    # HTTP 请求 → 解析响应 → 返回

# 3. 自定义数据接口（未来扩展）
async def fetch_latest_tweets_from_custom_source():
    """用户自定义的推文获取逻辑"""
    pass
```

**当前 MVP 只实现本地 JSON 模式，但代码结构支持后续无缝切换。**

### AI 分析函数签名
```python
def call_ai_for_tweet(text: str, author: str, introduction: str) -> Dict[str, Any]:
    """
    从 notebook 迁移的函数。
    返回格式（由 Poe API 决定，遵循提示词 提示词.txt）：
    {
        "交易币种": "BTC" | ["BTC", "ETH"],
        "交易方向": "做多" | "做空",
        "消息置信度": 0-100 (百分比数字),
        ...其他字段
    }
    """
```

### 下单流程

```
TradeSignal（来自 AI 分析）
  ↓
_consume_signals_and_trade()
  ├─ 解析 signal 的 symbol, side（从 AI direction 转换）
  ├─ 获取账户余额 & 当前价格
  ├─ 计算下单量（基于 RiskConfig.default_position_pct）
  ├─ 调用 exchange_client.place_market_order()
  └─ 记录订单结果
```

---

## 架构设计

### 时序图
```
main.py
  └─ asyncio.run(start_trading_app())
       └─ build_trading_app_context() [初始化]
             ├─ load_config()
             ├─ AIModelRouter(config.ai)
             ├─ BinanceAsyncClient(config)
             └─ TwitterCrawlerSignalSource(
                   fetch_func=fetch_latest_tweets,
                   tweet_conf={poll_interval_sec=10}
                 )
       
       └─ _consume_signals_and_trade(app)
             ├─ while True:
             │   ├─ async for signal in signal_source.stream(): [每 10 秒]
             │   │   ├─ fetch_latest_tweets() [从本地/API 读推文]
             │   │   ├─ call_ai_for_tweet(text, author, intro) [Poe API]
             │   │   ├─ detect_trade_symbol(ai_result) [提取币种]
             │   │   ├─ TradeSignal(symbol, side, ...) [构造信号]
             │   │   └─ place_market_order() [下单]
             │   └─ await asyncio.sleep(10)
```

### 文件结构

```
trading_bot/
├── main.py                    (入口，已有)
├── app_runner.py              (信号消费与下单，改进)
├── config.py                  (配置，已有 + 新增 user_intro_mapping)
├── twitter_source.py          (推特数据源，改进为本地 JSON 扫描)
├── tweet_analyzer.py          (新建：AI 分析函数，从 notebook 迁移)
├── domain.py                  (数据结构，已有)
├── exchange_binance_async.py  (Binance 客户端，已有)
├── ai_base.py                 (AI 路由，已有)
├── signals.py                 (信号源接口，已有)
└── ...其他

推特抢跑/
├── twitter_analysis one.ipynb (原始 notebook，保留)
├── 提示词.txt                 (AI 系统提示词，已有)
└── twitter_media/             (推文 JSON 文件目录)
    ├── 1984992347395141987.json
    ├── 1987990314997739625.json
    └── processed_ids.json      (已处理推文 ID 列表)

CLAUDE.md                       (本文档，新建)
```

---

## 代码改动清单（v1.0.0 已完成）

### 1. ✅ 改进：`trading_bot/twitter_source.py`
**推特数据源扩展 - 支持 API + 本地 JSON 双模式**

```python
# 新增异步函数：
async def fetch_latest_tweets_from_api() -> List[Dict[str, Any]]:
    """从 twitterapi.io API 获取推文（当前为骨架，自动降级到本地 JSON）"""
    try:
        config = load_config()
        print("[twitter_source] API mode: would call twitterapi.io")
        return fetch_latest_tweets_from_local_json()
    except Exception as e:
        print(f"[twitter_source] API fetch failed: {e}, falling back to local JSON")
        return fetch_latest_tweets_from_local_json()

# 改进统一入口：
async def fetch_latest_tweets() -> List[Dict[str, Any]]:
    """优先尝试 API，失败则自动降级到本地 JSON"""
    return await fetch_latest_tweets_from_api()
```

**关键特性**：
- ✨ 推特 API 骨架（twitterapi.io，当前返回本地 JSON）
- ✨ 自动降级机制（API 失败 → 本地 JSON）
- ✨ 后续补充真实 HTTP 调用无需改其他代码

---

### 2. ✅ 改进：`trading_bot/config.py`
**用户映射表扩展 - 从 4 人到 10 人**

```python
# 扩展 TwitterAPIConfig.user_intro_mapping：
user_intro_mapping: Dict[str, str] = field(
    default_factory=lambda: {
        "cz_binance": "BINANCE创始人，全球最大加密货币交易所龙头",
        "haydenzadams": "Uniswap协议发明者，DeFi 先驱",
        "elonmusk": "特斯拉 CEO，加密货币爱好者",
        "VitalikButerin": "以太坊创始人，区块链技术核心架构师",
        "justinsuntron": "波场 TRON 创始人，区块链企业家",
        "SBF_FTX": "FTX交易所创始人，加密衍生品领域专家",
        "aantonop": "比特币倡导者，技术教育家",
        "DocumentingBTC": "比特币文化与历史研究者",
        "APompliano": "加密投资专家，市场分析师",
        "CryptoByzantine": "区块链安全与共识机制研究者",
    }
)
```

**关键改进**：
- ✨ 硬编码 10 个影响力人物
- ✨ 为 AI 分析提供用户背景信息
- ✨ 后续可改为读取 CSV/JSON 文件

---

### 3. ✅ 改进：`trading_bot/app_runner.py`（核心改动）
**风控集成 + 多持仓并发监控 + 详细日志**

```python
# 核心改动1：RiskManager 初始化与 Position 注册
risk_manager = RiskManager(config.risk)
position = Position(
    position_id=f"pos_{signal.symbol}_{int(time.time())}",
    symbol=signal.symbol,
    side=signal.side,
    entry_price=entry_price,
    quantity=quantity,
)
risk_manager.register_position(position)

# 核心改动2：启动独立的异步风控监控任务
monitor_task = asyncio.create_task(
    monitor_position_with_risk_manager(
        position, risk_manager,
        price_fetcher, close_executor
    )
)
monitor_tasks[position.position_id] = monitor_task

# 核心改动3：价格获取回调
async def price_fetcher() -> float:
    """获取实时价格"""
    price = await exchange_client.get_latest_price(signal.symbol)
    print(f"[PRICE_FETCH] {signal.symbol}: {price}")
    return price

# 核心改动4：平仓执行回调
async def close_executor(qty: float, reason: str):
    """执行实际平仓"""
    close_side = "SELL" if signal.side == "BUY" else "BUY"
    resp = await exchange_client.place_future_market_order(
        symbol=signal.symbol,
        side=close_side,
        quantity=qty
    )
    print(f"[EXIT] {reason}: closing {qty} of {signal.symbol}")
    return resp
```

**关键特性**：
- ✨ 每个信号创建独立的 Position + 监控任务
- ✨ 后台 asyncio 任务每 1 秒检查止损止盈
- ✨ 止损 1% 全平 + 分批止盈（+2% 平 50% + +5% 平 50%）
- ✨ 标准化日志：[SIGNAL]、[ORDER]、[EXIT]、[RISK_MANAGER]、[PRICE_FETCH]

---

### 4. ✅ 改进：`trading_bot/CLAUDE.md`
**项目文档升级 v1.0.0**

- ✨ 版本号：v0.2.0 → v1.0.0
- ✨ 新增特性章节（RiskManager 集成、多持仓监控等）
- ✨ 更新已知限制（API 骨架、AI 延迟、风控粒度等）
- ✨ 后续演进路线（v1.1.0 ~ v2.0.0）

---

### 5. ✅ 新建：`IMPLEMENTATION_v1.0.0.md`
**实现总结与验证指南**

- 核心改动清单（4 个文件）
- 关键参数配置
- 后续优化方向

---

### 6. ✅ 改进：`trading_bot/` 代码架构清理（v1.3.3）
**删除冗余代码，统一架构，消除技术债务**

#### 6.1 ✅ 统一 processed_ids 管理
**改动前**：
```python
# app_runner.py - ProcessedIdStore 类（本地存储）
class ProcessedIdStore:
    def __init__(self, path: Path):
        self.path = path
        self._cache: Set[str] = set()
    
    def has(self, tweet_id: str) -> bool:
        return tweet_id in self._cache
    
    def add_many(self, ids: List[str]) -> None:
        # ... 实现 ...
```

**改动后**：
```python
# 删除 ProcessedIdStore 类，统一使用 twitter_source 全局函数
from twitter_source import load_processed_ids, mark_as_processed

# 使用全局函数替代
if tweet_id in load_processed_ids():
    continue
```

**收益**：
- ✅ 单一数据源，消除不一致风险
- ✅ 简化代码，减少约40行
- ✅ 职责清晰：`twitter_source` 负责数据层

#### 6.2 ✅ 删除同步AI调用遗留
**改动前**：
```python
def _to_trade_signal(self, tweet: RawTweet, ai_result: Optional[Any]) -> Optional[TradeSignal]:
    if ai_result is None:
        # 尝试同步 AI 调用（阻塞风险）
        try:
            ai_result = call_ai_for_tweet(text=text, author=user_name, introduction="unknown author")
        except Exception as e:
            print(f"[_to_trade_signal] sync AI error: {e}")
            return None
```

**改动后**：
```python
def _to_trade_signal(self, tweet: RawTweet, ai_result: Optional[Any]) -> Optional[TradeSignal]:
    # ai_result 为 None 时直接返回 None（AI 分析在后台 worker 完成）
    if ai_result is None:
        return None
```

**收益**：
- ✅ 遵循异步架构原则
- ✅ 主循环不阻塞，保持 10 秒周期
- ✅ 职责清晰：AI 分析只在后台 worker 中进行

#### 6.3 ✅ 修复引用错误
**改动前**：
```python
async def call_ai_for_tweet_async(...):
    # 错误引用已删除的函数
    result = await asyncio.wait_for(
        loop.run_in_executor(None, call_ai_for_tweet, text, author, introduction),
        timeout=timeout
    )
```

**改动后**：
```python
async def call_ai_for_tweet_async(...):
    # 直接调用核心 AI 函数
    raw_result = await asyncio.wait_for(
        loop.run_in_executor(None, ai_analyze_text, text, author, introduction),
        timeout=timeout
    )
    
    # 尝试解析 AI 返回的 JSON 结果
    try:
        import json
        return json.loads(raw_result)
    except json.JSONDecodeError:
        return {"raw": raw_result}
```

**收益**：
- ✅ 修复引用错误
- ✅ 直接调用核心函数，减少中间层
- ✅ 添加 JSON 解析容错处理

#### 6.4 ✅ 删除占位实现和孤立代码
- ✅ 删除 `network.py` 中的 `check_google_connectivity()` 占位实现
- ✅ 删除 `app_runner.py` 中的 `_save_raw_batch()` 方法
- ✅ 删除 `twitter_source.py` 末尾孤立代码行
- ✅ 删除 `tweet_analyzer.py` 中的同步版本 `call_ai_for_tweet()`

**收益**：
- ✅ 消除功能重复
- ✅ 简化网络模块逻辑
- ✅ 减少维护成本

---

## 环境 & 版本

### 依赖
- Python 3.8+
- `aiohttp` (异步 HTTP 客户端)
- `requests` (同步 HTTP，用于 Binance K 线)
- `openai` (Poe API 兼容的 OpenAI 客户端)
- `httpx` (可选，用于代理支持)

### API Key 配置
所有 API Key 已存储在 `config.py` 中：
- `AIConfig.poe_api_key` → Poe (OpenAI 兼容)
- `AIConfig.poe_base_url` → https://api.poe.com/v1
- `ExchangeConfig.api_key_env` & `api_secret_env` → Binance

### 运行方式

```bash
# 1. 确保依赖已安装
pip install aiohttp requests openai httpx

# 2. 启动交易机器人
python trading_bot/main.py

# 3. 日志输出示例
# [trading_app] started. Press Ctrl+C to stop.
# [TwitterCrawlerSignalSource] fetch_latest_tweets: 2 tweets fetched
# [TwitterCrawlerSignalSource] AI analyze success for tweet_id=xxx
# [trade] placing order: symbol=BTCUSDT, side=BUY, qty=0.001
# [trade] order_resp={...}
```

---

## 关键设计决策

### 1️⃣ 为什么抽象推特数据源？
- **现状**：当前 `twitter_source.py` 返回硬编码假数据
- **目标**：支持从本地 JSON、真实 API、自定义接口读数据
- **方案**：`fetch_latest_tweets()` 作为唯一的数据入口，替换实现无需改其他代码
- **收益**：测试用本地 JSON，线上用真实 API，一套代码两种用途

### 2️⃣ RiskManager 集成设计
- **v1.0.0 改进**：完整集成 RiskManager 风控模块
- **设计**：每个 TradeSignal 创建一个 Position，注册到 RiskManager 进行并发监控
- **功能**：
  - 止损：浮动亏损超过 `stop_loss_pct`（默认 1%）时全部平仓
  - 分批止盈：达到 +2% 时平 50%，+5% 时平剩余 50%
- **后台监控**：独立 asyncio task 每秒检查一次，触发条件时自动调用 `close_executor()`

### 3️⃣ 为什么用用户简介映射表？
- **问题**：Notebook AI 分析需要用户简介（如 "BINANCE 的创始人"），但推特 API 数据里没有
- **方案**：在 `config.py` 维护 `user_intro_mapping` 字典
- **优势**：
  - 集中管理，易于扩展（添加新用户只需改配置）
  - AI 分析结果更准确（有上下文信息）
  - 后续可从数据库动态加载

### 4️⃣ 为什么 poll_interval 改为 10 秒？
- **用户需求**：每 10 秒执行一次推特爬虫 → AI 分析 → 下单
- **权衡**：
  - 太快（1-2 秒）：API 压力大，容易触发限流
  - 太慢（30+ 秒）：反应速度慢，容易错过交易机会
  - 10 秒：平衡点，既能及时响应，又不过度消耗资源

---

## 注意事项 & 限制

### ⚠️ v1.3.3 已知限制

1. **推特 API 骨架**
   - 当前 `fetch_latest_tweets_from_api()` 为骨架，自动降级到本地 JSON
   - 实际使用需补充真实 HTTP 请求逻辑（aiohttp + twitterapi.io）
   - 建议：参考 config 中的 `TwitterAPIConfig.user_last_tweets_url` 补充 API 调用

2. **AI 分析延迟**
   - Poe API 响应时间约 2-5 秒，可能导致实际循环周期 > 10 秒
   - ✅ 已异步化 AI 调用（v1.2.0），不阻塞主循环

3. **风控监控粒度**
   - 当前风控检查间隔为 1 秒，可根据需要调整 `poll_interval_sec`
   - 止损止盈逻辑基于收益率（pnl_ratio），暂不支持价位锁定

4. **多持仓并发管理**
   - 支持为每个信号创建独立的 Position + 监控任务
   - 当前未实现持仓聚合与风险限额检查，后续可补充

5. **下单风险**
   - 当前无置信度过滤，所有 AI 信号都会下单
   - 建议：添加 `confidence_threshold` 配置，低于阈值忽略
   - **强烈建议**：先用 `dry_run=True` 模拟测试，确认逻辑无误后再开启真实下单

6. **用户映射表**
   - 当前硬编码 10 个人物，后续可读取 CSV/JSON 文件扩展

7. **架构清理完成**
   - ✅ 已删除冗余代码（ProcessedIdStore、同步AI调用、占位实现）
   - ✅ 统一数据源管理（单一 processed_ids 全局函数）
   - ✅ 修复引用错误（call_ai_for_tweet_async 直接调用核心函数）

### ✅ v1.3.3 新增特性

- ✅ 代码架构清理（删除冗余代码，统一数据源管理）
- ✅ 统一 processed_ids 管理（消除数据不一致风险）
- ✅ 保持异步架构一致性（主循环不阻塞）
- ✅ 简化网络模块（删除占位实现）
- ✅ 修复引用错误（直接调用核心函数）
- ✅ 减少维护成本（消除功能重复）

### ✅ 历史版本特性

- ✅ v1.0.0：推特 API 数据源抽象层、RiskManager 完整集成、详细日志系统
- ✅ v1.2.0：异步化 AI 调用（后台队列 + 超时控制）
- ✅ v1.3.0：推特 API 并发抓取 + processed_ids 缓存
- ✅ v1.3.1：JSONL 日志 + 两套版本函数 + v1.4.0 框架设计
- ✅ v1.3.2：清理旧代码架构（删除 `_load_twitter_fetch_func`）

---

## 后续演进路线

| 版本 | 目标 | 优先级 |
|------|------|--------|
| **v0.2.0** | MVP：本地 JSON + AI 分析 + 下单基础链路 | ✅ 已完成 |
| **v1.0.0** | 风控集成 + API 骨架 + 详细日志 + 多持仓监控 | ✅ 已完成 |
| **v1.1.0** | 补充真实 Twitter API 实现 | 高 |
| **v1.2.0** | 异步化 AI 调用（后台队列 + 超时控制） | ✅ 已完成 |
| **v1.3.0** | 推特 API 并发抓取 + processed_ids 缓存 | ✅ 已完成 |
| **v1.3.1** | JSONL 日志 + 两套版本函数 + v1.4.0 框架设计 | ✅ 已完成 |
| **v1.3.2** | 清理旧代码架构（删除 `_load_twitter_fetch_func`） | ✅ 已完成 |
| **v1.3.3 (当前)** | 代码架构清理（删除冗余代码，统一数据源管理） | ✅ 已完成 |
| **v1.4.0** | 动态触发框架（K线信号动态触发 + 10分钟窗口 + 5秒间隔） | 中 |
| **v2.0.0** | 置信度过滤 + 持仓聚合 + 风险限额 + 多策略 | 低 |

---

## 开发流程与验证

### 验证清单
- [ ] 本地 JSON 推文能正常读取（含 processed_ids 去重）
- [ ] AI 分析函数成功调用，返回结构正确
- [ ] TradeSignal 正确提取 symbol、direction、confidence
- [ ] FakeExchange 下单日志打印完整
- [ ] 10 秒循环正常运行，无崩溃
- [ ] 对接 Binance 真实下单（dry_run=True 先验证）

### 调试建议
```python
# 在 app_runner.py 里增加以下日志便于调试：
print(f"[DEBUG] Raw tweet: {tweet}")
print(f"[DEBUG] AI result: {ai_result}")
print(f"[DEBUG] Extracted symbol: {symbol}, direction: {direction}, confidence: {confidence}")
print(f"[DEBUG] Final TradeSignal: {signal}")
```

---

## 文档维护

- **版本更新**：每次重要改动更新版本号、日期、更新内容
- **架构变更**：同步更新流程图、文件结构、模块职责
- **新增依赖**：及时添加到"环境 & 版本"章节
- **限制与风险**：定期审视，及时补充

---

**最后修订**：2025-11-17 by AI Assistant (v1.3.3 代码架构清理)
**项目负责人**：用户
**预期交付**：完成 MVP 实现，通过验证清单
