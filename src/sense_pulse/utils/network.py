"""Network scanning utilities."""

import asyncio
import ipaddress
import socket

import psutil  # type: ignore[import-untyped]


async def scan_network_for_port(
    port: int,
    max_concurrent: int = 100,
    timeout: float = 1.5,
) -> list[str]:
    """
    Scan local network for hosts with a specific port open.

    Args:
        port: Port number to scan for
        max_concurrent: Max concurrent connection attempts
        timeout: Timeout per connection attempt in seconds

    Returns:
        List of IP addresses with the port open
    """
    network = _get_local_network()
    if not network:
        return []

    semaphore = asyncio.Semaphore(max_concurrent)
    hosts = [str(ip) for ip in network.hosts()]

    async def check_host(host: str) -> str | None:
        async with semaphore:
            try:
                _, writer = await asyncio.wait_for(
                    asyncio.open_connection(host, port),
                    timeout=timeout,
                )
                writer.close()
                await writer.wait_closed()
                return host
            except (TimeoutError, OSError, ConnectionRefusedError):
                return None

    results = await asyncio.gather(*[check_host(h) for h in hosts])
    return [ip for ip in results if ip]


def _get_local_network() -> ipaddress.IPv4Network | None:
    """Detect local network from active interfaces."""
    for _iface, addrs in psutil.net_if_addrs().items():
        for addr in addrs:
            if addr.family == socket.AF_INET:
                ip = addr.address
                if ip.startswith("127.") or ip.startswith("169.254."):
                    continue
                if addr.netmask:
                    return ipaddress.IPv4Network(f"{ip}/{addr.netmask}", strict=False)
    return None
