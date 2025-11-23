# Trading Bot 日志框架设计文档

**版本**: v1.0.0  
**最后更新**: 2025-11-22  
**文档状态**: 设计阶段

---

## 1. 日志框架目标与需求

### 1.1 设计背景

当前系统使用 `print()` 语句进行日志输出，存在以下问题：
- 日志格式不统一，难以解析和分析
- 日志仅输出到控制台，无法持久化存储
- 缺少结构化信息，不利于监控和告警
- 无法记录函数执行性能指标
- 不支持日志级别控制，生产环境日志过多

### 1.2 核心目标

- **统一日志格式**: 采用结构化JSON格式，便于机器解析和查询
- **多输出通道**: 同时支持文件持久化和控制台输出
- **性能可观测**: 自动记录函数执行耗时，识别性能瓶颈
- **分级管理**: 支持DEBUG/INFO/WARNING/ERROR等级别控制
- **业务可追溯**: 记录完整的推文处理、AI分析、交易执行链路
- **低性能开销**: 异步日志写入，不影响主业务流程

### 1.3 关键需求

1. **统一存储**: 所有日志写入单一文件，便于集中分析
2. **无按天轮转**: 使用固定日志文件，可配置大小限制（如100MB）
3. **函数耗时统计**: 自动记录关键函数的执行时间和调用次数
4. **上下文追踪**: 支持请求ID、推文ID等上下文信息的跨函数传递
5. **兼容现有代码**: 平滑迁移现有 `print()` 日志，保持业务连续性

---

## 2. 日志结构设计（结构化JSON格式）

### 2.1 基础日志结构

每条日志以JSON对象形式存储，包含以下字段：

```json
{
  "timestamp": "2025-11-22T12:30:45.123456+08:00",
  "level": "INFO",
  "module": "app_runner",
  "func": "_consume_signals_and_trade",
  "line": 627,
  "component": "SIGNAL",
  "message": "received: tweet_id=1234567890, symbol=BTCUSDT, side=BUY",
  "context": {
    "tweet_id": "1234567890",
    "symbol": "BTCUSDT",
    "side": "BUY"
  },
  "performance": {
    "duration_ms": 45.2,
    "memory_mb": 128.5
  },
  "extra": {}
}
```

### 2.2 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `timestamp` | string | 是 | ISO 8601格式时间戳，带时区信息 |
| `level` | string | 是 | 日志级别: DEBUG/INFO/WARNING/ERROR/CRITICAL |
| `module` | string | 是 | Python模块名（如 `app_runner`） |
| `func` | string | 是 | 函数名（如 `_consume_signals_and_trade`） |
| `line` | integer | 是 | 代码行号 |
| `component` | string | 是 | 业务组件标识（如 `SIGNAL`、`AI_WORKER`、`TWITTER_API`） |
| `message` | string | 是 | 人类可读的日志消息 |
| `context` | object | 否 | 业务上下文信息（推文ID、交易对等） |
| `performance` | object | 否 | 性能指标（耗时、内存等） |
| `extra` | object | 否 | 扩展字段，用于自定义数据 |

### 2.3 组件标识定义

保留现有代码中的日志前缀作为 `component` 字段：

| 组件标识 | 说明 | 使用场景 |
|----------|------|----------|
| `SYSTEM` | 系统级日志 | 启动、关闭、配置加载 |
| `TWITTER_API` | 推特API调用 | 推文获取、API请求 |
| `AI_WORKER` | AI分析工作线程 | AI调用、超时处理 |
| `AI_ASYNC` | AI异步调用 | AI分析结果 |
| `SIGNAL` | 交易信号处理 | 信号接收、转换 |
| `ORDER` | 订单执行 | 下单、订单响应 |
| `EXIT` | 平仓操作 | 止损止盈执行 |
| `RISK_MANAGER` | 风控管理 | 持仓监控、价格轮询 |
| `TWEET_RECORD` | 推文记录管理 | 记录持久化、加载 |
| `CONFIG` | 配置管理 | 配置加载、验证 |

---

## 3. 日志级别定义

### 3.1 级别划分

