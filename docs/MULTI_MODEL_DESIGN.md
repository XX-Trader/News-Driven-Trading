# 多模型支持设计文档

**版本**: v1.0.0
**最后更新**: 2025-11-22
**文档状态**: 延迟实现（v3.0+）

---

## 1. 概述

### 1.1 设计目标

为 [`trading_bot`](trading_bot/) 项目提供多AI模型支持能力，通过模型路由和结果验证机制，提升AI分析的准确性、可靠性和容错性。

**重要说明**: 本设计为长期规划功能，当前版本(v2.x)暂不实现，将在v3.0或更高版本中根据实际需求逐步落地。

### 1.2 核心价值

- **准确性提升**: 多模型投票/加权，降低单一模型误判风险
- **可靠性增强**: 模型故障自动降级，确保系统持续可用
- **性能优化**: 并行调用策略，减少AI分析延迟

### 1.3 当前状态

当前系统已实现单模型（Poe API）支持，多模型功能为后续扩展预留接口。现有代码中的 `AIModelRouter` 为简化实现，仅支持单模型路由。

---

## 2. 模型路由策略

### 2.1 路由模式

系统支持三种路由模式，通过配置动态切换：

#### 2.1.1 最快返回模式（FIRST_COMPLETED）

```
┌─────────┐      ┌─────────┐      ┌─────────┐
│ Model A │      │ Model B │      │ Model C │
│ Claude  │      │  GPT-4  │      │ Gemini  │
└───┬─────┘      └───┬─────┘      └───┬─────┘
    │                │                │
    └───────┬────────┴────────┬───────┘
            ▼                 ▼
    ┌─────────────────────────────┐
    │  并行调用，取最快返回的结果  │
    │  其余任务自动取消            │
    └────────────┬────────────────┘
                 │
                 ▼
         ┌───────────────┐
         │  Trade Signal │
         └───────────────┘
```

**适用场景**: 对延迟敏感，需要快速响应的场景

**配置示例**:
```yaml
router_mode: "first_completed"
timeout: 30s
```

#### 2.1.2 一致性验证模式（CONSENSUS）

```
┌─────────┐      ┌─────────┐      ┌─────────┐
│ Model A │      │ Model B │      │ Model C │
│ Claude  │      │  GPT-4  │      │ Gemini  │
└───┬─────┘      └───┬─────┘      └───┬─────┘
    │                │                │
    └───────┬────────┴────────┬───────┘
            ▼                 ▼
    ┌─────────────────────────────┐
    │  等待所有模型返回结果        │
    │  ▼                           │
    │  一致性检查（投票/阈值）      │
    │  ▼                           │
    │  计算置信度                  │
    │  ▼                           │
    │  判断是否通过验证            │
    └────────────┬────────────────┘
                 │
        ┌────────┴────────┐
        ▼                 ▼
   ┌─────────┐      ┌──────────┐
   │ 通过    │      │ 不通过   │
   │ 执行交易 │      │  丢弃信号 │
   └─────────┘      └──────────┘
```

**适用场景**: 高价值信号，需要确保分析准确性的场景

**配置示例**:
```yaml
router_mode: "consensus"
required_agreement: 0.67  # 至少67%模型一致
min_confidence: 0.8      # 最小置信度阈值
timeout: 45s
```

#### 2.1.3 加权评分模式（WEIGHTED）

```
模型结果 → 权重分配 → 加权计算 → 最终决策

┌─────────┐    ┌─────────┐    ┌─────────┐
│ Model A │    │ Model B │    │ Model C │
│ Claude  │    │  GPT-4  │    │ Gemini  │
└───┬─────┘    └───┬─────┘    └───┬─────┘
    │              │              │
score: 0.8     score: 0.6     score: 0.9
weight: 0.5    weight: 0.3    weight: 0.2
    │              │              │
    └───────┬──────┴──────┬───────┘
            ▼             ▼
      ┌──────────────────────┐
      │ 加权平均:             │
      │ 0.8*0.5 + 0.6*0.3 + │
      │ 0.9*0.2 = 0.76       │
      └──────────┬───────────┘
                 ▼
         ┌───────────────┐
         │ 最终置信度:    │
         │     0.76      │
         └───────────────┘
```

**适用场景**: 各模型可靠性不同，需要差异化加权的场景

