"""Network camera discovery via TCP port scanning.

Scans local network for hosts with RTSP ports open.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
from typing import Any

logger = logging.getLogger(__name__)

# Common RTSP ports
RTSP_PORTS = [554, 8554, 10554]


def _get_local_network() -> ipaddress.IPv4Network | None:
    """Detect local network from active interfaces."""
    try:
        import psutil  # type: ignore[import-untyped]

        for _iface, addrs in psutil.net_if_addrs().items():
            for addr in addrs:
                if addr.family == socket.AF_INET:
                    ip = addr.address
                    if ip.startswith("127.") or ip.startswith("169.254."):
                        continue
                    if addr.netmask:
                        return ipaddress.IPv4Network(f"{ip}/{addr.netmask}", strict=False)
    except ImportError:
        logger.warning("psutil not available, trying socket-based detection")
        # Fallback: detect local IP via UDP socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            return ipaddress.IPv4Network(f"{local_ip}/24", strict=False)
        except Exception:
            pass
    return None


async def _scan_port(
    host: str,
    port: int,
    timeout: float = 1.5,
    semaphore: asyncio.Semaphore | None = None,
) -> str | None:
    """Check if a specific port is open on a host."""

    async def _check() -> str | None:
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

    if semaphore:
        async with semaphore:
            return await _check()
    return await _check()


async def discover_cameras(
    timeout: int = 30,
    max_concurrent: int = 100,
) -> list[dict[str, Any]]:
    """Discover cameras by scanning local network for open RTSP ports.

    Args:
        timeout: Total discovery timeout in seconds
        max_concurrent: Max concurrent connection attempts

    Returns:
        List of discovered cameras:
        [{"name": "Camera at 192.168.1.100:554", "host": "192.168.1.100", "port": 554}, ...]
    """
    network = _get_local_network()
    if not network:
        logger.warning("Could not detect local network")
        return []

    cameras: list[dict[str, Any]] = []
    seen: set[str] = set()
    semaphore = asyncio.Semaphore(max_concurrent)
    hosts = [str(ip) for ip in network.hosts()]

    logger.info(
        "Starting camera discovery: %d hosts, ports=%s, timeout=%ds",
        len(hosts),
        RTSP_PORTS,
        timeout,
    )

    time_per_port = max(timeout // len(RTSP_PORTS), 5)

    for port in RTSP_PORTS:
        try:
            results = await asyncio.wait_for(
                asyncio.gather(
                    *[_scan_port(h, port, timeout=1.5, semaphore=semaphore) for h in hosts]
                ),
                timeout=time_per_port,
            )
            for host_ip in results:
                if host_ip is not None:
                    key = f"{host_ip}:{port}"
                    if key not in seen:
                        seen.add(key)
                        cameras.append(
                            {
                                "name": f"Camera at {host_ip}:{port}",
                                "host": host_ip,
                                "port": port,
                            }
                        )
                        logger.debug("Found camera: %s:%d", host_ip, port)
        except TimeoutError:
            logger.debug("Port scan timed out: port=%d", port)
        except Exception as e:
            logger.debug("Error scanning port %d: %s", port, e)

    logger.info("Camera discovery complete: %d cameras found", len(cameras))
    return cameras
