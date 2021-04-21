#!/usr/bin/env python3
"""
A service that reads libvirtd events from a hook and manages VM resources.

Functions:
    service: Creates the services and handles exceptions in the event loop.
    main: The entry point for the service that runs the event loop.

Environment Variables:
    LOGLEVEL: The level of logs to output.
"""

import asyncio
import logging
import os
import pathlib
import signal
import sys

from .service import AkeydoService
from .settings import Settings
from .task import create_task


_DEFAULT_CONFIG_PATH = "/etc/akeydo.conf"


async def service(config: pathlib.Path) -> None:
    """Configure logging and error handling and start the service.

    Args:
        config: A Path to a YAML configuration file to configure the service and
            plug-ins.
    """
    logging.basicConfig(
        level=os.environ.get("LOGLEVEL", "INFO").upper(),
        format="[%(levelname)s] %(message)s",
    )
    loop = asyncio.get_event_loop()
    settings = Settings(config or _DEFAULT_CONFIG_PATH)
    manager = AkeydoService(settings, *settings.enabled_plugins.values())

    def signal_handler() -> None:
        """Stop the service and cleanup devices on receiving a signal."""
        manager.stop()
        loop.stop()

    for sig in (signal.SIGINT, signal.SIGQUIT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)

    task = create_task(manager.start())
    try:
        await task
    except Exception as e:
        task.exception()


def main():
    """The service entry point."""
    loop = asyncio.get_event_loop()
    path = pathlib.Path(_DEFAULT_CONFIG_PATH if len(sys.argv) < 2 else sys.argv[1])
    loop.create_task(service(path))
    loop.run_forever()


if __name__ == "__main__":
    main()
