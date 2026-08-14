import pytest

from ilias_mcp.exceptions import ProviderNotFoundError
from ilias_mcp.providers.kit import KITProvider
from ilias_mcp.providers.registry import discover_providers, get_provider_class


def test_kit_provider_is_registered():
    providers = discover_providers()
    assert providers["kit"] is KITProvider


def test_get_provider_class_unknown_raises():
    with pytest.raises(ProviderNotFoundError):
        get_provider_class("does-not-exist")
