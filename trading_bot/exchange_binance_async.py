"""
trading_bot.exchange_binance_async

Binance 异步 REST / Futures 适配（简化版，参考 binance.Binance 类的关键逻辑）：

- 现货接口（保留，以后需要可以补充）：
  - get_balance: 查询指定资产余额 (/api/v3/account)
  - get_latest_price: 查询交易对最新价格（ticker price）

- 合约接口（本项目下单主要使用 U 本位永续合约）：
  - place_future_market_order: 在合约账户下市价开仓/平仓（支持 LONG/SHORT + BUY/SELL）
  - set_dual_position_mode: 设置双向持仓模式 (/fapi/v1/positionSide/dual)
  - change_leverage: 调整单个 symbol 的杠杆倍数 (/fapi/v1/leverage)
  - get_future_balance: 查询 U 本位合约账户余额 (/fapi/v2/account)

注意：
- 代码风格参考了根目录的 binance.Binance，但改成异步 aiohttp 实现；
- 所有 HTTP 调用直接使用 aiohttp.ClientSession，代理逻辑在本模块中根据配置直接处理；
- API KEY 已在 config.load_config() 中解析为 exchange._resolved_api_key/_resolved_api_secret；
- 是否真实下单由 ExchangeConfig.dry_run 控制；
- 当前只实现项目最需要的最小子集，未做完备错误分类与限频处理，后续可以按需扩展。
"""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any, Dict, Optional

import aiohttp

try:
    from config import AppConfig, ExchangeConfig
except ImportError:
    from .config import AppConfig, ExchangeConfig

# Note: network module dependency removed - session creation is now inline

BINANCE_TIMESTAMP_MARGIN_MS = 1000  # 本地时间与服务器时间的安全边际


def format_quantity_for_binance(quantity: float, step_size: float = 0.001) -> str:
    """
    将数量格式化为符合 Binance API 要求的字符串格式。
    
    Binance 要求：
    - 数量必须符合 step_size 的精度
    - 必须格式化为字符串，避免浮点数精度问题
    
    参数：
    - quantity: 原始数量
    - step_size: 最小变动单位（默认 0.001）
    
    返回：
    - 格式化后的数量字符串
    """
    if step_size <= 0:
        # 如果 step_size 无效，使用默认精度 8 位小数
        return f"{quantity:.8f}".rstrip('0').rstrip('.')
    
    # 计算需要保留的小数位数
    # 例如：step_size=0.001 -> 3位小数，step_size=0.01 -> 2位小数
    decimal_places = 0
    temp = step_size
    while temp < 1:
        temp *= 10
        decimal_places += 1
    
    # 格式化数量
    formatted = f"{quantity:.{decimal_places}f}"
    
    # 移除末尾的0和小数点
    return formatted.rstrip('0').rstrip('.')


