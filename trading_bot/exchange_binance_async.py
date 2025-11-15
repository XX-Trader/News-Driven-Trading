"""
trading_bot.exchange_binance_async

Binance 异步 REST 适配（骨架版）：

- get_balance: 查询指定资产余额
- get_latest_price: 查询交易对最新价格（ticker price）
- place_market_order: 发送市价单（支持 BUY/SELL）

注意：
- 当前实现偏向最小可用版本（MVP），未做完备错误分类与限频处理；
- 所有 HTTP 调用复用 trading_bot.network 中创建的 aiohttp.ClientSession；
- 真实密钥从环境变量读取，具体变量名由 ExchangeConfig.api_key_env / api_secret_env 决定；
- 是否真实下单由 ExchangeConfig.dry_run 控制。
"""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any, Dict, Optional

import aiohttp

from .config import AppConfig, ExchangeConfig, load_env_var
from .network import create_http_client


BINANCE_TIMESTAMP_MARGIN_MS = 1000  # 本地时间与服务器时间的安全边际


class BinanceAsyncClient:
    """
    Binance 异步 REST 客户端（简化版）。

    只实现本项目需要的最小接口：
    - get_balance
    - get_latest_price
    - place_market_order
    """

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.exchange_conf: ExchangeConfig = config.exchange

        # API key / secret 从环境变量中读取
        self.api_key: Optional[str] = load_env_var(self.exchange_conf.api_key_env)
        self.api_secret: Optional[str] = load_env_var(self.exchange_conf.api_secret_env)

        if not self.exchange_conf.dry_run and (not self.api_key or not self.api_secret):
            raise RuntimeError(
                "BinanceAsyncClient: 实盘模式下需要在环境变量中配置 API KEY/SECRET"
            )

        self._session: Optional[aiohttp.ClientSession] = None
        self._proxy_url_in_use: Optional[str] = None

    async def _ensure_session(self) -> None:
        """
        确保已创建 aiohttp session，并根据网络配置设置代理。

        使用 trading_bot.network.create_http_client 来保持行为一致。
        """
        if self._session is None or self._session.closed:
            session, proxy_url = await create_http_client(self.config)
            self._session = session
            self._proxy_url_in_use = proxy_url

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
        if self.exchange_conf.use_testnet:
            # 如有需要，可在这里切换 testnet base_url
            # 目前保持与配置一致，具体值由 config.ExchangeConfig.base_url 决定
            return self.exchange_conf.base_url
        return self.exchange_conf.base_url

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        signed: bool = False,
    ) -> Any:
        """
        通用请求封装。

        - method: "GET"/"POST"
        - path: 如 "/api/v3/account"
        - params: query/body 参数
        - signed: 是否需要签名（私有接口通常需要）
        """
        await self._ensure_session()
        assert self._session is not None

        url = self._get_base_url().rstrip("/") + path
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
            data=params if method.upper() == "POST" else None,
            proxy=proxy,
            timeout=timeout,
        ) as resp:
            # Binance 常见错误可在这里扩展判断，目前先直接 json()
            data = await resp.json()
            if resp.status >= 400:
                raise RuntimeError(f"Binance API error {resp.status}: {data}")
            return data

    # --------------------
    # 对外接口
    # --------------------

    async def get_balance(self, asset: str) -> float:
        """
        查询指定资产的可用余额。

        使用 /api/v3/account 接口，然后在 balances 中查找对应资产。
        """
        data = await self._request("GET", "/api/v3/account", signed=True)
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
        查询交易对最新价格。

        使用 /api/v3/ticker/price 接口。
        """
        data = await self._request(
            "GET",
            "/api/v3/ticker/price",
            params={"symbol": symbol},
            signed=False,
        )
        price_str = data.get("price", "0")
        try:
            return float(price_str)
        except ValueError:
            return 0.0

    async def place_market_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
    ) -> Dict[str, Any]:
        """
        发送市价单。

        - symbol: 交易对，如 BTCUSDT
        - side: "BUY"/"SELL"
        - quantity: 下单数量（以 base 计量）

        若 dry_run=True，则只返回一个 mock 结果，不调用真实 API。
        """
        side_u = side.upper()
        if quantity <= 0:
            raise ValueError("place_market_order: quantity 必须大于 0")

        if self.exchange_conf.dry_run:
            # 模拟模式：不真正下单，仅返回伪造结果
            return {
                "symbol": symbol,
                "side": side_u,
                "status": "DRY_RUN",
                "executedQty": quantity,
                "fills": [],
            }

        params = {
            "symbol": symbol,
            "side": side_u,
            "type": "MARKET",
            "quantity": quantity,
        }

        data = await self._request(
            "POST",
            "/api/v3/order",
            params=params,
            signed=True,
        )
        return data