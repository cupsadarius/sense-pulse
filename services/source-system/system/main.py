"""Entry point for the system metrics source service."""

import asyncio

from sense_common.config import get_redis_url
from system.source import SystemSource


def main() -> None:
    source = SystemSource()
    asyncio.run(source.run(get_redis_url()))


if __name__ == "__main__":
    main()
