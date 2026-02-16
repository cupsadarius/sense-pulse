"""Entry point for the weather source service."""

import asyncio

from sense_common.config import get_redis_url
from weather.source import WeatherSource


def main() -> None:
    source = WeatherSource()
    asyncio.run(source.run(get_redis_url()))


if __name__ == "__main__":
    main()
