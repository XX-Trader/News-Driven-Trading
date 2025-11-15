# News-Driven Trading Bot 需求与架构说明（v0.1.0）

## 1. 文档信息

- **版本号**：v0.1.0
- **日期**：2025-11-14
- **状态**：设计已确认，准备开始实现
- **适用范围**：`News-Driven-Trading` 项目内的实盘自动交易子系统（trading_bot）

---

## 2. 项目概述

### 2.1 项目名称

- **中文**：信号驱动实盘交易系统
- **英文**：News-Driven Trading Bot

### 2.2 项目目标

基于外部消息（例如推特抢跑策略）、行情数据和多个 AI 模型的分析结果，自动生成交易信号，并在**真实交易所（例如 Binance 实盘）**进行下单。  
系统提供统一的风险控制能力（止损、分批止盈）和仓位管理，并预留可扩展的出场策略接口（例如德马克 DeMark、AI 出场策略等），便于后续持续演化。

---

## 3. 使用场景

1. 已有一个“推特抢跑”策略模块（如 `推特抢跑/twitter_crawler_functional_min.py`），可以输出对某个币种的多空信号。
2. 希望将该信号接入到一个统一的“下单+风控引擎”中，实现：
   - 收到信号后，无人工干预，直接在交易所实盘下单。
   - 自动设置止损（默认 1%，可配置/可覆盖）。
   - 按预设分批止盈方案逐步平仓。
   - 仓位按账户资产百分比控制（默认从 USDT 余额计算，可通过信号覆盖）。
3. 未来希望在不改核心交易逻辑的前提下，接入更多：
   - 信号来源（其他社交媒体、新闻数据源等）。
   - AI 模型（多个模型并行分析，选最快可用结果）。
   - 出场策略（德马克、技术指标组合、AI 驱动出场等）。

---

## 4. 功能需求

### 4.1 信号接入层

**目标**：从多个来源异步接收交易信号，统一输出标准结构 `TradeSignal`，供交易执行与风控使用。

#### 4.1.1 信号来源

- **现有来源**：
  - 推特抢跑模块（`推特抢跑/` 目录下的脚本/Notebook）。
- **预留扩展**：
  - 其他社交媒体数据（例如 Telegram、Reddit 等）。
  - 新闻/公告接口。
  - 交易所内部数据（如盘口异动、成交量异常）。
  - 手动注入的测试信号（便于调试）。

#### 4.1.2 信号统一结构（TradeSignal）

初版拟定义字段（最终在 `domain.py` 中实现）：

- `symbol`: 交易对，如 `"BTCUSDT"`。
- `side`: 方向，`"BUY"` / `"SELL"` 或 `"LONG"` / `"SHORT"`。
- `position_pct`（可选）：建议使用的仓位百分比，覆盖全局默认。
- `stop_loss_pct`（可选）：建议的止损幅度，覆盖默认 1%。
- `take_profit_scheme`（可选）：分批止盈配置，覆盖全局默认配置。
- `source_id`（可选）：信号来源 ID，例如 `"twitter_cz"`, `"news_api"`, `"manual"` 等。
- `meta`（可选）：原始数据/调试信息（比如推特链接、推文内容摘要、AI 评分等）。

#### 4.1.3 信号获取方式

- 各信号源实现统一接口（伪代码）：
  - `async def next_signal() -> TradeSignal | None`
- 上层通过一个调度器（如 `SignalDispatcher`）并行地从多个源 `await next_signal()` 或消费异步队列。

---

### 4.2 AI 分析与决策层

**目标**：为原始文本或基础信号提供 AI 增强分析能力，同时具备多模型并行与“取最快可用结果”的能力。

#### 4.2.1 抽象接口

- 定义 `BaseAIModel` 抽象类（如 `ai_base.py` 中）：
  - `async def analyze(self, input: AIInput) -> AIResult`
- `AIInput` 可以是：
  - 原始推文/新闻文本。
  - 基础 `TradeSignal`（缺少置信度、强度等字段）。
- `AIResult` 包括：
  - 置信度、建议方向、风险提示等。

#### 4.2.2 多模型路由

- `AIModelRouter`：
  - 按配置加载多个 `BaseAIModel` 的实现（例如 OpenAI、本地模型、其他云模型）。
  - 并行调用，在指定超时时间内：
    - 谁先返回且结果合法，就使用谁的结果。
    - 超时/失败的模型记录日志但不阻塞整体流程。

#### 4.2.3 MVP 要求

- MVP 只要求：
  - 完整的接口与路由框架。
  - 至少一个简单实现（可以是 dummy / mock，或简单规则），以跑通流程。
