"""
trading_bot.config

集中管理交易系统的配置，避免在业务逻辑中散落硬编码。

当前仅提供简单配置骨架，后续可以根据需要扩展为从环境变量 / 配置文件加载。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import os


# --------------------
# 数据类定义
# --------------------


@dataclass
class ProxyConfig:
    """网络代理相关配置"""

    google_check_enabled: bool = True
    force_proxy: bool = False
    use_proxy_by_default: bool = False
    proxy_url: str = "http://127.0.0.1:1080"
    google_test_url: str = "https://www.google.com"
    google_timeout_sec: float = 3.0


@dataclass
class ExchangeConfig:
    """交易所相关配置（当前以 Binance 为主）"""

    name: str = "binance"
    api_key_env: str = "BINANCE_API_KEY"
    api_secret_env: str = "BINANCE_API_SECRET"
    base_url: str = "https://api.binance.com"
    recv_window: int = 50000
    request_timeout_sec: float = 10.0
    use_testnet: bool = False  # 虽然当前目标是实盘，但仍保留 testnet 选项
    dry_run: bool = False  # 强烈建议开发/调试阶段保持 True，实盘时显式改为 False

    quote_asset_for_position: str = "USDT"  # 用于计算仓位的计价资产，比如 USDT
    
    # 交易对精度配置（修复：将硬编码值移至配置）
    min_qty: float = 0.001  # 最小下单数量（BTC为例）
    step_size: float = 0.001  # 最小变动单位（步长）


@dataclass
class RiskConfig:
    """风控相关全局配置"""

    default_stop_loss_pct: float = 0.01  # 默认止损 1%
    # 默认分批止盈方案：例如 +2% 平 50%，+5% 平剩余 50%
    default_take_profit_scheme: List[Dict[str, float]] = field(
        default_factory=lambda: [
            {"take_profit": 0.02, "size_pct": 0.5},
            {"take_profit": 0.05, "size_pct": 0.5},
        ]
    )
    default_position_pct: float = 0.02  # 默认单次开仓 2% 资金
    exit_strategy_type: str = "basic"  # 当前只有 basic，未来可扩展 demark / ai 等


@dataclass
class AIConfig:
    """AI 模型相关配置"""

    # 是否启用 AI 分析
    enabled: bool = True

    # AI 路由超时时间（秒）
    router_timeout_sec: float = 60.0

    # ===== Poe(OpenAI 兼容)配置（当前直接硬编码，方便你本地快速联调。
    # 实盘前强烈建议改为从环境变量或独立配置文件加载）=====
    poe_api_key: str = (
        "OboBsTgiTVCQs15npJuWcIUVIoOW7Spz1XzyHOcc8Zk"  # 示例 Key
    )
    poe_base_url: str = "https://api.poe.com/v1"
    # poe_model: str = "gpt-5.1"
    poe_model: str = "Kimi-K2-Thinking"

    # AI代理配置（MVP新增）
    use_proxy: bool = False  # 是否启用代理（默认真盘直连，调试可改为True）
    proxy_config: Dict[str, str] = field(default_factory=lambda: {
        "http": "http://localhost:1080",
        "https": "http://localhost:1080"
    })  # 代理URL配置（仅当use_proxy=True时生效）

    # 预留多模型路由的配置（当前不使用）
    models: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class TwitterAPIConfig:
    """Twitter 推文接口配置（当前使用 twitterapi.io 服务）"""

    # 接口密钥，放在请求头 X-API-Key 中
    api_key: str = "new1_58fe956453e744e4844728c68ba187d4"

    # 基础域名，便于后续扩展不同 endpoint，避免到处硬编码
    api_base: str = "https://api.twitterapi.io"

    # 用户最近推文 API 的路径部分
    # 示例完整 URL: f"{api_base}{user_last_tweets_path}?username=xxx&limit=10"
    user_last_tweets_path: str = "/twitter/user/last_tweets"

    # 用户简介映射表：用于 AI 分析时补充作者背景信息
    # 硬编码多个行业影响力人物，便于 AI 理解其身份背景与发言可信度
    # 后续可改为从 CSV/JSON 文件动态加载
    user_intro_mapping: Dict[str, str] = field(
        default_factory=lambda: {
            "cz_binance": "BINANCE创始人，全球最大加密货币交易所龙头",
            "haydenzadams": "Uniswap协议创始人，DeFi领域先驱",
            "elonmusk": "特斯拉、SpaceX创始人，科技与加密领域意见领袖",
            "VitalikButerin": "以太坊创始人，区块链技术核心架构师",
            "justinsuntron": "TRON创始人，数字资产倡导者",
            "SBF_FTX": "FTX交易所创始人，加密衍生品领域专家",
            "aantonop": "比特币先驱，区块链技术布道者",
            "DocumentingBTC": "比特币与闪电网络观察者",
            "APompliano": "加密资产投资专家，市场分析师",
            "CryptoByzantine": "区块链安全与共识机制研究者",
        }
    )

    @property
    def user_last_tweets_url(self) -> str:
        """组合完整的最近推文 URL"""
        return f"{self.api_base}{self.user_last_tweets_path}"


@dataclass
class AppConfig:
    """应用级整体配置"""

    proxy: ProxyConfig = field(default_factory=ProxyConfig)
    exchange: ExchangeConfig = field(default_factory=ExchangeConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    ai: AIConfig = field(default_factory=AIConfig)
    twitter_api: TwitterAPIConfig = field(default_factory=TwitterAPIConfig)


# --------------------
# 加载配置入口
# --------------------


def load_env_var(name: str, default: Optional[str] = None) -> Optional[str]:
    """从环境变量中读取值，若不存在则返回 default。"""
    return os.environ.get(name, default)


def load_config() -> AppConfig:
    """
    构建并返回应用配置。

    当前实现：
    - 大部分值用 dataclass 默认值；
    - 敏感信息优先从环境变量读取，若没有则使用代码中的“开发环境默认值”（你当前提供的 key）；
    - 后续可以改成从独立配置文件加载。
    """
    app_config = AppConfig()

    # --------------------
    # Binance API Key 处理
    # --------------------
    api_key_env_name = app_config.exchange.api_key_env
    api_secret_env_name = app_config.exchange.api_secret_env

    # 1. 优先尝试从环境变量读取
    api_key = load_env_var(api_key_env_name)
    api_secret = load_env_var(api_secret_env_name)

    # 2. 如果环境变量不存在，就使用你当前提供的 key（仅作为开发环境默认值）
    if api_key is None:
        api_key = "sFgmh9GNjGpUyWZ1ebI7HVMRDXHTFzJ4t8VJj08K1EmcTf6w4C9vWVcDuXqdW02t"
    if api_secret is None:
        api_secret = "c5ios8fEtgrvjpRAWyryInzRFyqAsBLBxFIW7AUoxjdpKEOdyGNaZCsAOg54WKTD"

    # 3. 将“解析后的 key/secret”挂在 exchange 配置上，供后续客户端使用
    #    注意：下划线前缀表示“内部使用字段”，后续如果要改回纯环境变量方式，直接删掉这两行即可。
    setattr(app_config.exchange, "_resolved_api_key", api_key)
    setattr(app_config.exchange, "_resolved_api_secret", api_secret)

    # --------------------
    # DRY_RUN 覆盖逻辑
    # --------------------
    dry_run_env = load_env_var("TRADING_BOT_DRY_RUN")
    if dry_run_env is not None:
        app_config.exchange.dry_run = dry_run_env.lower() in {"1", "true", "yes", "on"}

    return app_config