**配置示例**:
```yaml
router_mode: "weighted"
weights:
  claude: 0.5
  gpt-4: 0.3
  gemini: 0.2
min_confidence: 0.7
```

### 2.2 模型优先级策略

支持静态和动态两种优先级策略：

#### 2.2.1 静态优先级

```yaml
models:
  - name: "claude-3-opus"
    priority: 1  # 最高优先级
    enabled: true
    
  - name: "gpt-4"
    priority: 2
    enabled: true
    
  - name: "gemini-pro"
    priority: 3
    enabled: true
```

#### 2.2.2 动态优先级

基于实时监控指标动态调整：
- **成功率**: 近期调用成功率高的模型优先级提升
- **平均延迟**: 响应快的模型优先级提升
- **可用性**: 连续失败的模型自动降级
- **成本**: 高成本模型在非关键场景优先级降低

---

## 3. 模型结果验证机制

### 3.1 一致性检查算法

#### 3.1.1 标签一致性检查

```python
# 输入: 多模型返回的标签列表
labels = ["bullish", "bullish", "bearish", "bullish"]

# 步骤1: 统计各标签出现次数
counts = {
    "bullish": 3,
    "bearish": 1,
    "neutral": 0
}

# 步骤2: 计算一致性分数
consistency_score = max(counts.values()) / len(labels)
# 3 / 4 = 0.75

# 步骤3: 判断阈值
if consistency_score >= required_agreement:
    # 通过验证，采用多数标签
    final_label = max(counts, key=counts.get)  # "bullish"
else:
    # 未通过验证
    final_label = None
```

#### 3.1.2 置信度聚合算法

```python
# 输入: 模型结果列表
results = [
    {"label": "bullish", "score": 0.85, "model": "claude"},
    {"label": "bullish", "score": 0.72, "model": "gpt4"},
    {"label": "bearish", "score": 0.91, "model": "gemini"}
]

# 步骤1: 筛选一致的结果
majority_label = "bullish"  # 通过一致性检查得到
consistent_results = [r for r in results if r["label"] == majority_label]
# [
#   {"label": "bullish", "score": 0.85, "model": "claude"},
#   {"label": "bullish", "score": 0.72, "model": "gpt4"}
# ]

# 步骤2: 计算加权置信度
weights = {"claude": 0.5, "gpt4": 0.3}  # 配置中的权重

weighted_sum = sum(r["score"] * weights[r["model"]] for r in consistent_results)
# 0.85*0.5 + 0.72*0.3 = 0.425 + 0.216 = 0.641

weight_sum = sum(weights[r["model"]] for r in consistent_results)
# 0.5 + 0.3 = 0.8

final_confidence = weighted_sum / weight_sum if weight_sum > 0 else 0
# 0.641 / 0.8 = 0.80125 ≈ 0.80
```

### 3.2 结果有效性验证

#### 3.2.1 结构完整性检查

```python
# 必需字段验证
required_fields = ["label", "score", "symbol"]

for result in model_results:
    # 检查必需字段是否存在
    missing_fields = [f for f in required_fields if f not in result]
    if missing_fields:
        result["valid"] = False
        result["errors"] = f"Missing fields: {missing_fields}"
        continue
    
    # 检查数据类型
    if not isinstance(result["label"], str):
        result["valid"] = False
        result["errors"] = "label must be string"
        continue
    
    if not (0 <= result["score"] <= 1):
        result["valid"] = False
        result["errors"] = "score must be between 0 and 1"
        continue
    
    result["valid"] = True
```

#### 3.2.2 业务规则验证

```python
# 交易方向验证
valid_labels = ["bullish", "bearish", "neutral", "ignore"]

for result in model_results:
    if result["label"] not in valid_labels:
        result["valid"] = False
        result["errors"] = f"Invalid label: {result['label']}"
    
    # 交易对格式验证
    symbol = result.get("symbol", "")
    if not re.match(r'^[A-Z0-9]+USDT$', symbol):
        result["valid"] = False
        result["errors"] = f"Invalid symbol format: {symbol}"
```

### 3.3 置信度计算算法

#### 3.3.1 综合置信度公式

```
最终置信度 = 基础置信度 × 一致性系数 × 模型可靠性系数

其中:
- 基础置信度: 加权平均后的模型置信度
- 一致性系数: f(一致模型数/总模型数) → 0.7~1.0
- 模型可靠性系数: 基于历史成功率的动态系数
```

#### 3.3.2 动态可靠性系数

