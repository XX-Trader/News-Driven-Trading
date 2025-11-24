# IMPLEMENTATION_v1.3.0.md

**版本**：v1.3.1（JSONL 日志存储版）
**更新时间**：2025-11-17 09:01 (UTC+8)
**改进范围**：推特 API 数据源优化 - 并发多用户抓取 + processed_ids 缓存去重 + JSONL 推文日志

---

## 概述

v1.3.1 实现了推特数据源层的完整优化：
- ✅ **并发多用户 API 抓取**：基于 aiohttp，异步抓取 10 个目标用户的推文
- ✅ **推文 ID 去重缓存**：本地 processed_ids.json 追踪已处理推文，避免重复 AI 分析与下单
- ✅ **跳过日志输出**：对已在缓存中的推文输出日志 `[TWITTER_API] tweet {id} already processed, skipped`
- ✅ **JSONL 推文日志**：每个用户的完整推文数据存储在 JSONL，支持高效追加写入
- ✅ **API 失败提醒**：API 异常时输出警告，不自动降级（用户可手动调用本地 JSON）
- ✅ **多格式兼容**：支持 dict/list、多字段名称（data/tweets/results）

---

## 改动清单

### 1. **trading_bot/twitter_source.py**（更新）

**核心改进**：

| 改动点 | 原代码 | 新代码 | 说明 |
|--------|--------|--------|------|
| API 异常处理 | 自动降级到本地 JSON | 输出警告 + 返回 [] | 不隐藏问题，让用户察觉 |
| 缓存命中日志 | 无日志 | `[TWITTER_API] tweet {id} already processed, skipped` | 增强可追踪性 |
| 跳过计数 | 无 | `skipped_count` 统计 | 告知用户多少条被过滤 |
| aiohttp 缺失 | 降级到本地 | 输出提醒 + 返回 [] | 提示用户需要安装依赖 |

| JSONL 推文日志 | 无 | 每条推文追加到 JSONL | 记录完整推文数据供后续分析 |

**关键实现**：

```python
# 检查是否已处理（历史缓存）
if tweet_id in processed_ids:
    print(f"[TWITTER_API] tweet {tweet_id} already processed, skipped")
    skipped_count += 1
    continue

# 新增：追加推文到 JSONL 日志
_append_tweet_to_jsonl(username, tweet)
```

**JSONL 存储结构**：

```
trading_bot/twitter_media/
├── processed_ids.json              # ID 去重缓存
└── user_logs/
    ├── elonmusk.jsonl             # 每个用户的推文日志（JSONL 格式）
    ├── vitalikbuterin.jsonl
    └── ...
```

**JSONL 文件格式示例**：

```
{"id": "1234567890", "text": "Bitcoin reaching new ATH", "created_at": "2025-11-17T08:30:00Z", "author": "elonmusk", ...}
{"id": "1234567891", "text": "Ethereum merge complete", "created_at": "2025-11-17T08:45:00Z", "author": "vitalikbuterin", ...}
```

**日志示例**：

```
[TWITTER_API] 并发抓取 10 个用户的推文...
[TWITTER_API] tweet 1234567890 already processed, skipped
[TWITTER_API] tweet 1234567891 already processed, skipped
[TWITTER_API] 获取 5 条新推文，跳过 3 条已处理推文
```

### 2. **trading_bot/app_runner.py**（已集成，无改动）

继续使用 `mark_as_processed()` 标记处理过的推文 ID。

### 3. **trading_bot/twitter_media/processed_ids.json**（自动初始化）

格式保持不变：
```json
{
  "ids": [
    "tweet_id_1",
    "tweet_id_2"
  ]
}
```

---

## 核心特性详解

### 1. **三层去重机制**

```
API 返回推文
    ↓
检查 1：是否在 processed_ids.json（历史已处理）
  ✗ 如果是 → 输出"already processed"日志 → 跳过
  ✓ 如果否 → 继续
    ↓
检查 2：是否在本次会话 seen_ids（避免单轮重复）
  ✗ 如果是 → 跳过
  ✓ 如果否 → 继续
    ↓
检查 3：是否在 config.twitter_api.user_intro_mapping（用户列表）
  （已在 _fetch_for_user_async 阶段通过并发用户列表隐式检查）
    ↓
返回新推文 → 进入 AI 队列
```

### 2. **警告而非降级的设计**

**原来的做法（自动降级）**：
- API 失败 → 悄悄降级本地 JSON → 用户察觉不到问题
- 风险：隐藏 API 配置错误、网络问题

**新的做法（提醒用户）**：
- API 失败 → 输出 `⚠️ API 抓取失败: {error}。建议检查网络连接或 API 配置`
- 用户可主动选择：
  - 方案 A：修复 API 配置，重新运行
  - 方案 B：调用 `fetch_latest_tweets_from_local_json()` 进行测试

**测试建议**：
- 初期开发：直接用 `fetch_latest_tweets_from_local_json()` 测试全流程
- 后期集成：配置 API 密钥，改用 `fetch_latest_tweets_from_api()`

### 3. **日志标签统一**

