# 信号过滤设计文档 (简化版)

**版本**: v1.1.0
**最后更新**: 2025-11-23
**文档状态**: 已更新 (简化设计)

---

## 1. 概述

### 1.1 设计目标

本设计旨在提供一个极简、高效的信号过滤机制，确保只有高质量的交易信号进入执行阶段。核心原则是**删除过度设计，保留核心功能**。

### 1.2 核心原则

1.  **极度简化**: 移除复杂的评分系统和多维度评估。
2.  **核心保留**: 仅保留置信度过滤和黑名单过滤。
3.  **配置驱动**: 风险控制参数直接在 `config.py` 中定义，不作为独立过滤器。
4.  **数据留存**: 过滤统计信息必须持久化保存。

---

## 2. 过滤器架构

### 2.1 过滤器链

系统仅包含两个核心过滤器，按顺序执行：

```
┌─────────────────────────────────────┐
│  1. ConfidenceFilter (置信度)      │  ← 快速失败，基于AI评分
├─────────────────────────────────────┤
│  2. BlacklistFilter (黑名单)       │  ← 策略性过滤，基于配置
└─────────────────────────────────────┘
```

### 2.2 核心组件接口

```python
class SignalFilter(ABC):
    """信号过滤器抽象基类"""
    
    @abstractmethod
    async def filter(self, signal: TradeSignal) -> FilterResult:
        """过滤信号，返回过滤结果"""
        pass

@dataclass
class FilterResult:
    """过滤结果"""
    passed: bool                    # 是否通过过滤
    reason: Optional[str] = None    # 拒绝原因（如果未通过）
```

---

## 3. 过滤器实现

### 3.1 置信度过滤器 (ConfidenceFilter)

**功能**: 基于 AI 模型返回的置信度分数进行过滤。

**逻辑**:
- 检查 `signal.confidence` 是否大于等于配置的 `min_confidence`。
- 如果小于阈值，拒绝信号。

**配置**:
```python
# config.py
min_confidence = 0.75
```

### 3.2 黑名单过滤器 (BlacklistFilter)

**功能**: 过滤特定币种或用户。

**逻辑**:
- 检查 `signal.symbol` 是否在黑名单币种列表中。
- 检查 `signal.source_user` 是否在黑名单用户列表中。
- 如果匹配任意黑名单，拒绝信号。

**配置**:
```python
# config.py
blacklisted_symbols = ["DOGE", "SHIB"]
blacklisted_users = ["spam_bot"]
```

### 3.3 重复信号处理

**说明**: 重复信号过滤不再作为独立的过滤器存在。
**实现位置**: 在 AI 分析前的推文处理阶段，通过 `tweet_id` 进行去重。已处理过的推文直接跳过，不会生成信号进入过滤器链。

---

## 4. 风险控制 (配置化)

风险控制不再作为独立的过滤器逻辑，而是作为交易执行前的参数检查。相关参数直接在 `config.py` 中定义：

```python
# config.py

# 单笔交易风险限制
max_position_size_usdt = 1000.0  # 单笔最大金额
max_daily_trades = 10            # 每日最大交易次数

# 账户风险限制
min_account_balance = 500.0      # 最低账户余额
```

在生成订单时，直接读取这些配置进行校验。

---

## 5. 过滤统计与持久化

### 5.1 统计需求

必须记录所有被过滤掉的信号及其原因，用于后续分析和优化。

### 5.2 持久化存储

统计数据保存到本地 JSON 文件：`data/filter_stats.json`。

**数据结构**:
```json
{
  "last_updated": "2025-11-23T10:00:00",
  "total_signals": 100,
  "passed_signals": 20,
  "rejected_signals": 80,
  "rejection_reasons": {
    "low_confidence": 50,
    "blacklisted_symbol": 20,
    "blacklisted_user": 10
  },
  "recent_rejections": [
    {
      "time": "2025-11-23T09:55:00",
      "symbol": "DOGE",
      "reason": "blacklisted_symbol"
    }
  ]
}
```

**实现逻辑**:
- 每次过滤发生时，更新内存中的统计数据。
- 定期（如每5分钟）或在程序退出时将统计数据写入文件。

---

## 6. 总结

本设计移除了所有非必要组件，专注于最核心的信号筛选功能。通过置信度和黑名单两层过滤，配合配置化的风险控制，足以满足当前系统的安全需求。
