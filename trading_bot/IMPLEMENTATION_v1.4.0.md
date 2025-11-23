# v1.4.0 AI 分析流程优化与健壮性提升

**日期**: 2025-11-20
**状态**: 规划中

## 1. 问题分析

### 1.1 数据处理问题
- **现象**: 用户反馈代码可能将 JSON 数据误当作 TXT 处理，导致 AI 分析失败或结果不准确。
- **原因**: `app_runner.py` 中的 `_ai_worker` 在提取推文内容时，可能直接将整个推文对象（字典）转换为字符串，而不是提取关键的 `text` 字段。此外，`author` 字段如果是字典，直接转换也会导致信息丢失。id是可以用的，内容txt是 tweets[0]到tweets[-1]，Id 是 tweets[0]['id'], author = tweets[0]['author']['userName']  （一切以这个为准这个是我手动修改的）
- **证据**: 代码中存在 `text = str(tweet)` 和 `user_name = str(tweet.get("author", {}))` 的写法。

### 1.2 去重逻辑不完善
- **现状**: 虽然有 `processed_ids` 检查，但在高并发或异常情况下，可能会重复提交正在处理中的推文给 AI。
- **需求**: 必须确保“给 AI 后，在处理中，不要再给 AI 去处理”。

### 1.3 重试机制缺失或不完善
- **现状**: 简单的超时重试可能导致死循环或无效重试。
- **需求**: 
    - 处理失败（Error/Timeout）时，允许重试。
    - 最大重试次数限制为 3 次。
    - 需要处理“僵尸任务”（卡在 Processing 状态过久的任务）。

## 2. 解决方案

### 2.1 优化 `TwitterCrawlerSignalSource` 类 (`trading_bot/app_runner.py`)

#### A. 完善状态管理 (`tweet_status`)
在内存中维护一个状态字典，记录每个推文的处理状态：
```python
self.tweet_status[tweet_id] = {
    "status": "pending" | "processing" | "done" | "timeout" | "error",
    "retry_count": 0,
    "created_at": timestamp,
    "last_update": timestamp
}
```

#### B. 增强 `_ai_worker`
- **数据提取**: 健壮地从队列数据中提取 `tweet` 对象和 `id`。
- **字段解析**: 
    - 正确提取 `text`：`tweet.get("text", "")`。
    - 正确提取 `author`：处理 `author` 为字典的情况，提取 `userName` 或 `name`。
- **状态更新**: 在处理开始、完成、失败时及时更新 `tweet_status` 和 `last_update`。
- **异常处理**: 确保所有异常路径都调用 `task_done()`，防止队列阻塞。

#### C. 改进 `stream` 主循环
- **去重检查**: 
    1. 检查 `processed_ids`（持久化历史）。
    2. 检查 `tweet_status`（当前内存状态）。
    3. 如果状态是 `processing` 或 `pending`，坚决跳过。
- **重试策略**:
    - 如果状态是 `timeout` 或 `error`：
        - 检查 `retry_count < 3`：重置状态为 `pending`，重新入队。
        - 检查 `retry_count >= 3`：跳过，不再重试（可选择记录日志）。

#### D. 新增僵尸任务清理 (`_cleanup_expired_tweets`)
- **僵尸检测**: 如果任务处于 `processing` 状态超过 5 分钟（300秒），视为超时失败。
- **处理动作**: 强制将状态置为 `timeout`，增加 `retry_count`，允许主循环在下一轮进行重试。
- **最终清理**: 对于超过 30 分钟的旧任务，从内存中彻底清除。

### 2.2 验证数据源 (`trading_bot/twitter_source.py`)
- 确认 `fetch_latest_tweets` 返回的是解析后的字典列表，而非原始 JSON 字符串。根据代码审查，目前使用的是 `json.load`，返回结构正确，内容是tweets[0]到之后，一共20条数据，当然你也要根据长度去读取。

## 3. 修改计划

### 步骤 1: 修改 `trading_bot/app_runner.py`
- 重写 `_ai_worker` 方法。
- 重写 `_cleanup_expired_tweets` 方法。
- 重写 `stream` 方法。

### 步骤 2: 验证
- 运行 `main.py`。
- 观察日志，确认：
    - 推文被正确入队。
    - AI Worker 正确提取了文本和作者。
    - 处理中的推文没有被重复入队。
    - 模拟超时或错误，确认重试逻辑生效。

## 4. 风险评估
- **内存占用**: `tweet_status` 会随时间增长，但已有清理机制（30分钟过期），风险可控。
- **并发竞争**: `stream` 和 `worker` 都会读写 `tweet_status`，但在 Python 的 `asyncio` 单线程模型下，字典操作是原子的，不存在线程安全问题。