```python
# 模型历史表现数据库
model_reliability = {
    "claude": {
        "total_calls": 1000,
        "successful_calls": 920,
        "avg_latency": 2.3,
        "reliability_score": 0.92
    },
    "gpt4": {
        "total_calls": 850,
        "successful_calls": 800,
        "avg_latency": 3.1,
        "reliability_score": 0.94
    }
}

# 计算可靠性系数（指数平滑）
alpha = 0.1  # 平滑系数

for model_name, metrics in model_reliability.items():
    # 基础可靠性 = 成功率
    base_reliability = metrics["successful_calls"] / metrics["total_calls"]
    
    # 延迟惩罚（超过5秒的线性惩罚）
    latency_penalty = max(0, (metrics["avg_latency"] - 5) * 0.05)
    
    # 更新可靠性分数
    metrics["reliability_score"] = base_reliability - latency_penalty
```

---

## 4. 支持的模型类型

### 4.1 在线商业模型

| 模型提供商 | 模型名称 | 特点 | 适用场景 |
|------------|----------|------|----------|
| **Poe** | Kimi-K2-Thinking | 中文理解优秀 | 中文推文分析 |
| **Poe** | GPT-4 | 综合能力最强 | 复杂逻辑分析 |
| **Poe** | Claude-3-Opus | 逻辑严谨 | 风险控制场景 |
| **OpenAI** | GPT-4-Turbo | 低延迟 | 实时性要求高的场景 |
| **Anthropic** | Claude-3-Sonnet | 性价比高 | 批量处理 |
| **Google** | Gemini-Pro | 多模态支持 | 含图片的推文 |

### 4.2 开源本地模型

| 模型 | 参数量 | 部署要求 | 延迟 | 成本 |
|------|--------|----------|------|------|
| **LLaMA-2-70B** | 70B | A100-80GB×2 | 高 | 低 |
| **LLaMA-2-13B** | 13B | A100-40GB | 中 | 低 |
| **ChatGLM3-6B** | 6B | RTX 3090 | 低 | 低 |
| **Qwen-14B** | 14B | A100-40GB | 中 | 低 |

### 4.3 专用微调模型

- **Trading-Llama**: 基于交易数据微调的LLaMA模型
- **Crypto-BERT**: 针对加密货币领域的BERT模型（用于分类）
- **Sentiment-FinGPT**: 金融情绪分析专用模型

---

## 5. 模型配置管理

### 5.1 配置文件结构

```yaml
# config/ai_models.yaml
ai:
  enabled: true
  default_router_mode: "consensus"  # first_completed | consensus | weighted
  
  # 全局路由配置
  router_config:
    timeout: 45  # 路由超时时间（秒）
    max_concurrent_calls: 5  # 最大并发调用数
    
  # 一致性验证配置
  consensus:
    required_agreement: 0.67  # 一致性阈值（0-1）
    min_confidence: 0.75      # 最小置信度
    max_wait_models: 3        # 最多等待的模型数
    
  # 加权配置
  weighted:
    min_confidence: 0.70
    
  # 模型定义
  models:
    - name: "claude-primary"
      type: "anthropic"
      model: "claude-3-opus-20240229"
      api_key: "${ANTHROPIC_API_KEY}"
      base_url: "https://api.anthropic.com"
      enabled: true
      priority: 1
      weight: 0.5
      cost_per_1k: 0.015
      timeout: 30
      
    - name: "gpt4-backup"
      type: "openai"
      model: "gpt-4-turbo-preview"
      api_key: "${OPENAI_API_KEY}"
      base_url: "https://api.openai.com/v1"
      enabled: true
      priority: 2
      weight: 0.3
      cost_per_1k: 0.01
      timeout: 25
      
    - name: "local-llama"
      type: "local"
      model: "llama-2-13b"
      base_url: "http://localhost:8080"
      enabled: false
      priority: 3
      weight: 0.2
      timeout: 60
      
  # 验证规则
  validation_rules:
    required_fields: ["label", "score", "symbol"]
    valid_labels: ["bullish", "bearish", "neutral", "ignore"]
    min_confidence: 0.6
    max_confidence: 1.0
```

### 5.2 配置加载逻辑

