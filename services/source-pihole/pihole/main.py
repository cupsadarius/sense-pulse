"""Entry point for the Pi-hole source service."""

import asyncio

from sense_common.config import get_redis_url

from pihole.source import PiHoleSource


def main() -> None:
    source = PiHoleSource()
    asyncio.run(source.run(get_redis_url()))


if __name__ == "__main__":
    main()
