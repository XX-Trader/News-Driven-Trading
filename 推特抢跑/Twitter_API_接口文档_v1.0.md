# Twitter API 接口文档 v1.0

## 概述

TwitterAPI.io 是一个第三方的Twitter API服务，提供比官方Twitter API更便宜、更高效的解决方案。

### 关键特性
- **稳定性**：经过1000K+ API调用验证
- **性能**：平均响应时间700ms
- **高QPS**：每个客户端支持最多200 QPS
- **易用性**：遵循标准OpenAPI规范的RESTful API设计
- **成本效益**：相比官方API节省96%的费用

### 定价信息
- **推文数据**：$0.15/1k条推文
- **用户资料**：$0.18/1k个用户资料
- **关注者数据**：$0.15/1k个关注者
- **最低收费**：每次请求$0.00015（即使没有返回数据）
- **特殊优惠**：学生和研究机构享有折扣价格 🎓

---

## 认证

所有API请求都需要进行身份验证。请参考认证文档获取详细信息。

---

## API端点

### 用户相关API (User Endpoints)

#### 1. 批量获取用户信息 (Batch Get User Info By UserIds)
- **方法**: GET
- **路径**: `/api-reference/endpoint/batch_get_user_by_userids`
- **描述**: 通过用户ID批量获取用户信息
- **参数**: 
  - `userIds`: 用户ID数组
- **返回值**: 用户信息对象数组

#### 2. 获取用户信息 (Get User Info)
- **方法**: GET
- **路径**: `/api-reference/endpoint/get_user_by_username`
- **描述**: 通过用户名获取用户信息
- **参数**:
  - `username`: Twitter用户名
- **返回值**: 用户详细信息对象

#### 3. 获取用户最新推文 (Get User Last Tweets)
- **方法**: GET
- **路径**: `/api-reference/endpoint/get_user_last_tweets`
- **描述**: 获取指定用户的最新推文
- **参数**:
  - `username`: Twitter用户名
  - `count`: 可选，返回推文数量
- **返回值**: 推文对象数组

#### 4. 获取用户关注者 (Get User Followers)
- **方法**: GET
- **路径**: `/api-reference/endpoint/get_user_followers`
- **描述**: 获取指定用户的关注者列表
- **参数**:
  - `username`: Twitter用户名
  - `count`: 可选，返回数量限制
  - `cursor`: 可选，分页游标
- **返回值**: 关注者用户对象数组

#### 5. 获取用户关注的人 (Get User Followings)
- **方法**: GET
- **路径**: `/api-reference/endpoint/get_user_followings`
- **描述**: 获取指定用户关注的人列表
- **参数**:
  - `username`: Twitter用户名
  - `count`: 可选，返回数量限制
  - `cursor`: 可选，分页游标
- **返回值**: 被关注用户对象数组

#### 6. 获取用户提及 (Get User Mentions)
- **方法**: GET
- **路径**: `/api-reference/endpoint/get_user_mention`
- **描述**: 获取提及指定用户的推文
- **参数**:
  - `username`: Twitter用户名
  - `count`: 可选，返回数量限制
- **返回值**: 提及推文对象数组

#### 7. 检查关注关系 (Check Follow Relationship)
- **方法**: GET
- **路径**: `/api-reference/endpoint/check_follow_relationship`
- **描述**: 检查两个用户之间的关注关系
- **参数**:
  - `sourceUsername`: 源用户名
  - `targetUsername`: 目标用户名
- **返回值**: 关注关系状态对象

#### 8. 按关键词搜索用户 (Search user by keyword)
- **方法**: GET
- **路径**: `/api-reference/endpoint/search_user`
- **描述**: 根据关键词搜索用户
- **参数**:
  - `keyword`: 搜索关键词
  - `count`: 可选，返回数量限制
- **返回值**: 匹配用户对象数组

#### 9. 获取用户认证关注者 (Get User Verified Followers)
- **方法**: GET
- **路径**: `/api-reference/endpoint/get_user_verified_followers`
- **描述**: 获取指定用户的认证关注者
- **参数**:
  - `username`: Twitter用户名
  - `count`: 可选，返回数量限制