```python
class ModelConfigLoader:
    def __init__(self, config_path: str):
        self.config_path = config_path
    
    def load(self) -> AIConfig:
        """加载并验证配置"""
        # 1. 读取YAML文件
        with open(self.config_path, 'r') as f:
            raw_config = yaml.safe_load(f)
        
        # 2. 环境变量替换
        self._substitute_env_vars(raw_config)
        
        # 3. 配置验证
        self._validate_config(raw_config)
        
        # 4. 模型实例化
        models = self._instantiate_models(raw_config["models"])
        
        return AIConfig(
            enabled=raw_config["enabled"],
            router_mode=raw_config["default_router_mode"],
            models=models,
            router_config=raw_config["router_config"]
        )
    
    def _substitute_env_vars(self, config: Dict):
        """递归替换环境变量占位符"""
        for key, value in config.items():
            if isinstance(value, str) and value.startswith("${"):
                env_var = value[2:-1]  # 提取变量名
                config[key] = os.getenv(env_var)
            elif isinstance(value, dict):
                self._substitute_env_vars(value)
```

---

## 6. 容错和降级策略

### 6.1 层级容错架构

```
┌─────────────────────────────────────────┐
│        应用层 (Trading App)              │
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│       路由层 (Model Router)              │
│  • 策略选择                              │
│  • 结果聚合                              │
└──────────────┬──────────────────────────┘
               │
    ┌──────────┼──────────┬──────────┐
    │          │          │          │
┌───▼───┐  ┌───▼───┐  ┌───▼───┐  ┌──▼───┐
│Model A│  │Model B│  │Model C│  │本地词库│
│在线   │  │在线   │  │离线   │  │降级  │
└───┬───┘  └───┬───┘  └───┬───┘  └───┬──┘
    │          │          │          │
    └───────┬──┴──────┬───┴──────┬───┘
            ▼         ▼          ▼
    ┌───────────────────────────┐
    │     熔断器 (Circuit       │
    │       Breaker)            │
    │  • 失败计数                │
    │  • 自动恢复                │
    └────────────┬──────────────┘
                 │
        ┌────────┴────────┐
        ▼                 ▼
   ┌─────────┐      ┌──────────┐
   │ 正常模式 │      │ 降级模式  │
   │ 多模型   │      │ 单模型/词库│
   └─────────┘      └──────────┘
```

### 6.2 熔断器机制

```python
class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold  # 失败阈值
        self.recovery_timeout = recovery_timeout    # 恢复等待时间
        self.failure_count = 0                      # 当前失败次数
        self.last_failure_time = None               # 最后失败时间
        self.state = "CLOSED"                       # CLOSED / OPEN / HALF_OPEN
        
    def call(self, func, *args, **kwargs):
        """包装函数调用，实现熔断逻辑"""
        
        if self.state == "OPEN":
            # 检查是否可以尝试恢复
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                self.state = "HALF_OPEN"
            else:
                raise Exception("Circuit breaker is OPEN")
        
        try:
            result = func(*args, **kwargs)
            # 成功调用
            self.on_success()
            return result
            
        except Exception as e:
            # 失败调用
            self.on_failure()
            raise e
    
    def on_success(self):
        """成功时重置失败计数"""
        self.failure_count = 0
        self.state = "CLOSED"
    
    def on_failure(self):
        """失败时增加计数，达到阈值后打开熔断器"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
```

### 6.3 降级策略

#### 6.3.1 模型级降级

```python
class FallbackStrategy:
    """降级策略管理"""
    
    def __init__(self, primary_models: List[str], fallback_models: List[str]):
        self.primary_models = primary_models
        self.fallback_models = fallback_models
        self.failed_models = set()
    
    def get_available_models(self) -> List[str]:
        """获取当前可用模型列表"""
        available = []
        
        # 优先使用主模型
        for model in self.primary_models:
            if model not in self.failed_models:
                available.append(model)
        
        # 主模型全部失败，使用降级模型
        if not available:
            for model in self.fallback_models:
                if model not in self.failed_models:
                    available.append(model)
        
        return available
    
    def mark_failed(self, model_name: str):
        """标记模型失败"""
        self.failed_models.add(model_name)
        
        # 触发告警（日志、邮件、钉钉等）
        self._trigger_alert(f"Model {model_name} failed")
```

#### 6.3.2 系统级降级

