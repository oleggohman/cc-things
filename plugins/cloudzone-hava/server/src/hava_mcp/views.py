"""Mapping between Hava's internal view class names and friendly names.

A Hava "diagram" is an *environment* that holds several *views*. The API uses
Ruby class names (``Views::Infrastructure::Extended``); tools in this server
accept and emit short names (``extended``) so callers never have to guess the
exact casing.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .errors import HavaError

#: Canonical API view type -> short name used by this server's tools.
SHORT_NAMES: dict[str, str] = {
    "Views::Infrastructure": "infrastructure",
    "Views::Infrastructure::Extended": "extended",
    "Views::Security": "security",
    "Views::Container": "container",
    "Views::List": "list",
}

#: Everything a caller might plausibly type -> canonical API view type.
ALIASES: dict[str, str] = {
    "infrastructure": "Views::Infrastructure",
    "infra": "Views::Infrastructure",
    "topology": "Views::Infrastructure",
    "extended": "Views::Infrastructure::Extended",
    "infrastructure_extended": "Views::Infrastructure::Extended",
    "extended_infrastructure": "Views::Infrastructure::Extended",
    "security": "Views::Security",
    "container": "Views::Container",
    "containers": "Views::Container",
    "list": "Views::List",
}

VIEW_CHOICES: tuple[str, ...] = ("infrastructure", "extended", "security", "container", "list")


def short_name(view_type: str | None) -> str:
    """``Views::Security`` -> ``security``; unknown types pass through cleaned up."""
    if not view_type:
        return "unknown"
    if view_type in SHORT_NAMES:
        return SHORT_NAMES[view_type]
    return view_type.removeprefix("Views::").replace("::", "_").lower()


def canonical_name(view: str) -> str:
    """Resolve a user-supplied view name to the canonical API view type."""
    key = (view or "").strip()
    if key in SHORT_NAMES:  # already canonical
        return key
    resolved = ALIASES.get(key.lower().replace("-", "_").replace(" ", "_"))
    if resolved is None:
        raise HavaError(
            f"Unknown view {view!r}. Valid views are: {', '.join(VIEW_CHOICES)}."
        )
    return resolved


def pick_view(views: Sequence[Mapping[str, Any]], view: str) -> Mapping[str, Any]:
    """Find the requested view in an environment's ``views`` array.

    Raises a ``HavaError`` naming the views that *do* exist, which is far more
    useful to an agent than a bare "not found".
    """
    wanted = canonical_name(view)
    for candidate in views or ():
        if candidate.get("type") == wanted:
            return candidate
    available = sorted({short_name(v.get("type")) for v in views or ()})
    if not available:
        raise HavaError(
            "This diagram has no views yet. Environments report no views while they are "
            "still building (state 'pending') - check again with hava_get_diagram."
        )
    raise HavaError(
        f"This diagram has no {short_name(wanted)!r} view. Available views: "
        f"{', '.join(available)}. Security views exist for AWS and Azure only, and "
        f"container views only where containerised resources were discovered."
    )