```python
class LogLevel:
    DEBUG = 10     # 详细调试信息
    INFO = 20      # 正常业务流程
    WARNING = 30   # 警告（非致命错误）
    ERROR = 40     # 错误（功能受影响）
    CRITICAL = 50  # 严重错误（系统不可用）
```

### 3.2 使用场景

| 级别 | 使用场景 | 示例 |
|------|----------|------|
| **DEBUG** | 开发调试，详细跟踪数据流 | AI调用参数、API响应详情 |
| **INFO** | 正常业务流程，关键节点 | 推文接收、信号生成、订单执行 |
| **WARNING** | 非致命异常，可恢复 | AI超时重试、API限流、部分失败 |
| **ERROR** | 功能异常，需要关注 | 下单失败、AI调用异常、配置错误 |
| **CRITICAL** | 系统级错误，需立即处理 | 交易所连接断开、配置缺失 |

### 3.3 环境配置建议

- **开发环境**: `DEBUG` 级别，包含完整调试信息
- **测试环境**: `INFO` 级别，记录业务流程
- **生产环境**: `WARNING` 级别，仅记录异常和关键事件

---

## 4. 日志输出方式（文件+控制台）

### 4.1 输出配置

```python
# config.py 中的日志配置
@dataclass
class LoggingConfig:
    level: str = "INFO"                    # 全局日志级别
    file_path: str = "logs/trading_bot.log" # 日志文件路径
    max_bytes: int = 100 * 1024 * 1024     # 文件大小限制（100MB）
    backup_count: int = 1                  # 备份文件数量（0表示不轮转）
    console_output: bool = True            # 是否输出到控制台
    file_output: bool = True               # 是否输出到文件
    json_format: bool = True               # 是否使用JSON格式
```

### 4.2 文件存储策略

**无按天轮转设计**：
- 使用单一日志文件 `trading_bot.log`
- 当文件大小超过 `max_bytes`（默认100MB）时，执行轮转
- `backup_count=1` 表示保留一个备份文件 `trading_bot.log.1`
- `backup_count=0` 表示禁用轮转，文件无限增长（需手动清理）

**轮转示例**：
```
trading_bot.log          # 当前活跃日志文件
trading_bot.log.1        # 上一个日志文件（最多保留1个）
```

### 4.3 控制台输出

控制台输出使用**易读格式**（非JSON），便于开发调试：

```
2025-11-22 12:30:45.123 [INFO] [SIGNAL] app_runner:_consume_signals_and_trade:627
  received: tweet_id=1234567890, symbol=BTCUSDT, side=BUY
  duration: 45.2ms
```

---

## 5. 函数耗时统计机制

### 5.1 性能装饰器设计

使用装饰器自动记录函数执行耗时：

```python
# trading_bot/performance.py
import time
import functools
from typing import Callable, Optional
from trading_bot.logger import logger

def log_performance(
    component: Optional[str] = None,
    log_args: bool = False
) -> Callable:
    """
    性能监控装饰器
    
    Args:
        component: 组件标识（如 AI_WORKER、TWITTER_API）
        log_args: 是否记录函数参数（注意：可能包含敏感信息）
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            start_memory = get_current_memory_mb()
            
            try:
                result = await func(*args, **kwargs)
                status = "success"
                return result
            except Exception as e:
                status = f"error: {type(e).__name__}"
                raise
            finally:
                duration_ms = (time.perf_counter() - start_time) * 1000
                end_memory = get_current_memory_mb()
                memory_delta_mb = end_memory - start_memory
                
                # 构建日志
                logger.bind(
                    component=component or func.__name__.upper(),
                    performance={
                        "duration_ms": round(duration_ms, 2),
                        "memory_delta_mb": round(memory_delta_mb, 2),
                        "status": status
                    },
                    context={
                        "func_args": str(args) if log_args else None,
                        "func_kwargs": str(kwargs) if log_args else None
                    }
                ).info(f"Function {func.__name__} completed")
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            start_memory = get_current_memory_mb()
            
            try:
                result = func(*args, **kwargs)
                status = "success"
                return result
            except Exception as e:
                status = f"error: {type(e).__name__}"
                raise
            finally:
                duration_ms = (time.perf_counter() - start_time) * 1000
                end_memory = get_current_memory_mb()
                memory_delta_mb = end_memory - start_memory
                
                logger.bind(
                    component=component or func.__name__.upper(),
                    performance={
                        "duration_ms": round(duration_ms, 2),
                        "memory_delta_mb": round(memory_delta_mb, 2),
                        "status": status
                    }
                ).info(f"Function {func.__name__} completed")
        
        # 判断是同步还是异步函数
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator
```

