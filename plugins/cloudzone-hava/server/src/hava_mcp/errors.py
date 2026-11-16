"""Exception types shared across the Hava MCP server."""

from __future__ import annotations


class HavaError(RuntimeError):
    """A Hava operation failed in a way worth reporting back to the caller."""


class HavaConfigError(HavaError):
    """The server is missing configuration it needs (usually the API token)."""