- **返回值**: 认证关注者用户对象数组

---

### 推文相关API (Tweet Endpoints)

#### 1. 根据ID获取推文 (Get Tweets by IDs)
- **方法**: GET
- **路径**: `/api-reference/endpoint/get_tweet_by_ids`
- **描述**: 通过推文ID获取推文详情
- **参数**:
  - `tweetIds`: 推文ID数组
- **返回值**: 推文对象数组

#### 2. 获取推文回复 (Get Tweet Replies)
- **方法**: GET
- **路径**: `/api-reference/endpoint/get_tweet_reply`
- **描述**: 获取指定推文的回复
- **参数**:
  - `tweetId`: 推文ID
  - `count`: 可选，返回数量限制
- **返回值**: 回复推文对象数组

#### 3. 获取推文引用 (Get Tweet Quotations)
- **方法**: GET
- **路径**: `/api-reference/endpoint/get_tweet_quote`
- **描述**: 获取引用指定推文的推文
- **参数**:
  - `tweetId`: 推文ID
  - `count`: 可选，返回数量限制
- **返回值**: 引用推文对象数组

#### 4. 获取推文转发者 (Get Tweet Retweeters)
- **方法**: GET
- **路径**: `/api-reference/endpoint/get_tweet_retweeter`
- **描述**: 获取转发指定推文的用户
- **参数**:
  - `tweetId`: 推文ID
  - `count`: 可选，返回数量限制
- **返回值**: 转发用户对象数组

#### 5. 获取推文线程上下文 (Get Tweet Thread Context)
- **方法**: GET
- **路径**: `/api-reference/endpoint/get_tweet_thread_context`
- **描述**: 获取推文所在线程的完整上下文
- **参数**:
  - `tweetId`: 推文ID
- **返回值**: 线程推文对象数组

#### 6. 获取文章 (Get Article)
- **方法**: GET
- **路径**: `/api-reference/endpoint/get_article`
- **描述**: 获取Twitter文章详情
- **参数**:
  - `articleId`: 文章ID
- **返回值**: 文章详情对象

#### 7. 高级搜索 (Advanced Search)
- **方法**: GET
- **路径**: `/api-reference/endpoint/tweet_advanced_search`
- **描述**: 使用高级过滤器搜索推文
- **参数**:
  - `query`: 搜索查询
  - `startDate`: 可选，开始日期
  - `endDate`: 可选，结束日期
  - `lang`: 可选，语言代码
  - `count`: 可选，返回数量限制
- **返回值**: 匹配推文对象数组

---

### 列表相关API (List Endpoints)

#### 1. 获取列表关注者 (Get List Followers)
- **方法**: GET
- **路径**: `/api-reference/endpoint/get_list_followers`
- **描述**: 获取Twitter列表的关注者
- **参数**:
  - `listId`: 列表ID
  - `count`: 可选，返回数量限制
- **返回值**: 列表关注者对象数组

#### 2. 获取列表成员 (Get List Members)
- **方法**: GET
- **路径**: `/api-reference/endpoint/get_list_members`
- **描述**: 获取Twitter列表的成员
- **参数**:
  - `listId`: 列表ID
  - `count`: 可选，返回数量限制
- **返回值**: 列表成员对象数组

---

### 社区相关API (Community Endpoints)

#### 1. 根据ID获取社区信息 (Get Community Info By Id)
- **方法**: GET
- **路径**: `/api-reference/endpoint/get_community_by_id`
- **描述**: 获取Twitter社区的详细信息
- **参数**:
  - `communityId`: 社区ID
- **返回值**: 社区信息对象

#### 2. 获取社区成员 (Get Community Members)
- **方法**: GET
- **路径**: `/api-reference/endpoint/get_community_members`
- **描述**: 获取社区成员列表
- **参数**:
  - `communityId`: 社区ID
  - `count`: 可选，返回数量限制
- **返回值**: 社区成员对象数组

#### 3. 获取社区管理员 (Get Community Moderators)
- **方法**: GET
- **路径**: `/api-reference/endpoint/get_community_moderators`
- **描述**: 获取社区管理员列表
- **参数**:
  - `communityId`: 社区ID
