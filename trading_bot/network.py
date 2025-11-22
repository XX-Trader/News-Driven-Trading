"""
trading_bot.network

网络层核心模块：
- Google 连通性检测（检测是否需要代理）
- 代理决策逻辑（根据配置和检测结果决定是否使用代理）
- 统一 aiohttp ClientSession 创建（复用连接，提高性能）

设计原则：
- 将网络检测、代理决策、session 管理封装在一起
- 支持同步和异步两种网络检测方式
- 运行时动态决定是否使用代理（无需手动切换）
"""

from __future__ import annotations

import asyncio
from typing import Optional, Tuple, Dict

import aiohttp
import requests


try:
    from config import AppConfig, ProxyConfig
except ImportError:
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
        """关闭 aiohttp session（释放连接资源）"""
        await self.session.close()


async def check_google_connectivity(config: ProxyConfig) -> bool:
    """
    异步检测是否能直连 Google。
    
    实现细节：
    - 使用 asyncio.to_thread 将同步 requests 调用转为异步（避免阻塞事件循环）
    - 超时时间从 config.google_timeout_sec 读取（可配置，默认 3 秒）
    - 只检测一次，返回结果供后续逻辑使用
    
    参数：
    - config: ProxyConfig 配置
    
    返回：
    - True: 可以直连 Google
    - False: 需要代理或网络不通
    """
    try:
        # 在线程池中执行同步请求（不阻塞主循环）
        response = await asyncio.to_thread(
            requests.get,
            config.google_test_url,
            timeout=config.google_timeout_sec
        )
        return response.status_code == 200
    except Exception:
        return False


def test_network() -> Optional[Dict[str, str]]:
    """
    测试网络并返回代理配置（兼容性函数）。
    
    行为：
    - 尝试访问 http://www.google.com（1秒超时）
    - 成功：返回 None（无代理）
    - 失败：返回代理配置字典
    
    注意：这是同步函数，建议在启动时使用。运行时检测请使用 check_google_connectivity()
    
    返回值：
    - None: 无需代理
    - Dict: 需要代理（格式：{'http': 'url', 'https': 'url'}）
    """
    try:
        url = 'http://www.google.com'
        response = requests.get(url, timeout=1)
        return None  # 连接成功，无需代理
    except Exception:
        # 连接失败，返回代理配置（硬编码，与 config.py 中的 proxy_url 保持一致）
        return {
            'http': 'http://127.0.0.1:1080',
            'https': 'http://127.0.0.1:1080'
        }


def decide_proxy_usage(
    proxy_config: ProxyConfig,
    google_reachable: bool,
) -> Optional[str]:
    """
    根据配置与 Google 连通结果，决定是否使用代理，并返回实际代理 URL（或 None）。
    
    决策逻辑（优先级从高到低）：
    1. force_proxy=True → 强制使用代理（跳过检测）
    2. google_check_enabled=False → 根据 use_proxy_by_default 决定
    3. 检测 Google → 能连上则直连，否则使用代理
    
    参数：
    - proxy_config: 代理配置
    - google_reachable: Google 连通性检测结果
    
    返回：
    - 代理 URL 或 None（直连）
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
    - 根据配置决定是否检查 Google 连通性
    - 根据检测结果决定是否使用代理
    - 创建统一 aiohttp.ClientSession
    
    决策流程：
    1. 如果 force_proxy=True → 直接使用代理，跳过检测
    2. 如果 google_check_enabled=False → 根据 use_proxy_by_default 决定
    3. 否则进行检测 → 能连上则直连，否则使用代理
    """
    proxy_conf = config.proxy
    
    # Google 连通性检测（如果启用）
    if proxy_conf.force_proxy:
        # 强制代理，无需检测
        google_ok = False
    elif not proxy_conf.google_check_enabled:
        # 不检测，假设无法连接（安全起见）
        google_ok = False
    else:
        # 进行检测
        google_ok = await check_google_connectivity(proxy_conf)
    
    proxy_url = decide_proxy_usage(proxy_conf, google_ok)
    
    # 创建超时配置
    timeout = aiohttp.ClientTimeout(total=proxy_conf.google_timeout_sec)
    
    # 创建 session（根据是否需要代理配置连接器）
    if proxy_url:
        # 修复：默认启用 SSL 验证，仅对特定测试代理允许禁用
        # 检查是否是本地测试代理（127.0.0.1 或 localhost）
        is_local_proxy = "127.0.0.1" in proxy_url or "localhost" in proxy_url
        
        if is_local_proxy:
            # 本地测试代理可以禁用 SSL（开发环境）
            print(f"[NETWORK] Using local proxy {proxy_url}, SSL verification disabled")
            connector = aiohttp.TCPConnector(ssl=False)
        else:
            # 远程代理必须启用 SSL（生产环境安全）
            print(f"[NETWORK] Using remote proxy {proxy_url}, SSL verification enabled")
            connector = aiohttp.TCPConnector(ssl=True)
        session = aiohttp.ClientSession(timeout=timeout, connector=connector)
    else:
        # 直连模式，启用 SSL
        session = aiohttp.ClientSession(timeout=timeout)
    
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