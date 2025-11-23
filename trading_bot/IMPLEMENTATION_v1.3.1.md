# IMPLEMENTATION_v1.3.1.md

**版本**：v1.3.1（JSONL 推文日志 + 两套版本代码 + v1.4.0 框架设计）  
**日期**：2025-11-17 17:24 (北京时间)

---

## 核心变更概述

### 改动清单

| 文件 | 变更 | 说明 |
|------|------|------|
| `trading_bot/twitter_source.py` | ✅ 移除"已处理"跳过日志 | 直接跳过，无日志输出 |
| `trading_bot/twitter_source.py` | ✅ 新增本地版本函数 | `fetch_latest_tweets_from_local_with_logging()` |
| `trading_bot/twitter_source.py` | ✅ 新增 API 版本函数 | `fetch_latest_tweets_from_api_with_logging()` |
| `trading_bot/twitter_source.py` | ✅ 更新主入口函数 | `fetch_latest_tweets()` 现调用本地版本（可切换） |
| `trading_bot/twitter_source.py` | ✅ 新增 v1.4.0 框架注释 | 动态触发机制设计框架（伪代码） |

---

## 详细变更说明

### 1. 移除"已处理"跳过日志

**原代码（v1.3.0）**：
```python
if tweet_id in processed_ids:
    print(f"[TWITTER_API] tweet {tweet_id} already processed, skipped")
    skipped_count += 1
    continue
```

**新代码（v1.3.1）**：
```python
if tweet_id in processed_ids:
    skipped_count += 1
    continue  # 直接跳过，无日志
```

**原因**：
- 避免日志过载（每条已处理推文都输出一行）
- 仅在汇总日志中统计跳过数量：`跳过 {skipped_count} 条已处理推文`

---

### 2. 新增两套完整版本函数

#### 版本 A：API 版（后期集成）

```python
async def fetch_latest_tweets_from_api_with_logging() -> List[Dict[str, Any]]:
    """
    【版本 A - API 版】并发抓取多个用户的推文（后期集成）
    
    配置项：需要设置 TwitterAPIConfig 中的 api_key 和其他参数
    推荐用途：生产环境，真实推特数据
    
    流程同 fetch_latest_tweets_from_api()，支持 JSONL 日志记录
    """
    return await fetch_latest_tweets_from_api()
```

**特点**：
- 调用真实 API（twitterapi.io）
- 支持并发多用户抓取
- 支持 JSONL 日志记录（第 280-281 行）
- 支持 processed_ids 去重缓存

#### 版本 B：本地版（初期测试）

```python
async def fetch_latest_tweets_from_local_with_logging() -> List[Dict[str, Any]]:
    """
    【版本 B - 本地版】从本地 JSON 读取推文并记录到 JSONL（初期测试推荐）
    
    配置项：无需 API 密钥，直接读取 推特抢跑/twitter_media/*.json
    推荐用途：初期开发、功能验证、快速迭代
    
    特性：
    - 支持与 API 版本相同的 JSONL 日志记录
    - 无网络依赖，速度快
    - 适合全流程功能验证
    """
    tweets = fetch_latest_tweets_from_local_json()
    
    # 记录到 JSONL
    for tweet in tweets:
        username = tweet.get("user_name") or tweet.get("author") or "unknown"
        _append_tweet_to_jsonl(username, tweet)
    
    return tweets
```

**特点**：
- 从本地 JSON 文件读取推文
- 无 API 依赖，无网络请求
- 支持相同的 JSONL 日志记录
- 适合快速功能验证

---

### 3. 版本切换机制

**主入口函数 `fetch_latest_tweets()`**：

```python
async def fetch_latest_tweets() -> List[Dict[str, Any]]:
    """
    获取最新推文的异步接口（推荐方法）。
    
    版本切换说明：
    - 初期测试：使用本地版本
    - 后期集成：使用 API 版本
    
    在 app_runner.py 中的调用处选择其中一个：
      # return await fetch_latest_tweets_from_api_with_logging()     # 后期：真实 API
      # return await fetch_latest_tweets_from_local_with_logging()   # 初期：本地测试
    
    返回：推文列表，每条至少包含 id、text 字段
    """
    # 【初期开发推荐】使用本地版本测试
    return await fetch_latest_tweets_from_local_with_logging()
```

**切换方法**：
- 修改第 322 行的 return 语句
- 或在 `app_runner.py` 中创建条件判断切换

---

### 4. v1.4.0 动态触发框架设计

**背景**：目前推特查询是定时固定执行的（如 5 分钟一次）。后期需要根据 K 线成交量异动信号动态触发查询。

**框架设计思路**：

```
信号监听 → 触发条件检查 → 启动 10 分钟查询窗口 → 5 秒间隔查询 → 自动停止
```

**伪代码框架**（在文件末尾）：

