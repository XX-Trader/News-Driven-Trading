"""
trading_bot.network

负责：
- Google 连通性检测；
- 根据配置决定是否启用代理；
- 创建统一的 aiohttp ClientSession，供交易所 / AI / 消息源使用。

当前为骨架实现，后续会在此基础上补充具体逻辑。
"""

from __future__ import annotations

from typing import Optional, Tuple

import aiohttp

from .config import AppConfig, ProxyConfig


class NetworkContext:
    """
    封装网络相关状态：
    - 是否可直连 Google
    - 实际使用的代理 URL（如果有）
    - 公共 aiohttp.ClientSession
    """

    def __init__(
        self,
        proxy_config: ProxyConfig,
        google_reachable: bool,
        proxy_url_in_use: Optional[str],
        session: aiohttp.ClientSession,
    ) -> None:
        self.proxy_config = proxy_config
        self.google_reachable = google_reachable
        self.proxy_url_in_use = proxy_url_in_use
        self.session = session

    async def close(self) -> None:
        await self.session.close()


async def check_google_connectivity(proxy_config: ProxyConfig) -> bool:
    """
    检测是否可以访问 Google。

    TODO（后续实现）：
    - 使用 aiohttp 访问 proxy_config.google_test_url
    - 在 proxy_config.google_timeout_sec 内判断成功/失败

    当前占位实现：直接返回 False，方便先把主流程跑通。
    """
    return False


def decide_proxy_usage(
    proxy_config: ProxyConfig,
    google_reachable: bool,
) -> Optional[str]:
    """
    根据配置与 Google 连通结果，决定是否使用代理，并返回实际代理 URL（或 None）。
    """
    if proxy_config.force_proxy:
        return proxy_config.proxy_url

    if not proxy_config.google_check_enabled:
        # 不检测 Google，根据默认策略决定
        if proxy_config.use_proxy_by_default:
            return proxy_config.proxy_url
        return None

    # 进行了 Google 检测
    if google_reachable:
        # 能连上 Google，默认直连
        if proxy_config.use_proxy_by_default:
            # 如果用户特别指定默认走代理，则尊重配置
            return proxy_config.proxy_url
        return None

    # 不能连 Google，则启用代理
    return proxy_config.proxy_url


async def create_network_context(config: AppConfig) -> NetworkContext:
    """
    根据 AppConfig 构建 NetworkContext：
    - 先检查 Google 连通性（如果启用）；
    - 决定是否使用代理；
    - 创建统一 aiohttp.ClientSession。
    """
    proxy_conf = config.proxy

    if proxy_conf.google_check_enabled:
        google_ok = await check_google_connectivity(proxy_conf)
    else:
        google_ok = False

    proxy_url = decide_proxy_usage(proxy_conf, google_ok)

    # 这里只设置一个相对宽松的超时时间，后续可按 API 需要细化
    timeout = aiohttp.ClientTimeout(total=None)

    session_kwargs = {"timeout": timeout}
    # aiohttp 的代理通常在请求级别指定，这里只记录 proxy_url，用于上层调用时选择性传入
    session = aiohttp.ClientSession(**session_kwargs)

    return NetworkContext(
        proxy_config=proxy_conf,
        google_reachable=google_ok,
        proxy_url_in_use=proxy_url,
        session=session,
    )


async def create_http_client(config: AppConfig) -> Tuple[aiohttp.ClientSession, Optional[str]]:
    """
    兼容性函数：返回 (session, proxy_url_in_use)。

    在部分场景下，只需要一个 session + 当前代理设置即可。
    """
    net = await create_network_context(config)
    return net.session, net.proxy_url_in_use