# v1.2.0 实现文档

**版本**: v1.2.0  
**日期**: 2025-11-17  
**UTC+8 时间**: 15:50

---

## 核心问题与解决方案

### 背景
- **v1.0.0 性能瓶颈**：Poe API 同步调用阻塞主循环，AI 分析耗时 2-5 秒
- **实际循环周期**：> 10 秒，无法满足高频交易需求

### v1.2.0 设计目标
- ✅ 异步 AI 处理：后台 3 个 worker 并发分析推文
- ✅ 非阻塞主循环：推文入队立即返回，主循环保持 10 秒周期
- ✅ 智能缓存：结果缓存 + 60 秒过期清理机制
- ✅ 向后兼容：旧代码继续可用

---

## 核心改动清单

### 1. `trading_bot/tweet_analyzer.py`
**新增函数**：`call_ai_for_tweet_async(text, author, introduction, timeout=30)`
- 异步调用 AI，支持 timeout 参数
- 在 `asyncio.run_in_executor()` 中运行同步 Poe API
- 捕获 `asyncio.TimeoutError` 进行超时处理

**保留**：原有 `call_ai_for_tweet()` 同步函数（向后兼容）

### 2. `trading_bot/app_runner.py`
**新增初始化** (TwitterCrawlerSignalSource.__init__)：
```python
# AI 队列 & 缓存
self.ai_queue: asyncio.Queue = asyncio.Queue(maxsize=0)  # 无限制
self.ai_results_cache: Dict[str, Any] = {}  # {tweet_id: ai_result}
self.tweet_status: Dict[str, Dict[str, Any]] = {}  # {tweet_id: {status, created_at}}
self.worker_tasks: List[asyncio.Task] = []
self.cleanup_task: Optional[asyncio.Task] = None
```

**新增方法**：
- `_ai_worker()`: 后台 worker 任务，从队列取推文 → 调用异步 AI → 存储结果
- `_cleanup_expired_tweets()`: 定期清理 60 秒未完成的推文

**修改 stream() 方法**：
- 启动 3 个 worker 任务 + cleanup 任务
- 主循环：推文入队（非阻塞）→ 检查缓存 → yield Signal
- finally 块：清理后台任务

---

## 流程图

```
┌─────────────────────────────────────────────────────────────────┐
│ Main Loop (10s interval)                                        │
│  1. Fetch tweets from crawler                                   │
│  2. For each unprocessed tweet:                                 │
│     - Queue into ai_queue (non-blocking)                        │
│     - Mark status as "pending"                                  │
│     - Check ai_results_cache                                    │
│     - If result exists: yield TradeSignal                       │
└─────────────────────────────────────────────────────────────────┘
              ↑                              ↓
              │                             │
        worker_tasks (×3)          cleanup_task (every 5s)
        ┌──────────────┐            ┌──────────────┐
        │ Worker 1     │            │ Cleanup      │
        │ Worker 2     │            │ - Check expired
        │ Worker 3     │            │ - Remove >60s  
        └──────────────┘            └──────────────┘
              │                             
        ai_queue.get()              
        call_ai_for_tweet_async()   
        store result in cache       
```

---

## 关键参数配置

| 参数 | 值 | 说明 |
|------|-----|------|
| AI 队列大小 | 无限制 | asyncio.Queue(maxsize=0) |
| Worker 数量 | 3 | 并发处理能力 |
| AI 单次超时 | 30 秒 | asyncio.wait_for(timeout=30) |
| 过期推文周期 | 60 秒 | 超过 60 秒未完成则丢弃 |
| Cleanup 检查间隔 | 5 秒 | 定期清理过期数据 |
| 主循环轮询间隔 | 10 秒 | 保持与 v1.0.0 一致 |

---

## 异常处理

### AI 超时 (asyncio.TimeoutError)
- Worker 捕获并标记 `status="timeout"`
- 日志：`[AI_WORKER] timeout after 30s for tweet {tweet_id}`
- 推文仍被追踪，60 秒后自动清理

### 队列满 (理论上不会)
- 无限制队列，不会阻塞入队
- 内存压力：由 cleanup 任务定期清理缓存

### AI 错误 (Exception)
- Worker 捕获并标记 `status="error"`
- 日志：`[AI_WORKER] error for tweet {tweet_id}: {e}`
- 错误推文也被自动清理

---

## 验证清单

- [ ] AI 队列正确入队/出队
- [ ] 3 个 worker 并发处理，30s 超时正确捕获
- [ ] 60 秒未完成的推文正确清理
- [ ] 主循环保持 10 秒周期，不被 AI 阻塞
- [ ] 日志输出完整（[AI_QUEUE]、[AI_WORKER]、[AI_TIMEOUT] 等）
- [ ] 与 v1.0.0 兼容（旧的同步调用仍可用）

---

## 已知限制

1. **内存使用**：大量待处理推文会占用内存（由缓存字典管理）
2. **顺序保证**：异步处理不保证推文处理顺序
3. **推文丢弃**：60 秒未完成的推文永久丢弃（无重试机制）
4. **Poe API 限制**：单个 worker 同步调用受 API 速率限制约束

---

## 下一步优化方向

1. **动态 worker 数量**：根据队列长度自动调整 worker 数量
2. **失败重试**：为超时/错误的推文实现有限次重试
3. **优先级队列**：按推文置信度或来源优先级排序
4. **监控面板**：实时显示队列长度、worker 状态、处理速率
