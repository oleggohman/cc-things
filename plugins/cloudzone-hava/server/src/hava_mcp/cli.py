"""Command line interface for the Hava MCP server.

``hava-mcp`` with no arguments runs the MCP server over stdio, which is what an
MCP client invokes. ``hava-mcp status`` is a diagnostic: it reports which token
the server would use and checks it against the API.

There is no ``login`` command. The API token is configuration - the plugin and
extension prompt for it at install time and deliver it as HAVA_API_TOKEN.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from . import __version__, auth
from .client import HavaClient
from .errors import HavaError


async def _source_count(token: str, base_url: str) -> int:
    client = HavaClient(token=token, base_url=base_url)
    try:
        payload = await client.get_json("/sources")
    finally:
        await client.aclose()
    if isinstance(payload, dict):
        return len(payload.get("results") or [])
    return len(payload or [])


def cmd_status(args: argparse.Namespace) -> int:
    base_url = (args.endpoint or auth.default_base_url()).rstrip("/")
    credential = auth.resolve()
    print(f"endpoint:          {base_url}")
    print(f"token variable:    {auth.TOKEN_ENV_VAR}")
    if credential is None:
        print("status:            NO TOKEN CONFIGURED")
        print()
        print(auth.setup_instructions(), file=sys.stderr)
        return 1
    print(f"credential origin: {credential.origin}")
    print(f"token:             {auth.mask(credential.token)}")
    account = auth.account_id_from_token(credential.token)
    if account:
        print(f"account id:        {account}")
    try:
        count = asyncio.run(_source_count(credential.token, base_url))
    except HavaError as exc:
        print(f"live check:        FAILED - {exc}")
        return 1
    print(f"live check:        OK ({count} source(s))")
    return 0


def cmd_serve(_: argparse.Namespace) -> int:
    from .server import main as serve

    serve()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hava-mcp",
        description="MCP server for Hava cloud architecture diagrams.",
    )
    parser.add_argument("--version", action="version", version=f"hava-mcp {__version__}")
    parser.add_argument(
        "--endpoint",
        default=None,
        help=f"Hava API base URL (default: ${auth.ENDPOINT_ENV_VAR} or {auth.DEFAULT_BASE_URL}).",
    )
    sub = parser.add_subparsers(dest="command")

    serve = sub.add_parser("serve", help="Run the MCP server over stdio (default).")
    serve.set_defaults(func=cmd_serve)

    status = sub.add_parser(
        "status", help="Show which token is configured and verify it against the API."
    )
    status.set_defaults(func=cmd_status)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, "func", cmd_serve)
    return handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
