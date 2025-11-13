# Twitter 爬虫需求处理文档 (RPD)

**文档版本**: v1.0  
**创建日期**: 2025-11-11  
**作者**: Claude Code Assistant

---

## 1. 需求复述

### 1.1 目标
修改现有的 `twitter_crawler_functional.ipynb` 文件，实现爬取指定用户的最新推特消息功能。

### 1.2 具体需求
- 基于Twitter API接口文档 v1.0的规范
- 爬取2个指定用户的最新推文
- 数据清理和格式化
- 输出为CSV格式

### 1.3 成功判据
- ✅ API连接成功
- ✅ 获取指定用户的推文数据
- ✅ 数据结构化存储
- ✅ 生成CSV文件

---

## 2. 问题分析

### 2.1 当前代码问题
根据接口文档分析，现有代码存在以下问题：

1. **API路径错误**:
   - 当前: `https://api.twitterapi.io/v1/search`
   - 正确: `https://api.twitterapi.io/v1/user/{username}/tweets`

2. **参数格式不匹配**:
   - 当前使用search查询参数
   - 应使用用户名路径参数

3. **API响应格式差异**:
   - 需要适配新的响应结构

### 2.2 接口文档要点
- **基础URL**: `https://api.twitterapi.io/v1`
- **认证方式**: HTTP Header `x-api-key`
- **推文端点**: `/user/{username}/tweets`
- **支持参数**: count(数量限制)
- **响应格式**: JSON with success/data/message结构

---

## 3. 解决方案

### 3.1 核心修改点

#### 3.1.1 API配置更新
```python
# 当前配置
SEARCH_URL = f"{BASE_URL}/search"

# 修正配置
TWEETS_URL_TEMPLATE = f"{BASE_URL}/user/{{username}}/tweets"
```

#### 3.1.2 请求方法调整
```python
# 从搜索API改为用户推文API
def get_user_tweets_v2(session, username: str, count: int = 5):
    url = TWEETS_URL_TEMPLATE.format(username=username)
    params = {'count': min(count, 100)}  # API限制
    response = session.get(url, params=params, timeout=30)
```

#### 3.1.3 响应数据处理适配
```python
# 适配新的API响应格式
if response.status_code == 200:
    data = response.json()
    if data.get('success') and 'data' in data:
        tweets = data['data']
        return tweets
```

### 3.2 保持优点
- ✅ 函数式编程架构
- ✅ 单步调试友好
- ✅ 详细调试输出
- ✅ 错误处理机制

---

## 4. 实施计划

### 4.1 修改步骤
1. **更新API配置**
   - 修改URL模板
   - 调整参数格式

2. **重写数据获取函数**
   - 适配新的API端点
   - 处理新的响应格式

3. **测试验证**
   - API连接测试
   - 数据获取测试
   - 完整流程验证

### 4.2 质量保证
- 保持原有的调试输出
- 增强错误处理
- 验证数据完整性

---

## 5. 待确认问题

### 5.1 关键信息缺失
❓ **需要确认**: 要爬取的2个具体Twitter用户名是什么？

### 5.2 建议的默认用户
如果用户未指定，建议使用：
- `cz_binance` (币安创始人)
- `elonmusk` (特斯拉CEO)

### 5.3 数据量需求
- 每个用户获取多少条推文？
- 是否需要特定时间段的数据？

---

## 6. 风险评估

### 6.1 技术风险
- **API限制**: 需要注意速率限制(200 QPS)
- **数据格式变化**: 可能需要适配API响应变化

### 6.2 业务风险
- **权限问题**: 需要有效的API密钥
- **数据量**: 避免请求过多数据导致费用增加

### 6.3 应对措施
- 添加请求间隔控制
- 实现重试机制
- 添加使用量监控

---

## 7. 交付物

### 7.1 代码文件
- 修正后的 `twitter_crawler_functional.ipynb`

### 7.2 文档更新
- 更新相关说明文档
- 添加使用示例

### 7.3 测试验证
- 功能测试报告
- 性能基准测试

---

**文档状态**: 待用户确认关键信息  
**下一步**: 获取用户指定的2个Twitter用户名，开始代码修改