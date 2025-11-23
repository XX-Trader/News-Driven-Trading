# News-Driven-Trading 项目目录结构调整记录
> > 
> > **版本**: 1.1.0  
> > **日期**: 2025-11-23 17:56 (UTC+8)  
> > **状态**: ✅ 已完成  
> > 
> > ---
> 
> ## 一、调整背景
> 
> 项目目录结构进行了调整，主要变更：
> - `提示词.txt` 文件从 `推特抢跑/` 目录移动到 `trading_bot/` 目录
> - 需要更新所有硬编码路径引用，确保代码能正确找到文件
> 
> ---
> 
> ## 二、修复内容
> 
> ### 2.1 修复文件路径
> 
> #### 1. `trading_bot/tweet_analyzer.py`
> **问题**：第74-75行硬编码路径指向旧的目录结构
> ```python
> # 修复前
> base_dir = Path(__file__).resolve().parent.parent
> prompt_path = base_dir / "推特抢跑" / "提示词.txt"
> 
> # 修复后
> base_dir = Path(__file__).resolve().parent
> prompt_path = base_dir / "提示词.txt"
> ```
> 
> #### 2. `推特抢跑/twitter_crawler_functional_min.py`
> **问题**：第156行使用相对路径，无法找到文件
> ```python
> # 修复前
> promot = read_text("提示词.txt")
> 
> # 修复后
> prompt_path = os.path.join(os.path.dirname(__file__), os.pardir, "trading_bot", "提示词.txt")
> promot = read_text(prompt_path)
> ```
> 
> #### 3. `trading_bot/twitter_source.py` (v1.1.0 新增修复)
> **问题**：第67-68行路径错误，指向不存在的 `推特抢跑/twitter_media/` 目录
> ```python
> # 修复前
> base_dir = Path(__file__).resolve().parent.parent  # 指向项目根目录
> logs_dir = base_dir / "推特抢跑" / "twitter_media" / "user_logs"
> 
> # 修复后
> base_dir = Path(__file__).resolve().parent  # 指向 trading_bot/ 目录
> logs_dir = base_dir / "twitter_media" / "user_logs"
> ```
> 
> ---
> 
> ## 三、验证结果
> 
> ### 3.1 路径验证
> 
> **验证 1：`trading_bot/tweet_analyzer.py`**
> - `Path(__file__).resolve().parent` → `d:/学习资料/量化交易/News-Driven-Trading/trading_bot/`
> - `prompt_path` → `d:/学习资料/量化交易/News-Driven-Trading/trading_bot/提示词.txt`
> - ✅ 文件存在，路径正确
> 
> **验证 2：`推特抢跑/twitter_crawler_functional_min.py`**
> - `os.path.dirname(__file__)` → `d:/学习资料/量化交易/News-Driven-Trading/推特抢跑/`
> - `prompt_path` → `d:/学习资料/量化交易/News-Driven-Trading/推特抢跑/../trading_bot/提示词.txt`
> - 解析后 → `d:/学习资料/量化交易/News-Driven-Trading/trading_bot/提示词.txt`
> - ✅ 文件存在，路径正确
> 
> **验证 3：`trading_bot/twitter_source.py` (v1.1.0 新增)**
> - `Path(__file__).resolve().parent` → `d:/学习资料/量化交易/News-Driven-Trading/trading_bot/`
> - `logs_dir` → `d:/学习资料/量化交易/News-Driven-Trading/trading_bot/twitter_media/user_logs`
> - ✅ 目录存在，路径正确
> 
> ### 3.2 影响范围
> 
> **受影响的文件**：
> 
> - **添加新文件**：避免硬编码路径，使用 `Path(__file__).resolve().parent` 或 `os.path.dirname(__file__)` 构建路径
> - **移动文件**：如果再次移动文件，需要更新所有相关文件的路径引用
> 
> ---
> 
> ## 五、相关文件
> 
> - **提示词文件**：`trading_bot/提示词.txt`
> - **修复记录**：
>   - `trading_bot/tweet_analyzer.py` (第73-75行)
>   - `推特抢跑/twitter_crawler_functional_min.py` (第157-158行)
> 
> ---
> 
> **最后更新**: 2025-11-23 17:40 (UTC+8)
> 