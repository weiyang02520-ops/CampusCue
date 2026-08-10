#!/usr/bin/env python3
"""M2 development bootstrap: configure a Source (temporary tooling).

NOT public product API — M5 replaces this with the configuration API/UI.
Real conversation IDs should be passed via the CAMPUSCUE_SOURCE_CONVERSATION
environment variable, never hardcoded into Git.

Usage (PowerShell):
  $env:CAMPUSCUE_SOURCE_CONVERSATION = "123456789"   # real group id stays in env
  python scripts/m2_configure_source.py --platform onebot --name "测试群"

Usage (Git Bash):
  export CAMPUSCUE_SOURCE_CONVERSATION=123456789
  python scripts/m2_configure_source.py --platform onebot --name "测试群"
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from campuscue.repositories.repositories import DuplicateError, SourceRepository
from campuscue.services.source_service import SourceService
from campuscue.storage.database import Database, DatabaseConfig


async def _main(args: argparse.Namespace) -> None:
    conversation_id = args.conversation or os.environ.get("CAMPUSCUE_SOURCE_CONVERSATION")
    if not conversation_id:
        print("ERROR: provide --conversation or set CAMPUSCUE_SOURCE_CONVERSATION env")
        sys.exit(2)
    db = Database(DatabaseConfig(path=args.db_path, env="production"))
    await db.initialize()
    try:
        service = SourceService(SourceRepository(db.session))
        try:
            src = await service.create_source(
                platform=args.platform,
                conversation_id=conversation_id,
                name=args.name,
                auto_extract=args.auto_extract,
                context_window=args.context_window,
            )
            print(f"source configured: id={src.id} platform={src.platform} "
                  f"conversation={conversation_id[:4]}... (redacted)")
            print(f"enabled={src.enabled} auto_extract={src.auto_extract}")
        except Exception as e:
            print(f"source config failed: {e}")
    finally:
        await db.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="M2 dev bootstrap: configure source")
    parser.add_argument("--db-path", default="data/campuscue.db")
    parser.add_argument("--platform", default="onebot")
    parser.add_argument("--conversation", default=None,
                        help="group/private ID (prefer CAMPUSCUE_SOURCE_CONVERSATION env)")
    parser.add_argument("--name", default="")
    parser.add_argument("--no-auto-extract", dest="auto_extract", action="store_false", default=True)
    parser.add_argument("--context-window", type=int, default=5)
    asyncio.run(_main(parser.parse_args()))


if __name__ == "__main__":
    main()