| 日志标签 | 输出位置 | 说明 |
|---------|---------|------|
| `[TWITTER_API]` | twitter_source.py | API 数据源层（并发、去重、日志） |
| `[AI_QUEUE]` | app_runner.py | AI 队列与 worker（入队、完成、超时） |
| `[SIGNAL]` | app_runner.py | 信号流（接收、处理、错误） |
| `[ORDER]` | app_runner.py | 下单执行（请求、响应） |
| `[TWITTER_API] marked ... as processed` | app_runner.py | ID 标记（AI 完成、下单完成） |

---

## 测试方案

### 本地 JSON 测试（推荐初期）

```python
# 在 app_runner.py 中临时改为本地 JSON
# 第 433 行改为：
# fetch_func = fetch_latest_tweets_from_local_json  # 改为同步调用
# 需要包装为 async 版本：

async def _fetch_local_wrapper():
    return fetch_latest_tweets_from_local_json()

fetch_func = _fetch_local_wrapper
```

**验证清单**：

- [ ] 日志出现 `[TWITTER_API] tweet XXX already processed, skipped`
- [ ] processed_ids.json 中的 ID 数量逐次增加
- [ ] AI 队列正常工作（3 个 worker 处理推文）
- [ ] 下单流程正常执行

### JSONL 推文日志验证

**验证要点**：

```bash
# 1. 检查目录是否自动创建
ls -la trading_bot/twitter_media/user_logs/

# 2. 检查 JSONL 文件是否生成（每个用户一个）
cat trading_bot/twitter_media/user_logs/elonmusk.jsonl | head -1

# 3. 验证 JSONL 格式（每行一个完整 JSON 对象）
cat trading_bot/twitter_media/user_logs/elonmusk.jsonl | jq . | head -20

# 4. 计算推文总数
wc -l trading_bot/twitter_media/user_logs/*.jsonl

# 5. 验证追加模式（运行两次，第二次行数应增加而非重置）
```

**预期输出**：

- ✅ user_logs 目录存在，包含多个 `.jsonl` 文件
- ✅ 每行都是有效的 JSON 对象（可用 `jq` 解析）
- ✅ 文件逐次增长（支持追加写入）
- ✅ 无日志错误（追加失败时有错误提示但不中断流程）

### API 测试（后期集成）

配置 twitterapi.io API 密钥，运行 `fetch_latest_tweets_from_api()`：

- [ ] 10 个用户并发抓取成功
- [ ] 日志显示 `[TWITTER_API] 获取 N 条新推文，跳过 M 条已处理推文`
- [ ] 网络故障时输出警告（不降级）

---

## 环境与依赖

| 项 | 值 |
|----|-----|
| Python | 3.8+ |
| aiohttp | 可选（`pip install aiohttp`）；无则返回 [] |
| asyncio | 内置 |
| 存储目录 | `trading_bot/twitter_media/` |
| 缓存文件 | `processed_ids.json` |

---

## 完成定义（DoD）

- [x] 无编译错误（Pylance）
- [x] 所有配置来自 config.py（无硬编码）
- [x] 跳过日志已实现：`[TWITTER_API] tweet {id} already processed, skipped`
- [x] API 失败时输出警告（不自动降级）
- [x] processed_ids.json 自动初始化与持久化
- [x] JSONL 推文日志已实现
  - [x] `_get_user_logs_path(username)` 获取用户日志路径
  - [x] `_append_tweet_to_jsonl(username, tweet)` 追加推文到 JSONL
  - [x] user_logs 目录自动创建（Path.mkdir parents=True）
  - [x] 追加失败时有错误日志但不中断流程
- [x] 代码注释清晰（说明"为什么"而非"做了什么"）
- [x] 与 v1.2.0 异步 AI 队列无缝配合
- [x] 文档已更新，包含 JSONL 格式说明与验证步骤

---

## 后续步骤

### 短期（v1.3.1）
1. **本地 JSON 测试**：验证全流程工作正常
2. **日志审查**：确保跳过日志清晰可见
3. **ID 缓存验证**：确保 processed_ids.json 正确追踪

### 中期（v1.4.0）
1. **API 集成**：配置真实推特 API 密钥



---

## 相关文件

- [`trading_bot/twitter_source.py`](trading_bot/twitter_source.py) - 数据源实现
- [`trading_bot/app_runner.py`](trading_bot/app_runner.py) - 应用编排与 ID 标记
- [`trading_bot/config.py`](trading_bot/config.py) - TwitterAPIConfig 配置
- [`trading_bot/twitter_media/processed_ids.json`](trading_bot/twitter_media/processed_ids.json) - ID 缓存文件

---

## 总结

v1.3.0 通过**可见的去重日志 + 明确的错误提醒**，让用户对数据流有完整的可追踪性。相比自动降级方案：

| 方面 | 自动降级 | 提醒方案（v1.3.0） |
|------|---------|-----------------|
| 可追踪性 | ❌ 隐藏问题 | ✅ 明确提示 |
| 调试难度 | ❌ 易混淆 | ✅ 快速定位 |
| 生产稳定性 | ❌ 隐性风险 | ✅ 显性风险 |
| 用户掌控度 | ❌ 被动切换 | ✅ 主动选择 |

**建议**：初期用本地 JSON 验证全流程，待所有模块稳定后，再集成真实 API。这样既能快速验证业务逻辑，又能规避 API 依赖的风险。