- **返回值**: 社区管理员对象数组

#### 4. 获取社区推文 (Get Community Tweets)
- **方法**: GET
- **路径**: `/api-reference/endpoint/get_community_tweets`
- **描述**: 获取社区内的推文
- **参数**:
  - `communityId`: 社区ID
  - `count`: 可选，返回数量限制
- **返回值**: 社区推文对象数组

#### 5. 搜索所有社区推文 (Search Tweets From All Community)
- **方法**: GET
- **路径**: `/api-reference/endpoint/get_all_community_tweets`
- **描述**: 在所有社区中搜索推文
- **参数**:
  - `query`: 搜索查询
  - `count`: 可选，返回数量限制
- **返回值**: 匹配推文对象数组

---

### 趋势相关API (Trends)

#### 1. 获取趋势 (Get Trends)
- **方法**: GET
- **路径**: `/api-reference/endpoint/get_trends`
- **描述**: 获取当前热门趋势话题
- **参数**:
  - `woeid`: 可选，地理位置ID（默认为全球）
- **返回值**: 趋势话题对象数组

---

### 账户相关API (My Endpoint)

#### 1. 获取我的账户信息 (Get My Account Info)
- **方法**: GET
- **路径**: `/api-reference/endpoint/get_my_info`
- **描述**: 获取当前认证用户的账户信息
- **返回值**: 用户账户信息对象

---

### Webhook/Websocket过滤规则API

#### 1. 添加过滤规则 (Add Webhook/Websocket Tweet Filter Rule)
- **方法**: POST
- **路径**: `/api-reference/endpoint/add_webhook_rule`
- **描述**: 添加推文过滤规则用于Webhook或WebSocket
- **参数**:
  - `rule`: 过滤规则对象
- **返回值**: 创建的规则对象

#### 2. 获取所有过滤规则 (Get ALL test Webhook/Websocket Tweet Filter Rules)
- **方法**: GET
- **路径**: `/api-reference/endpoint/get_webhook_rules`
- **描述**: 获取所有测试环境的过滤规则
- **返回值**: 过滤规则对象数组

#### 3. 更新过滤规则 (Update Webhook/Websocket Tweet Filter Rule)
- **方法**: POST
- **路径**: `/api-reference/endpoint/update_webhook_rule`
- **描述**: 更新现有的过滤规则
- **参数**:
  - `ruleId`: 规则ID
  - `rule`: 更新的规则对象
- **返回值**: 更新后的规则对象

#### 4. 删除过滤规则 (Delete Webhook/Websocket Tweet Filter Rule)
- **方法**: DELETE
- **路径**: `/api-reference/endpoint/delete_webhook_rule`
- **描述**: 删除指定的过滤规则
- **参数**:
  - `ruleId`: 规则ID
- **返回值**: 删除操作结果

---

### 流式API (Stream Endpoint)

#### 1. 添加用户到监控列表 (Add a twitter user to monitor his tweets)
- **方法**: POST
- **路径**: `/api-reference/endpoint/add_user_to_monitor_tweet`
- **描述**: 添加Twitter用户到推文监控列表
- **参数**:
  - `username`: 要监控的用户名
- **返回值**: 添加操作结果

#### 2. 从监控列表移除用户 (Remove a user from monitor list)
- **方法**: POST
- **路径**: `/api-reference/endpoint/remove_user_to_monitor_tweet`
- **描述**: 从推文监控列表中移除用户
- **参数**:
  - `username`: 要移除的用户名
- **返回值**: 移除操作结果

---

### 登录API (已弃用)

#### 1. 通过邮箱或用户名登录 (Login Step 1: by email or username)
- **方法**: POST
- **路径**: `/api-reference/endpoint/login_by_email_or_username`
- **描述**: 登录步骤1：通过邮箱或用户名
- **参数**:
  - `emailOrUsername`: 邮箱或用户名
- **返回值**: 登录会话信息