- 未来可以无缝接入更多模型，无需修改使用方。

---

### 4.3 网络环境检测与代理管理

**目标**：自动适应当前网络环境。若不能直接访问 Google，则自动启用本地代理 `127.0.0.1:1080`，并确保交易所/API/AI 调用复用统一网络配置。

#### 4.3.1 Google 连通性检测

- 提供异步函数（例如 [`network/check_google_connectivity()`](trading_bot/network.py:1)）：
  - 尝试访问 `https://www.google.com` 或 `https://www.gstatic.com/generate_204`。
  - 在配置的超时时间内成功返回，则认为可以直连 Google。
  - 失败则认为需要使用代理。

> 说明：URL 与超时时间为可配置常量，代码中若有硬编码会在注释+文档中标出，并提供迁移到配置的方案。

#### 4.3.2 代理配置策略

- 在 `config.py` 中支持以下字段：
  - `USE_PROXY_BY_DEFAULT`：是否默认启用代理。
  - `PROXY_URL`：默认 `http://127.0.0.1:1080`。
  - `GOOGLE_CHECK_ENABLED`：是否在启动时进行 Google 检测。
- 策略：
  - 若 `GOOGLE_CHECK_ENABLED = True`：
    - 先进行 Google 检测。
    - 若可访问 Google，则优先使用直连（可再加一项 `FORCE_PROXY` 让用户强制走代理）。
    - 若不可访问，则自动使用 `PROXY_URL`。
  - 若 `GOOGLE_CHECK_ENABLED = False`：
    - 根据 `USE_PROXY_BY_DEFAULT` 和 `FORCE_PROXY` 决定是否走代理。

#### 4.3.3 统一 HTTP Client

- 提供统一的 `create_http_client(config)` 或 `get_http_session()`：
  - 内部根据上述代理策略配置 `aiohttp.ClientSession`（或其他 HTTP 客户端）的 `proxy`/`proxy_auth` 等参数。
  - 要求：交易所 API、AI 模型 API、消息源抓取全部使用该客户端，避免各模块自行处理代理。

---

### 4.4 实盘交易执行层

**目标**：在真实交易所（优先考虑 Binance 实盘）执行真实订单，支持市价单、余额查询、基础行情查询等。

#### 4.4.1 交易所配置

在 `config.py` 中管理：

- `EXCHANGE_NAME`：例如 `"binance"`.
- `BINANCE_API_KEY_ENV` / `BINANCE_API_SECRET_ENV`：
  - 指示从哪个环境变量读取 API key/secret。
- `BINANCE_BASE_URL`：
  - 实盘 REST API base URL。
- `BINANCE_RECV_WINDOW`、`BINANCE_TIMEOUT` 等基础参数。
- 可选：`USE_TESTNET`（尽管当前需求是实盘，也建议保留）。

#### 4.4.2 下单流程

给定一个 `TradeSignal`，交易执行层负责：

1. 获取账户余额：
   - 默认使用 USDT（或配置中指定的基础资产）。
   - 使用异步接口 `get_balance(asset) -> float`。
2. 计算下单数量：
   - 取可用余额 * `position_pct`（信号级 > 全局默认）。
   - 除以当前市价 ≈ 数量。
   - 按交易所最小下单量、精度要求进行调整（向下取整）。
3. 发送市价单：
   - 调用 `place_market_order(symbol, side, quantity) -> OrderInfo`。
   - 检查返回结果（订单 ID、成交信息等），失败则记录日志并返回错误状态。
4. 记录订单和持仓信息：
   - 保存到内存模型 `Position` / `Order` 对象中，交给风控模块监控。

> MVP 阶段可以先用轮询行情接口 `get_latest_price(symbol)` 来驱动风控；后续可升级为 WebSocket 行情订阅。

#### 4.4.3 安全性与 DRY_RUN 开关

- 即便当前需求是“直接实盘下单”，仍建议在 `config` 中保留：
  - `DRY_RUN`（默认可设为 `False`），用于：
    - 调试阶段设为 `True`：只打印/记录拟下单信息，但不真正调用交易所 API。
    - 正式阶段设为 `False`：真正实盘下单。
- 文档中需明确提醒：
  - 使用前务必确认 `DRY_RUN` 状态及 API key 权限。

---

### 4.5 风控与仓位管理（止损、分批止盈、出场策略接口）

**目标**：在持仓生命周期内自动管理止损与分批止盈，并提供可插拔的出场策略接口，以支持后续复杂策略（如德马克）。

#### 4.5.1 默认止损

- 全局默认止损比例（例如 1%）：
  - `DEFAULT_STOP_LOSS_PCT = 0.01`（在配置中维护）。
