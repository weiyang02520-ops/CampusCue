"""V2 entrypoint: python -m campuscue

Starts the M1 runtime. Ctrl+C triggers graceful shutdown.
"""

from __future__ import annotations

import asyncio
import logging
import sys

from campuscue.app.runtime import CampusRuntime
from campuscue.config import load_config


def _setup_logging(diagnostic: bool) -> None:
    level = logging.DEBUG if diagnostic else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    if not diagnostic:
        # normal mode: suppress anything that could carry message body / ids
        logging.getLogger("campuscue.onebot").setLevel(logging.WARNING)


async def _amain() -> int:
    config = load_config()
    _setup_logging(config.diagnostic)
    runtime = CampusRuntime(config)
    try:
        await runtime.start()
        if config.diagnostic:
            print(
                "DIAGNOSTIC MODE ON: will print conversation/group/sender/message for "
                "acceptance only. Turn off for production."
            )
        else:
            print("CampusCue V2 runtime RUNNING (normal logs are privacy-redacted).")
            print("Listening for NapCat reverse WS; send 'hello' from QQ to verify.")
        # keep running until Ctrl+C / SIGTERM
        stop_event = asyncio.Event()
        try:
            await stop_event.wait()
        except asyncio.CancelledError:
            pass
        return 0
    finally:
        await runtime.stop()


def main() -> None:
    try:
        asyncio.run(_amain())
    except KeyboardInterrupt:
        print("CampusCue V2 stopped.")
        sys.exit(0)
    except Exception:
        logging.getLogger("campuscue").exception("fatal runtime error")
        sys.exit(1)


if __name__ == "__main__":
    main()
