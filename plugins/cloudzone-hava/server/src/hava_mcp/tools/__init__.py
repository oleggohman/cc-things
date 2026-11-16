"""Tool modules. Importing them registers their tools on the shared server.

Do not name a module in this package ``annotations``: ``from __future__ import
annotations`` binds that name first, so ``from . import annotations`` resolves
to the future flag and the module's tools are never registered.
"""

from __future__ import annotations

from . import collaboration, custom_diagrams, org, reports, resources, sources  # noqa: F401

__all__ = ["collaboration", "custom_diagrams", "org", "reports", "resources", "sources"]