| 降级级别 | 触发条件 | 策略 | 性能影响 |
|----------|----------|------|----------|
| **Level 0** | 正常运行 | 多模型共识 | 正常 |
| **Level 1** | 30%模型失效 | 最快返回模式 | 延迟降低 |
| **Level 2** | 50%模型失效 | 单模型+简化验证 | 延迟降低50% |
| **Level 3** | 80%模型失效 | 关键词匹配 | 无AI延迟 |

---

## 7. 性能优化

### 7.1 连接池管理

```python
class AIClientPool:
    """AI客户端连接池"""
    
    def __init__(self, max_connections: int = 10):
        self.max_connections = max_connections
        self.connections = {}
        self.semaphore = asyncio.Semaphore(max_connections)
    
    async def get_client(self, model_name: str):
        """获取模型客户端（带连接复用）"""
        async with self.semaphore:
            if model_name not in self.connections:
                self.connections[model_name] = await self._create_client(model_name)
            
            return self.connections[model_name]
    
    async def _create_client(self, model_name: str):
        """创建模型客户端"""
        # Poe/OpenAI客户端
        if model_name in ["claude", "gpt4"]:
            return AsyncOpenAI(
                api_key=self._get_api_key(model_name),
                base_url=self._get_base_url(model_name),
                http_client=httpx.AsyncClient(
                    limits=httpx.Limits(
                        max_connections=100,
                        max_keepalive_connections=20,
                        keepalive_expiry=30.0
                    )
                )
            )
        
        # 本地模型客户端
        elif model_name == "local":
            return httpx.AsyncClient(
                base_url="http://localhost:8080",
                timeout=30.0
            )
```

### 7.2 结果缓存策略

#### 7.2.1 缓存层级

```python
class MultiLevelCache:
    """多级缓存系统"""
    
    def __init__(self):
        # L1: 内存缓存（LRU，10分钟）
        self.memory_cache = LRUCache(maxsize=1000, ttl=600)
        
        # L2: Redis缓存（1小时）
        self.redis_cache = RedisClient(host="localhost", port=6379)
        
        # L3: 文件缓存（24小时）
        self.file_cache = FileCache(cache_dir="cache/ai_results")
    
    async def get(self, key: str) -> Optional[AIResult]:
        """多级缓存查询"""
        # L1 内存缓存
        result = self.memory_cache.get(key)
        if result:
            return result
        
        # L2 Redis缓存
        result = await self.redis_cache.get(key)
        if result:
            self.memory_cache.set(key, result)  # 回填L1
            return result
        
        # L3 文件缓存
        result = self.file_cache.get(key)
        if result:
            await self.redis_cache.set(key, result)  # 回填L2
            self.memory_cache.set(key, result)       # 回填L1
            return result
        
        return None
```

#### 7.2.2 缓存键设计

```python
def generate_cache_key(tweet_text: str, model_name: str) -> str:
    """生成缓存键"""
    # 文本哈希
    text_hash = hashlib.md5(tweet_text.encode()).hexdigest()[:12]
    
    # 模型名称
    model_part = model_name.replace("-", "_")
    
    # 时间窗口（按小时）
    time_window = int(time.time() / 3600)
    
    return f"ai:v2:{model_part}:{text_hash}:{time_window}"
```

### 7.3 批量处理优化

```python
class BatchProcessor:
    """批量AI请求处理器"""
    
    def __init__(self, max_batch_size: int = 10, batch_timeout: float = 0.5):
        self.max_batch_size = max_batch_size
        self.batch_timeout = batch_timeout
        self.batch_queue = asyncio.Queue()
        self.processing_task = None
    
    async def add_request(self, request: AIRequest) -> AIResult:
        """添加请求到批次"""
        future = asyncio.Future()
        await self.batch_queue.put((request, future))
        
        # 延迟启动处理任务
        if not self.processing_task or self.processing_task.done():
            self.processing_task = asyncio.create_task(self._process_batch())
        
        return await future
    
    async def _process_batch(self):
        """批量处理逻辑"""
        batch = []
        deadline = time.time() + self.batch_timeout
        
        # 收集批次
        while len(batch) < self.max_batch_size and time.time() < deadline:
            try:
                request, future = await asyncio.wait_for(
                    self.batch_queue.get(),
                    timeout=deadline - time.time()
                )
                batch.append((request, future))
            except asyncio.TimeoutError:
                break
        
        # 批量调用（如果API支持）
        if batch:
            await self._call_batch(batch)
```

---

## 8. 使用示例

### 8.1 基础使用（单模型）