### 5.2 使用示例

```python
# 监控AI调用性能
@log_performance(component="AI_ASYNC", log_args=True)
async def call_ai_for_tweet_async(text: str, author: str, introduction: str):
    # AI调用逻辑
    pass

# 监控推文获取性能
@log_performance(component="TWITTER_API")
async def fetch_latest_tweets_from_api():
    # API调用逻辑
    pass

# 监控交易执行性能
@log_performance(component="ORDER")
async def place_future_market_order(symbol: str, side: str, quantity: float):
    # 下单逻辑
    pass
```

### 5.3 性能日志输出

```json
{
  "timestamp": "2025-11-22T12:30:45.123456+08:00",
  "level": "INFO",
  "module": "tweet_analyzer",
  "func": "call_ai_for_tweet_async",
  "line": 183,
  "component": "AI_ASYNC",
  "message": "Function call_ai_for_tweet_async completed",
  "context": {
    "func_args": "('BTC will moon', 'elonmusk', 'CEO of Tesla')",
    "func_kwargs": "{}"
  },
  "performance": {
    "duration_ms": 2345.67,
    "memory_delta_mb": 12.3,
    "status": "success"
  }
}
```

---

## 6. 关键日志事件定义

### 6.1 系统生命周期事件

| 事件 | 组件 | 级别 | 上下文字段 | 说明 |
|------|------|------|------------|------|
| 系统启动 | `SYSTEM` | INFO | `version`, `config_loaded` | 应用启动完成 |
| 系统关闭 | `SYSTEM` | INFO | `shutdown_reason` | 优雅退出 |
| 配置加载 | `CONFIG` | INFO | `config_path`, `env` | 配置文件加载 |
| 配置错误 | `CONFIG` | ERROR | `error`, `missing_keys` | 配置缺失或无效 |

### 6.2 推文处理事件

```python
# 推文获取
logger.bind(
    component="TWITTER_API",
    context={"username": "elonmusk", "count": 10}
).info(f"Fetched {len(tweets)} tweets")

# AI分析开始
logger.bind(
    component="AI_WORKER",
    context={"tweet_id": "1234567890", "text_length": 280}
).info("Starting AI analysis")

# AI分析完成
logger.bind(
    component="AI_ASYNC",
    context={
        "tweet_id": "1234567890",
        "ai_result": ai_result,
        "retry_count": 0
    }
).info("AI analysis completed")
```

### 6.3 交易执行事件

```python
# 信号接收
logger.bind(
    component="SIGNAL",
    context={
        "tweet_id": signal.source_id,
        "symbol": signal.symbol,
        "side": signal.side,
        "position_pct": signal.position_pct
    }
).info(f"Received trade signal")

# 下单执行
logger.bind(
    component="ORDER",
    context={
        "symbol": signal.symbol,
        "side": signal.side,
        "quantity": quantity,
        "price": price
    }
).info(f"Placing market order")

# 下单结果
logger.bind(
    component="ORDER",
    context={
        "symbol": signal.symbol,
        "order_id": order_resp.get("orderId"),
        "status": order_resp.get("status")
    }
).info(f"Order response: {order_resp}")
```

### 6.4 风控管理事件

```python
# 持仓注册
logger.bind(
    component="RISK_MANAGER",
    context={
        "position_id": position_id,
        "symbol": position.symbol,
        "quantity": position.quantity,
        "entry_price": position.entry_price
    }
).info(f"Registered position")

# 止损触发
logger.bind(
    component="EXIT",
    context={
        "position_id": position_id,
        "symbol": position.symbol,
        "exit_reason": "stop_loss",
        "pnl": -125.50
    }
).warning(f"Stop loss triggered")

# 止盈触发
logger.bind(
    component="EXIT",
    context={
        "position_id": position_id,
        "symbol": position.symbol,
        "exit_reason": "take_profit",
        "take_profit_level": 1,
        "pnl": 250.00
    }
).info(f"Take profit executed")
```