```python
class TwitterTrigger:
    """
    根据 K 线信号动态控制推特查询的触发器。
    
    核心功能：
    1. 监听成交量异动信号（从 signals.py 获取）
    2. 触发条件满足时启动 10 分钟的查询周期
    3. 查询间隔：5 秒一次
    4. 支持动态用户列表切换（根据异动币种）
    """
    
    def __init__(self, duration_seconds: int = 600, interval_seconds: float = 5):
        self.duration = duration_seconds       # 10 分钟
        self.interval = interval_seconds       # 5 秒
        self.trigger_start_time: Optional[float] = None
        self.active_usernames: List[str] = []  # 动态用户列表
    
    def is_triggered(self, signal: Dict[str, Any]) -> bool:
        """检查是否满足触发条件（成交量异动）"""
        pass
    
    def get_active_users(self, signal: Dict[str, Any]) -> List[str]:
        """根据信号获取本次查询的用户列表（动态映射）"""
        pass
    
    async def run_trigger_window(self, fetch_func, signal):
        """执行 10 分钟查询窗口（5 秒间隔）"""
        pass
```

**集成方案**（待实现）：
- 在 `app_runner.py` 中监听信号流
- 当检测到成交量异动时，启动 TwitterTrigger 实例
- 10 分钟后自动停止，恢复定时查询模式

---

## 目录结构

```
推特抢跑/twitter_media/
├── processed_ids.json              # 已处理推文 ID 列表（去重缓存）
├── user_logs/                      # 用户推文日志目录
│   ├── elonmusk.jsonl
│   ├── vitalikbuterin.jsonl
│   └── ...
└── *.json                          # 本地推文数据（测试用）
```

---

## JSONL 日志格式

**文件**：`推特抢跑/twitter_media/user_logs/{username}.jsonl`

**内容示例**：
```json
{"id": "1234567890", "text": "Bitcoin to the moon!", "author": "elonmusk", "timestamp": "2025-11-17T09:00:00Z"}
{"id": "1234567891", "text": "Smart contracts are amazing", "author": "vitalikbuterin", "timestamp": "2025-11-17T09:05:00Z"}
```

**特点**：
- 每行一个 JSON 对象
- 追加写入（`open(..., "a")`），高效支持流式日志
- 字段灵活（支持不同数据源的推文字段）
- 推文 ID 仅在 processed_ids.json 中管理去重

---

## 验证要点

### 初期测试（本地版本）

```bash
# 1. 确保本地 JSON 文件存在
ls 推特抢跑/twitter_media/*.json

# 2. 运行 app_runner，观察日志
python trading_bot/app_runner.py

# 3. 检查 JSONL 日志是否生成
ls 推特抢跑/twitter_media/user_logs/

# 4. 查看日志内容（示例）
head -5 推特抢跑/twitter_media/user_logs/elonmusk.jsonl
```

### 后期集成（API 版本）

```python
# 在 twitter_source.py 第 322 行改为：
return await fetch_latest_tweets_from_api_with_logging()

# 需要配置 config.py 中的 TwitterAPIConfig：
twitter_api:
  api_key: "your-api-key-here"
  user_intro_mapping:
    "elonmusk": "Elon Musk (@elonmusk)"
    "vitalikbuterin": "Vitalik Buterin (@vitalikbuterin)"
```

---

## 注意事项与风险

### 兼容性

- ✅ 本地版本与 API 版本共存，无冲突
- ✅ JSONL 日志与原有 processed_ids.json 独立管理
- ✅ processed_ids 缓存仅在 API 版本中使用

### 边界情况

1. **推文字段缺失**：处理 `user_name/author/unknown` 三级降级
2. **JSONL 写入失败**：捕获异常，输出错误日志，不中断主流程
3. **本地 JSON 文件为空**：返回空列表 `[]`

### 后续优化方向

- [ ] v1.4.0：实现 TwitterTrigger 动态触发机制
- [ ] v1.5.0：支持多币种动态用户列表映射
- [ ] v1.6.0：JSONL 日志查询与分析接口

---

## 完成定义 (DoD)

- [x] 移除"已处理"跳过日志输出
- [x] 新增 API 版本函数（支持 JSONL 记录）
- [x] 新增本地版本函数（支持 JSONL 记录）
- [x] 更新主入口函数（初期默认本地版本）
- [x] 新增 v1.4.0 框架伪代码与集成方案说明
- [x] 更新此文档（版本号、变更清单、验证要点）
- [x] 代码无类型检查错误（Pylance）

---

## 快速命令参考

```bash
# 查看已处理 ID 缓存
cat 推特抢跑/twitter_media/processed_ids.json

# 查看本地推文日志
cat 推特抢跑/twitter_media/user_logs/elonmusk.jsonl | python -m json.tool

# 统计已处理推文数量
cat 推特抢跑/twitter_media/processed_ids.json | grep -o '"' | wc -l

# 清空日志（谨慎操作）
rm -rf 推特抢跑/twitter_media/user_logs/*.jsonl
```

---

## 下一步行动

1. **本地验证**：运行 app_runner.py，确认本地版本能正常抓取并记录 JSONL
2. **API 集成**：获取 twitterapi.io API Key，修改 config.py
3. **v1.4.0 设计**：与用户讨论动态触发机制的具体实现
4. **性能优化**：监控 JSONL 写入性能，评估是否需要批量写入
