# 缺失功能与后续规划 (v1.4.0+)

本文档详细列出了 `News-Driven-Trading` 项目当前版本 (v1.4.0) 尚未实现的功能，以及对应的规划版本和实现建议。

## 1. 真实的 Twitter API 接入 (v1.1.0)

**现状**：
- `twitter_source.py` 中的 `fetch_latest_tweets_from_api` 仅为骨架，实际逻辑是降级调用本地 JSON 文件。
- 无法获取实时推特数据。

**缺失内容**：
- 基于 `aiohttp` 的真实 HTTP 请求逻辑。
- 对接 `twitterapi.io` 或官方 API 的鉴权与数据解析。
- API 限流处理与错误重试。

**实现建议**：
- 在 `twitter_source.py` 中完善 `_fetch_for_user_async`。
- 使用 `config.twitter_api` 中的 `api_key` 和 `base_url`。
- 确保返回的数据结构与本地 JSON 格式一致，以复用后续处理逻辑。

## 2. 动态触发框架 (v1.5.0)

**现状**：
- 系统采用固定间隔（默认 10 秒）轮询推特数据。
- 无论市场是否活跃，查询频率固定，可能造成 API 资源浪费或错过剧烈波动。

**缺失内容**：
- K 线数据监控模块（监听成交量异动）。
- 动态调整查询频率的逻辑（例如：异动时每 5 秒查一次，持续 10 分钟）。
- 动态切换关注列表（例如：ETH 异动时重点查 Vitalik，DOGE 异动时重点查 Musk）。

**实现建议**：
- 在 `app_runner.py` 中引入 `MarketMonitor`。
- 实现 `TwitterTrigger` 类来管理查询窗口和频率。

## 3. 置信度过滤 (v2.0.0)

**现状**：
- AI 分析出的所有信号（只要能提取出 symbol）都会生成 `TradeSignal` 并执行下单。
- 即使 AI 认为置信度很低（例如 "可能相关"），也会触发交易。

**缺失内容**：
- `TradeSignal` 中的 `confidence` 字段过滤逻辑。
- 可配置的置信度阈值（例如 `confidence > 75` 才下单）。

**实现建议**：
- 在 `config.py` 中添加 `confidence_threshold` 配置。
- 在 `app_runner.py` 的 `_consume_signals_and_trade` 中添加过滤判断。

## 4. 高级风控与订单管理 (v2.0.0+)

**现状**：
- `RiskManager` 仅实现了基础的持仓监控（止损 + 分批止盈）。
- 下单仅支持市价单 (`MARKET`)。

**缺失内容**：
- **资金管理**：最大持仓限制、每日最大亏损限额、杠杆动态调整。
- **订单类型**：限价单 (`LIMIT`)、追踪止损 (`TRAILING_STOP_MARKET`)。
- **持仓聚合**：同一币种多次信号的加仓逻辑（目前是独立 Position）。

**实现建议**：
- 扩展 `RiskConfig` 和 `RiskManager`。
- 在 `exchange_binance_async.py` 中添加更多订单类型的支持。

## 5. 动态用户映射表 (v1.x)

**现状**：
- `config.py` 中硬编码了 10 个影响力人物及其简介。
- 添加或修改关注对象需要修改代码。

**缺失内容**：
- 从外部文件（CSV / JSON）加载用户列表和简介。
- 支持热更新（不重启程序更新关注列表）。

**实现建议**：
- 在 `config.py` 的 `load_config` 中增加读取外部文件的逻辑。
- 优先读取 `user_mapping.json`，不存在则使用默认硬编码列表。

---

**总结**：
当前 v1.4.0 版本是一个**功能完备的 MVP (Minimum Viable Product)**，跑通了"数据读取 -> AI 分析 -> 模拟下单 -> 基础风控"的全链路。后续版本将侧重于**真实数据接入**、**智能化运行**和**精细化交易**。