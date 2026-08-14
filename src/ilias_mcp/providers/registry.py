from __future__ import annotations

import importlib.metadata as importlib_metadata

from ..exceptions import ProviderNotFoundError
from .base import AuthProvider

_ENTRY_POINT_GROUP = "ilias_mcp.providers"


def _builtin_providers() -> dict[str, type[AuthProvider]]:
    # Imported lazily (rather than via decorator self-registration) to avoid
    # a registry <-> provider-module circular import.
    from .kit import KITProvider

    return {KITProvider.name: KITProvider}


def discover_providers() -> dict[str, type[AuthProvider]]:
    """Return every known provider: built-ins plus anything a third-party
    package registered under the ``ilias_mcp.providers`` entry-point group.

    This is the whole plugin mechanism — a separately-installed package that
    exposes an entry point in that group shows up here with no changes to
    this codebase.
    """
    providers = _builtin_providers()
    for ep in importlib_metadata.entry_points(group=_ENTRY_POINT_GROUP):
        if ep.name in providers and ep.name in _builtin_providers():
            continue  # built-ins may also ship their own entry point; don't double-load
        try:
            providers[ep.name] = ep.load()
        except Exception as exc:  # pragma: no cover - defensive, third-party plugin failure
            raise ImportError(f"Failed to load ILIAS provider plugin '{ep.name}': {exc}") from exc
    return providers


def get_provider_class(name: str) -> type[AuthProvider]:
    providers = discover_providers()
    try:
        return providers[name]
    except KeyError:
        available = ", ".join(sorted(providers)) or "(none registered)"
        raise ProviderNotFoundError(
            f"Unknown ILIAS provider '{name}'. Available: {available}"
        ) from None