class BinanceAsyncClient:
    """
    Binance 异步 REST/Futures 客户端（简化版）。

    关键特性：
    - 使用 config.exchange 中的真实 base_url（现货）与 futures_base_url（合约）；
    - API key/secret 从 config.exchange._resolved_api_key/_resolved_api_secret 中读取；
    - 所有 HTTP 请求通过 trading_bot.network.create_http_client 统一创建 session + 代理；
    - 默认在合约端按「双向持仓 + 20 倍杠杆」下 U 本位永续合约单。
    """

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.exchange_conf: ExchangeConfig = config.exchange

        # API key / secret 从 config.exchange 中预先解析好的字段读取
        # 这些字段在 config.load_config() 中已经处理了「环境变量优先，缺失则用硬编码默认值」的逻辑。
        self.api_key: Optional[str] = getattr(
            self.exchange_conf, "_resolved_api_key", None
        )
        self.api_secret: Optional[str] = getattr(
            self.exchange_conf, "_resolved_api_secret", None
        )

        # 实盘模式下必须有 key/secret
        if not self.exchange_conf.dry_run and (not self.api_key or not self.api_secret):
            raise RuntimeError(
                "BinanceAsyncClient: 实盘模式下需要配置 API KEY/SECRET（已在 config 中硬编码或通过环境变量提供）"
            )

        # aiohttp session 由 network 层统一创建，内部复用
        self._session: Optional[aiohttp.ClientSession] = None
        # 实际使用的代理地址（由 create_http_client 决定是否启用）
        self._proxy_url_in_use: Optional[str] = None

        # futures base url：U 本位永续合约
        # 如果 ExchangeConfig 没有 futures_base_url，则回退到官方默认值。
        self._futures_base_url: str = getattr(
            self.exchange_conf,
            "futures_base_url",
            "https://fapi.binance.com",
        )

    async def _ensure_session(self) -> None:
        """
        确保已创建 aiohttp session，并根据代理配置设置代理。

        代理决策规则：
        - 如果 config.proxy.use_proxy_by_default=True，则使用 config.proxy.proxy_url
        - 如果 config.proxy.use_proxy_by_default=False，则不使用代理（None）
        """
        if self._session is None or self._session.closed:
            # 直接创建 aiohttp session
            self._session = aiohttp.ClientSession()
            
            # 根据配置决定是否使用代理
            proxy_config = self.config.proxy
            
            if proxy_config.use_proxy_by_default:
                self._proxy_url_in_use = proxy_config.proxy_url
            else:
                self._proxy_url_in_use = None

    async def close(self) -> None:
        """
        关闭内部 session。
        """
        if self._session is not None and not self._session.closed:
            await self._session.close()

    # --------------------
    # 签名与请求封装
    # --------------------

    def _sign(self, query: str) -> str:
        """
        使用 HMAC-SHA256 对 query 进行签名，返回 hex 字符串。
        """
        if not self.api_secret:
            raise RuntimeError("BinanceAsyncClient: 缺少 API secret，无法签名")
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            query.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return signature

    def _get_base_url(self) -> str:
        """
        获取现货 REST base url。

        当前直接返回 ExchangeConfig.base_url。
        如后续需要 testnet，可在 config 中切换 base_url 或扩展逻辑。
        """
        return self.exchange_conf.base_url

    def _get_futures_base_url(self) -> str:
        """
        获取 U 本位合约 REST base url。

        默认使用 https://fapi.binance.com，
        若在 ExchangeConfig 中定义了 futures_base_url，则优先使用配置值。
        """
        return self._futures_base_url

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        signed: bool = False,
        use_futures: bool = False,
    ) -> Any:
        """
        通用请求封装。

        - method: "GET"/"POST"/"DELETE"/"PUT"
        - path: 例如 "/api/v3/account"、"/fapi/v1/order"
        - params: query/body 参数
        - signed: 是否需要签名（私有接口通常需要）
        - use_futures: 是否调用合约 base_url（fapi）

        代理逻辑：
        - 是否使用代理由 network.create_http_client 决定；
        - 这里仅将 self._proxy_url_in_use 原样传给 aiohttp。
        """
        await self._ensure_session()
        assert self._session is not None

        # 根据 use_futures 选择 base_url
        if use_futures:
            base_url = self._get_futures_base_url()
        else:
            base_url = self._get_base_url()

        url = base_url.rstrip("/") + path
        params = params.copy() if params else {}

        headers: Dict[str, str] = {}
        if signed:
            if not self.api_key:
                raise RuntimeError("BinanceAsyncClient: 缺少 API KEY，无法调用私有接口")
            headers["X-MBX-APIKEY"] = self.api_key

            # 添加 timestamp 与 recvWindow 并签名
            timestamp = int(time.time() * 1000)
            params.setdefault("recvWindow", self.exchange_conf.recv_window)
            params["timestamp"] = timestamp
            query_str = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
            params["signature"] = self._sign(query_str)

        proxy = self._proxy_url_in_use

        timeout = aiohttp.ClientTimeout(total=self.exchange_conf.request_timeout_sec)
        async with self._session.request(
            method=method,
            url=url,
            params=params if method.upper() == "GET" else None,
            data=params if method.upper() in {"POST", "DELETE", "PUT"} else None,
            proxy=proxy,
            timeout=timeout,
            headers=headers,
        ) as resp:
            # Binance 返回 JSON；错误时依然返回 JSON，带 code/msg 字段
            data = await resp.json()
            if resp.status >= 400:
                raise RuntimeError(f"Binance API error {resp.status}: {data}")
            return data

    # --------------------
    # 对外接口
    # --------------------

    async def get_balance(self, asset: str) -> float:
        """
        查询现货账户中指定资产的可用余额。

        使用 /api/v3/account 接口，然后在 balances 中查找对应资产。
        """
        data = await self._request("GET", "/api/v3/account", signed=True, use_futures=False)
        balances = data.get("balances", [])
        for b in balances:
            if b.get("asset") == asset:
                free_str = b.get("free", "0")
                try:
                    return float(free_str)
                except ValueError:
                    return 0.0
        return 0.0

    async def get_latest_price(self, symbol: str) -> float:
        """
        查询交易对最新价格（现货价格）。

        使用 /api/v3/ticker/price 接口。
        """
        data = await self._request(
            "GET",
            "/api/v3/ticker/price",
            params={"symbol": symbol},
            signed=False,
            use_futures=False,
        )
        price_str = data.get("price", "0")
        try:
            return float(price_str)
        except ValueError:
            return 0.0

    # --------------------
    # 合约账户相关接口（U 本位永续）
    # --------------------

    async def get_future_balance(self) -> float:
        """
        查询 U 本位合约账户总余额（USDT）。

        对应 REST: GET /fapi/v2/account
        返回字段中 'assets' 里 asset == 'USDT' 的 walletBalance + unrealizedProfit。
        """
        data = await self._request(
            "GET",
            "/fapi/v2/account",
            params={"recvWindow": self.exchange_conf.recv_window},
            signed=True,
            use_futures=True,
        )
        assets = data.get("assets", [])
        for a in assets:
            if a.get("asset") == "USDT":
                wallet = float(a.get("walletBalance", "0"))
                unrealized = float(a.get("unrealizedProfit", "0"))
                return wallet + unrealized
        return 0.0

    async def set_dual_position_mode(self, enable: bool = True) -> Dict[str, Any]:
        """
        设置 U 本位合约账户的持仓模式为双向持仓。

        对应 REST:
        - POST /fapi/v1/positionSide/dual
        - 参数 dualSidePosition: "true"/"false"

        参考 binance.Binance.set_dual_position_mode。
        """
        params = {
            "dualSidePosition": "true" if enable else "false",
            "recvWindow": self.exchange_conf.recv_window,
        }
        data = await self._request(
            "POST",
            "/fapi/v1/positionSide/dual",
            params=params,
            signed=True,
            use_futures=True,
        )
        return data

    async def change_leverage(self, symbol: str, leverage: int = 20) -> Dict[str, Any]:
        """
        调整单个 symbol 的杠杆倍数（默认 20 倍）。

        对应 REST:
        - POST /fapi/v1/leverage
        - 参数 symbol, leverage, recvWindow

        参考 binance.Binance.change_leverage。
        """
        params = {
            "symbol": symbol,
            "leverage": leverage,
            "recvWindow": self.exchange_conf.recv_window,
        }
        data = await self._request(
            "POST",
            "/fapi/v1/leverage",
            params=params,
            signed=True,
            use_futures=True,
        )
        return data

    async def place_future_market_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        position_side: Optional[str] = None,
        leverage: int = 20,
    ) -> Dict[str, Any]:
        """
        在 U 本位永续合约账户中发送市价单。

        - symbol: 交易对，如 "BTCUSDT"
        - side: "BUY"/"SELL"（订单方向）
        - quantity: 下单数量（合约张数，按 Binance U 本位规则）
        - position_side: "LONG"/"SHORT"；若不传则不指定 positionSide（走双向模式下的默认行为）
        - leverage: 杠杆倍数（默认 20）

        行为：
        - 若 dry_run=True，则只返回一个 mock 结果，不调用真实 API；
        - 若 dry_run=False：
          1）先调用 set_dual_position_mode(true)，确保双向持仓；
          2）再调用 change_leverage(symbol, leverage)，确保杠杆为 20 倍（或你传入的值）；
          3）最后调用 POST /fapi/v1/order，type=MARKET 下单。
        """
        side_u = side.upper()
        if quantity <= 0:
            raise ValueError("place_future_market_order: quantity 必须大于 0")

        # 模拟模式：不真正下单，仅返回伪造结果
        if self.exchange_conf.dry_run:
            return {
                "symbol": symbol,
                "side": side_u,
                "positionSide": position_side or "BOTH",
                "status": "DRY_RUN",
                "executedQty": quantity,
                "fills": [],
                "leverage": leverage,
            }

        # 1. 确保双向持仓模式
        await self.set_dual_position_mode(True)

        # 2. 设置杠杆（如果需要，可在外部控制只设置一次，这里为了简单每次下单前都调用）
        await self.change_leverage(symbol=symbol, leverage=leverage)

        # 3. 发送市价单（修复：添加精度格式化）
        # 格式化数量以符合 Binance API 要求
        formatted_quantity = format_quantity_for_binance(quantity, step_size=0.001)
        
        params: Dict[str, Any] = {
            "symbol": symbol,
            "side": side_u,
            "type": "MARKET",
            "quantity": formatted_quantity,  # 使用格式化后的字符串
            "recvWindow": self.exchange_conf.recv_window,
        }
        if position_side:
            # 如 "LONG" / "SHORT"
            params["positionSide"] = position_side

        data = await self._request(
            "POST",
            "/fapi/v1/order",
            params=params,
            signed=True,
            use_futures=True,
        )
        return data