#### 2. 通过2FA代码登录 (Login Step 2: by 2fa code)
- **方法**: POST
- **路径**: `/api-reference/endpoint/login_by_2fa`
- **描述**: 登录步骤2：通过双因素认证代码
- **参数**:
  - `code`: 2FA验证码
  - `sessionToken`: 步骤1获得的会话令牌
- **返回值**: 完整的认证令牌

---

### 推文操作API (已弃用)

#### 1. 上传图片 (Upload Image)
- **方法**: POST
- **路径**: `/api-reference/endpoint/upload_tweet_image`
- **描述**: 上传图片用于推文
- **参数**:
  - `image`: 图片文件
- **返回值**: 上传的图片信息对象

#### 2. 发布/回复/引用推文 (Post/reply/quote a tweet)
- **方法**: POST
- **路径**: `/api-reference/endpoint/create_tweet`
- **描述**: 创建新推文、回复或引用推文
- **参数**:
  - `text`: 推文内容
  - `replyToTweetId`: 可选，回复的推文ID
  - `quoteTweetId`: 可选，引用的推文ID
  - `mediaIds`: 可选，媒体ID数组
- **返回值**: 创建的推文对象

#### 3. 点赞推文 (Like a tweet)
- **方法**: POST
- **路径**: `/api-reference/endpoint/like_tweet`
- **描述**: 点赞指定的推文
- **参数**:
  - `tweetId`: 推文ID
- **返回值**: 点赞操作结果

#### 4. 转发推文 (Retweet a tweet)
- **方法**: POST
- **路径**: `/api-reference/endpoint/retweet_tweet`
- **描述**: 转发指定的推文
- **参数**:
  - `tweetId`: 推文ID
- **返回值**: 转发操作结果

---

## 通用参数

### 分页参数
大多数支持列表返回的API都支持分页：
- `count`: 限制返回结果数量（默认值通常为20，最大值通常为100）
- `cursor`: 分页游标，用于获取下一页结果

### 响应格式
所有API响应都采用JSON格式，包含以下通用字段：
```json
{
  "success": true,
  "data": [...],
  "message": "操作成功",
  "rateLimit": {
    "remaining": 999,
    "resetTime": 1640995200
  }
}
```

---

## 频率限制

### 基础限制
- **每秒请求限制**: 每个客户端最多200 QPS
- **每日请求限制**: 根据订阅等级不同而有所差异

### 速率限制响应头
当触发速率限制时，API会返回以下信息：
- `X-RateLimit-Limit`: 该端点的请求限制总数
- `X-RateLimit-Remaining`: 剩余的请求次数
- `X-RateLimit-Reset`: 限制重置的时间戳

---

## 错误处理

### 标准错误响应
```json
{
  "success": false,
  "error": {
    "code": "INVALID_PARAMETER",
    "message": "参数无效",
    "details": "用户名不能为空"
  }
}
```

### 常见错误代码
- `INVALID_PARAMETER`: 参数无效
- `UNAUTHORIZED`: 未授权访问
- `RATE_LIMIT_EXCEEDED`: 超出速率限制
- `RESOURCE_NOT_FOUND`: 资源不存在
- `INTERNAL_ERROR`: 服务器内部错误

---

## 使用示例

### 获取用户信息示例
```javascript
const response = await fetch('https://api.twitterapi.io/v1/user/elonmusk', {
  headers: {
    'Authorization': 'Bearer YOUR_API_KEY'
  }
});

const userData = await response.json();
console.log(userData);
```

### 搜索推文示例
```javascript
const response = await fetch('https://api.twitterapi.io/v1/search?q=bitcoin&count=10', {
  headers: {
    'Authorization': 'Bearer YOUR_API_KEY'
  }
});

const searchResults = await response.json();
console.log(searchResults);
```

---

## 更新日志

### v1.0 (2025-11-11)
- 初始版本发布
- 包含所有主要API端点文档
- 添加价格和性能信息
- 完整的错误处理说明

---

## 联系支持

- **官方文档**: https://docs.twitterapi.io
- **Telegram支持**: https://t.me/kaitoeasyapivip
- **开始使用**: https://twitterapi.io

---

*本文档最后更新时间：2025-11-11*