"""Entry point for the Tailscale source service."""

import asyncio

from sense_common.config import get_redis_url

from tailscale.source import TailscaleSource


def main() -> None:
    source = TailscaleSource()
    asyncio.run(source.run(get_redis_url()))


if __name__ == "__main__":
    main()