```python
from trading_bot.ai_base import AIModelRouter, AIInput
from trading_bot.config import load_config

async def basic_usage():
    # 加载配置
    config = load_config()
    
    # 初始化路由器
    router = AIModelRouter(config)
    
    # 准备输入
    ai_input = AIInput(
        text="BTC突破新高，目标10万美元",
        meta={"author": "crypto_influencer", "tweet_id": "12345"}
    )
    
    # 调用AI分析
    result = await router.analyze(ai_input)
    
    if result:
        print(f"标签: {result.label}")
        print(f"置信度: {result.score}")
        print(f"交易对: {result.meta.get('symbol')}")
    else:
        print("AI分析失败")
```

### 8.2 多模型共识模式

```python
# config/ai_models.yaml
ai:
  router_mode: "consensus"
  
  models:
    - name: "claude"
      type: "anthropic"
      model: "claude-3-opus"
      enabled: true
      weight: 0.4
      
    - name: "gpt4"
      type: "openai" 
      model: "gpt-4-turbo"
      enabled: true
      weight: 0.35
      
    - name: "local"
      type: "local"
      model: "llama-2-13b"
      enabled: true
      weight: 0.25
      
  consensus:
    required_agreement: 0.67  # 至少2个模型一致
    min_confidence: 0.75
```

```python
# 代码使用（与基础使用相同，配置驱动）
result = await router.analyze(ai_input)

# 结果包含一致性信息
if result:
    print(f"最终标签: {result.label}")
    print(f"最终置信度: {result.score}")
    print(f"共识模型数: {result.meta['consensus_count']}/3")
    print(f"一致性分数: {result.meta['consistency_score']:.2f}")
```

### 8.3 快速响应模式

```python
# config/ai_models.yaml
ai:
  router_mode: "first_completed"
  timeout: 20s  # 20秒超时
  
  models:
    - name: "fast-model"
      type: "anthropic"
      model: "claude-3-haiku"  # 快速模型
      enabled: true
      priority: 1
      
    - name: "backup"
      type: "openai"
      model: "gpt-3.5-turbo"
      enabled: true
      priority: 2
```

### 8.4 动态容错示例

```python
async def resilient_analysis():
    router = AIModelRouter(config)
    
    try:
        # 正常调用
        result = await router.analyze(ai_input)
        return result
        
    except RuntimeError as e:
        # 所有模型失败，降级到关键词匹配
        logger.warning(f"AI models failed: {e}, falling back to keyword matching")
        
        return fallback_keyword_matching(ai_input.text)

def fallback_keyword_matching(text: str) -> AIResult:
    """降级策略：关键词匹配"""
    text_lower = text.lower()
    
    if any(word in text_lower for word in ["buy", "long", "抄底"]):
        label = "bullish"
    elif any(word in text_lower for word in ["sell", "short", "逃顶"]):
        label = "bearish"
    else:
        label = "neutral"
    
    return AIResult(
        score=0.5,  # 降级结果的置信度较低
        label=label,
        meta={"source": "keyword_fallback", "reliable": False}
    )
```



---

## 12. 演进路线

### 12.1 短期（v2.1 - 2.3）

- [x] **设计多模型架构**: 完成本设计文档
- [ ] **实现基础路由**: 支持最快返回模式
- [ ] **集成2个商业模型**: Poe + OpenAI
- [ ] **基础监控**: 调用次数、延迟、成功率

### 12.2 中期（v3.0）

- [ ] **共识模式实现**: 一致性验证和投票机制
- [ ] **置信度算法**: 动态可靠性系数计算


---

## 13. 附录

### 13.1 术语表

| 术语 | 解释 |
|------|------|
| **Router Mode** | 模型路由模式（最快返回/共识/加权） |
| **Consensus** | 多模型结果一致性 |
| **Confidence** | 置信度，表示结果的可信程度 |
| **Circuit Breaker** | 熔断器，防止级联故障 |
| **Fallback** | 降级策略，备选方案 |
| **Multi-model** | 同时使用多个AI模型 |

### 13.2 配置文件示例

完整的配置示例见 [`config/ai_models.example.yaml`](config/ai_models.example.yaml)

### 13.3 接口文档

详细的API接口文档见 [`docs/AI_API_REFERENCE.md`](docs/AI_API_REFERENCE.md)

---

**文档维护者**: 技术团队  
**最后审查**: 2025-11-22  
**文档版本**: v1.0.0