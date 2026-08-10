#!/usr/bin/env python3
"""M2 development bootstrap: configure a provider (temporary tooling).

This is NOT public product API — M5 replaces it with the configuration API/UI.
The actual secret value is NEVER accepted here; only the secret_reference
(environment variable NAME) is stored. The secret itself must already exist
in the environment.

Usage (PowerShell):
  $env:CAMPUSCUE_LLM_API_KEY = "..."     # actual secret, stays in env
  python scripts/m2_configure_provider.py --name default --base-url https://api.example.com/v1 --model gpt-4o --secret-ref CAMPUSCUE_LLM_API_KEY

Usage (Git Bash):
  export CAMPUSCUE_LLM_API_KEY=...
  python scripts/m2_configure_provider.py --name default --base-url https://api.example.com/v1 --model gpt-4o --secret-ref CAMPUSCUE_LLM_API_KEY
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# allow running as a script without install
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from campuscue.repositories.repositories import DuplicateError, ProviderConfigRepository
from campuscue.storage.database import Database, DatabaseConfig


async def _main(args: argparse.Namespace) -> None:
    db = Database(DatabaseConfig(path=args.db_path, env="production"))
    await db.initialize()
    try:
        repo = ProviderConfigRepository(db.session)
        try:
            cfg = await repo.create(
                name=args.name,
                base_url=args.base_url,
                model=args.model,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
                timeout_s=args.timeout,
                secret_reference=args.secret_ref,
                enabled=True,
            )
            print(f"provider configured: id={cfg.id} name={cfg.name} model={cfg.model}")
            print(f"secret_reference stored: {cfg.secret_reference!r} (value never stored)")
        except DuplicateError:
            print(
                f"provider {args.name!r} already exists; disable or remove it explicitly "
                "before reconfiguring (no --replace flag in M2 dev bootstrap)"
            )
    finally:
        await db.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="M2 dev bootstrap: configure provider")
    parser.add_argument("--db-path", default="data/campuscue.db", help="SQLite DB path")
    parser.add_argument("--name", required=True)
    parser.add_argument("--base-url", required=True, help="e.g. https://api.example.com/v1")
    parser.add_argument("--model", required=True)
    parser.add_argument("--secret-ref", default=None, help="ENV VARIABLE NAME of the API key (never the key itself)")
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument("--max-tokens", type=int, default=None)
    parser.add_argument("--timeout", type=float, default=30.0)
    asyncio.run(_main(parser.parse_args()))


if __name__ == "__main__":
    main()