---

## 7. 日志使用示例

### 7.1 基础日志记录

```python
from trading_bot.logger import logger

# INFO级别日志
logger.info("System started successfully")

# 带上下文日志
logger.bind(
    component="TWITTER_API",
    context={"username": "elonmusk"}
).info("Fetching latest tweets")

# 错误日志
logger.bind(
    component="AI_ASYNC",
    context={"tweet_id": "1234567890"}
).error(f"AI analysis failed: {error_message}")

# 带性能数据
logger.bind(
    component="ORDER",
    performance={"duration_ms": 123.45}
).info("Order placed")
```

### 7.2 上下文管理器（自动追踪）

```python
from trading_bot.logger import logger

# 自动添加上下文
with logger.contextualize(tweet_id="1234567890", symbol="BTCUSDT"):
    logger.info("Processing tweet")  # 自动包含tweet_id和symbol
    
    # 调用其他函数，上下文自动传递
    await process_signal(signal)
    
    logger.info("Tweet processing completed")

# 上下文退出后，不再包含额外字段
logger.info("Back to normal logging")
```

### 7.3 异常捕获与记录

```python
from trading_bot.logger import logger

try:
    await place_future_market_order(symbol, side, quantity)
except Exception as e:
    logger.bind(
        component="ORDER",
        context={
            "symbol": symbol,
            "side": side,
            "error_type": type(e).__name__
        }
    ).exception("Order execution failed")  # 自动记录堆栈跟踪
```

### 7.4 性能监控集成

```python
from trading_bot.performance import log_performance

@log_performance(component="AI_ASYNC")
async def call_ai_for_tweet_async(text: str, author: str):
    # AI调用逻辑
    pass

# 装饰器自动记录：
# - 函数开始时间
# - 函数结束时间
# - 执行耗时（毫秒）
# - 内存变化（MB）
# - 执行状态（success/error）
```

---

## 8. 配置说明

### 8.1 配置文件示例

```python
# trading_bot/config.py

@dataclass
class LoggingConfig:
    # 全局日志级别
    level: str = "INFO"
    
    # 文件输出配置
    file_output: bool = True
    file_path: str = "logs/trading_bot.log"
    max_bytes: int = 100 * 1024 * 1024  # 100MB
    backup_count: int = 1  # 0表示不轮转
    
    # 控制台输出配置
    console_output: bool = True
    console_level: str = "INFO"  # 控制台可独立设置级别
    
    # 格式配置
    json_format: bool = True  # 文件使用JSON格式
    console_json_format: bool = False  # 控制台使用易读格式
    
    # 性能监控
    enable_performance_logging: bool = True
    performance_sample_rate: float = 1.0  # 采样率（1.0表示100%记录）
    
    # 敏感信息过滤
    filter_sensitive_data: bool = True
    sensitive_keys: List[str] = None  # 需要过滤的字段名
    
    def __post_init__(self):
        if self.sensitive_keys is None:
            self.sensitive_keys = [
                "api_key", "api_secret", "poe_api_key", 
                "private_key", "password", "token"
            ]
```

### 8.2 环境变量配置

```bash
# .env 文件
# 日志配置
LOG_LEVEL=INFO
LOG_FILE_PATH=logs/trading_bot.log
LOG_MAX_BYTES=104857600  # 100MB
LOG_BACKUP_COUNT=1
LOG_CONSOLE_OUTPUT=true
LOG_JSON_FORMAT=true

# 性能监控
ENABLE_PERFORMANCE_LOGGING=true
PERFORMANCE_SAMPLE_RATE=1.0
```

### 8.3 不同环境配置建议

**开发环境**：
```python
LoggingConfig(
    level="DEBUG",
    console_output=True,
    file_output=True,
    enable_performance_logging=True,
    performance_sample_rate=1.0
)
```