- 信号可以提供自定义 `stop_loss_pct` 覆盖默认。
- 实现方式：
  - 开仓时记录开仓价格。
  - 由监控任务持续获取当前价格。
  - 当浮动亏损比例 ≥ `stop_loss_pct` 时，发起市价平仓指令。

#### 4.5.2 分批止盈

- 全局默认分批止盈方案（示例）：

```json
[
  { "take_profit": 0.02, "size_pct": 0.5 },
  { "take_profit": 0.05, "size_pct": 0.5 }
]
```

- 语义：
  - 当收益达到 +2% 时，平掉 50% 仓位。
  - 当收益达到 +5% 时，平掉剩余 50% 仓位。
- 配置要求：
  - 在 `config` 中以可 JSON/列表形式配置。
  - 信号级别可通过 `take_profit_scheme` 覆盖。
- 实现方式：
  - 对每个持仓按配置生成一个止盈序列。
  - 每个档位触发一次后，标记为已执行，避免重复平仓。

#### 4.5.3 出场策略接口（为德马克等预留）

定义统一接口，例如：

- `class ExitStrategy:`
  - `def __init__(self, position, config, market_data_source): ...`
  - `async def on_price_update(self, latest_price) -> ExitDecision | None`

其中 `ExitDecision` 包含：

- `action`: `"close_all"`, `"close_partial"`, `"do_nothing"` 等。
- `size_pct`: 平仓比例（对于部分平仓）。
- 可选的策略标签/原因说明。

##### 默认实现

- `BasicExitStrategy`：
  - 根据止损和分批止盈配置，在价格更新时决定是否平仓。
  - 逻辑简单透明，方便验证。

##### 未来扩展

- `DeMarkExitStrategy`：
  - 利用德马克指标判断出场时机。
- `AIExitStrategy`：
  - 利用 AI 模型对持仓状态与市场环境实时评估，给出出场信号。

核心要求：**在主业务流程中，通过配置选择 ExitStrategy 实现，而不是在逻辑里写死具体策略**。

#### 4.5.4 RiskManager

- 职责：
  - 为每一笔新开仓位创建风控监控任务。
  - 维护一个任务集合，统一管理生命周期（启动、取消）。
  - 对接行情数据源（轮询 REST 或 WebSocket）。
  - 在每次价格更新时调用对应 `ExitStrategy` 进行决策，并执行平仓。

---

### 4.6 异步任务管理与应用编排

**目标**：基于 `asyncio` 构建一个清晰的事件驱动架构，支持多信号源、多持仓并行管理。

#### 4.6.1 主流程（概览）

1. 启动阶段：
   - 加载配置。
   - 初始化网络与代理管理。
   - 初始化交易所适配器、AI 模型路由、信号源、风控管理器。
2. 运行阶段（循环）：
   - 从一个或多个信号源异步获取 `TradeSignal`。
   - （可选）调用 AI 模型进一步分析/过滤信号。
   - 基于信号生成下单请求，调用交易所适配器执行市价单。
   - 创建对应 `Position` 对象，并交由 `RiskManager` 启动监控任务。
3. 关闭阶段：
   - 停止接收新信号。
   - 优雅地取消所有监控任务（或等待它们自然结束）。
   - 关闭网络客户端等资源。

#### 4.6.2 app_runner

- 提供接口：
  - `async def start_trading_app()`：用于 CLI 或 Notebook 启动。
  - `async def stop_trading_app()`：用于优雅收尾。

---

## 5. 配置与可适配性

### 5.1 配置来源

- 统一通过 `trading_bot/config.py` 管理。
- 主要配置来源：
  - 环境变量（如 API key、secret 等敏感信息）。
  - 代码内默认配置常量（可将来迁移到 `.env` 或 YAML/JSON）。

### 5.2 关键配置项（示意）

- 网络/代理相关：
  - `GOOGLE_CHECK_ENABLED`
  - `FORCE_PROXY`
  - `USE_PROXY_BY_DEFAULT`
  - `PROXY_URL`
- 交易所相关：
  - `EXCHANGE_NAME`
  - `BINANCE_API_KEY_ENV`
  - `BINANCE_API_SECRET_ENV`
  - `BINANCE_BASE_URL`
  - `USE_TESTNET`
  - `DRY_RUN`
- 风控相关：
  - `DEFAULT_STOP_LOSS_PCT`
  - `DEFAULT_TAKE_PROFIT_SCHEME`
  - `DEFAULT_POSITION_PCT`
  - `EXIT_STRATEGY_TYPE`（如 `"basic"`, `"demark"`, `"ai"`）
- AI 相关：
  - 可用模型列表及参数。
  - 并行超时时间。

---

## 6. 日志与监控（MVP）

- 使用 Python 标准 `logging` 模块。
- 最少需要记录：
  - 收到的每个 `TradeSignal`。
  - AI 分析调用与结果（若启用）。
  - 每次下单请求 & 响应（包括错误信息）。
  - 止损/止盈触发细节（触发价格、收益率、平仓数量、使用策略）。
- 日志输出目标：
  - MVP 阶段：控制台输出。
  - 后续可选：文件或结构化日志（JSON）。

---

## 7. 目录与模块规划（v0.1.0）

在当前仓库基础上，规划新增结构如下（实际文件后续逐步实现）：

```text
News-Driven-Trading/
├── binance.py                        # 已有脚本，可作为接口参考或迁移
├── 推特抢跑/
│   ├── twitter_crawler_functional_min.py
│   ├── twitter_analysis.ipynb
│   ├── 需求确认.md
│   └── TRADE_SYSTEM_REQUIREMENTS.md  # 本文档
├── trading_bot/
│   ├── __init__.py
│   ├── config.py                     # 全局配置与加载逻辑
│   ├── network.py                    # Google 检测 + 统一 HTTP 客户端（含代理）
│   ├── exchange_binance_async.py     # Binance 异步实盘适配
│   ├── ai_base.py                    # AI 抽象接口与多模型路由
│   ├── signals.py                    # 信号源抽象 + 推特信号适配
│   ├── domain.py                     # 核心领域模型与下单数量计算等逻辑
│   ├── risk_exit.py                  # 止损/分批止盈 + ExitStrategy 接口与默认实现
│   └── app_runner.py                 # 应用编排与主异步流程
├── main.py                           # CLI 入口，启动 trading_bot.app_runner
└── CLAUDE.md                         # 架构与版本变更记录（单独维护）
```

> 注意：为避免文件过多导致维护困难，当前版本保持在 8~9 个 py 文件的级别，兼顾清晰分层与可维护性。  
> 未来若有需要，可进一步合并或拆分模块，但需在 `CLAUDE.md` 中记录变更原因。

---

## 8. 风险与注意事项

1. **实盘交易风险**
   - 默认行为需在文档中明确说明：
     - 是否开启 `DRY_RUN`。
     - 使用何种 API key 权限（建议关闭提现、划转等高风险权限）。
   - 初期建议：
     - 在代码中增加明显日志提示当前为 DRY_RUN/实盘模式。

2. **网络与代理**
   - 若 Google 检测逻辑出现误判，可能导致不必要的代理配置或访问失败。
   - 建议：
     - 在配置中保留手动覆盖选项（如 `FORCE_PROXY`）。
     - 在日志中记录当前网络模式（直连/代理）。

3. **API 限频**
   - 行情轮询过于频繁可能触发交易所的限频。
   - 需在实现时控制调用频率（如每秒一次或根据配置调整）。

4. **出场策略复杂度**
   - 未来接入德马克或复杂 AI 出场策略时，可能带来计算与依赖复杂度。
   - 应坚持：
     - 策略实现与主流程解耦。
     - 通过配置切换不同策略。

---

## 9. 版本规划（简要）

- **v0.1.0（当前）**
  - 明确需求与架构。
  - 创建基础目录与模块骨架。
  - 实现：
    - 配置系统。
    - 网络检测与代理管理。
    - Binance 异步实盘适配（最小可用：余额/市价单/价格）。
    - 简单 `TradeSignal` 模型与信号接入接口。
    - `BasicExitStrategy`：止损 + 分批止盈。
    - 主异步流程与 CLI 入口。
  - 更新 `CLAUDE.md` 记录设计。

- **后续版本（示意）**
  - v0.2.x：接入一个真实 AI 模型 & 多模型路由。
  - v0.3.x：增加德马克等高级出场策略。
  - v0.4.x：接入更多信号源、增加监控与告警能力。

---

## 10. 本次实现的 DoD（完成定义）

- 代码实现满足本文件描述的 v0.1.0 范围。
- 可以在 **受控环境** 下，从一个真实或 mock 信号源开始：
  - 自动完成：信号接收 → 实盘下单（或 DRY_RUN）→ 止损/分批止盈监控 → 平仓。
- 配置均通过 `config.py` 管理，关键参数可通过修改配置而不需要改业务逻辑。
- `TRADE_SYSTEM_REQUIREMENTS.md` 与 `CLAUDE.md` 内容与代码保持一致，并在每次重要修改后更新版本和说明。