**测试环境**：
```python
LoggingConfig(
    level="INFO",
    console_output=True,
    file_output=True,
    enable_performance_logging=True,
    performance_sample_rate=0.5  # 50%采样
)
```

**生产环境**：
```python
LoggingConfig(
    level="WARNING",
    console_output=False,  # 减少控制台输出
    file_output=True,
    enable_performance_logging=True,
    performance_sample_rate=0.1  # 10%采样，减少开销
)
```

---

## 9. 日志分析工具

### 9.1 命令行查询

```bash
# 查看所有ERROR级别日志
cat logs/trading_bot.log | jq 'select(.level == "ERROR")'

# 查看特定组件日志
cat logs/trading_bot.log | jq 'select(.component == "AI_WORKER")'

# 查看慢查询（耗时>1秒）
cat logs/trading_bot.log | jq 'select(.performance.duration_ms > 1000)'

# 查看特定推文处理链路
cat logs/trading_bot.log | jq 'select(.context.tweet_id == "1234567890")'
```

### 9.2 日志监控告警

```python
# 示例：监控ERROR日志并发送告警
import json

error_count = 0
with open("logs/trading_bot.log", "r") as f:
    for line in f:
        log = json.loads(line)
        if log["level"] == "ERROR":
            error_count += 1
            # 发送告警到钉钉/邮件
            send_alert(log)

if error_count > 10:
    send_summary_alert(f"系统异常：{error_count}个错误")
```

---

## 10. 迁移计划

### 10.1 第一阶段：日志框架实现

1. 实现 `trading_bot/logger.py` 核心日志模块
2. 实现 `trading_bot/performance.py` 性能监控模块
3. 在 `config.py` 中添加 `LoggingConfig`
4. 编写单元测试

### 10.2 第二阶段：逐步替换

按模块逐步替换 `print()` 语句：

1. **基础设施层**（config.py, tweet_record_manager.py）
2. **适配器层**（twitter_source.py, tweet_analyzer.py）
3. **核心层**（signals.py, risk_exit.py）
4. **应用层**（app_runner.py, main.py）

### 10.3 第三阶段：性能优化

1. 添加异步日志处理器
2. 实现日志采样机制
3. 优化JSON序列化性能
4. 添加日志缓冲区

---

## 11. 附录

### 11.1 日志文件示例

```json
{"timestamp": "2025-11-22T12:30:00.123456+08:00", "level": "INFO", "module": "main", "func": "main", "line": 52, "component": "SYSTEM", "message": "Trading bot started", "context": {"version": "v1.4.0"}, "performance": {"duration_ms": 0.0}}
{"timestamp": "2025-11-22T12:30:05.234567+08:00", "level": "INFO", "module": "app_runner", "func": "_consume_signals_and_trade", "line": 627, "component": "SIGNAL", "message": "Received trade signal", "context": {"tweet_id": "1234567890", "symbol": "BTCUSDT", "side": "BUY", "position_pct": 0.1}, "performance": {"duration_ms": 45.2}}
{"timestamp": "2025-11-22T12:30:06.345678+08:00", "level": "INFO", "module": "exchange_binance_async", "func": "place_future_market_order", "line": 156, "component": "ORDER", "message": "Market order placed successfully", "context": {"symbol": "BTCUSDT", "side": "BUY", "quantity": 0.001, "order_id": "9876543210"}, "performance": {"duration_ms": 234.5}}
{"timestamp": "2025-11-22T12:30:10.456789+08:00", "level": "WARNING", "module": "risk_exit", "func": "monitor_loop", "line": 89, "component": "EXIT", "message": "Stop loss triggered", "context": {"position_id": "pos_123", "symbol": "BTCUSDT", "exit_price": 95000.0, "pnl": -125.5}, "performance": {"duration_ms": 12.3}}
```

### 11.2 相关文档链接

- [ARCHITECTURE.md](./ARCHITECTURE.md) - 系统架构设计
- [CLAUDE.md](../CLAUDE.md) - 项目主文档
- [IMPLEMENTATION_v1.4.0.md](../IMPLEMENTATION_v1.4.0.md) - 当前实现文档

---

**文档维护者**: 技术团队  
**最后审查**: 2025-11-22  
**文档版本**: v1.0.0