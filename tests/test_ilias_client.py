import pytest
import responses

from ilias_mcp.exceptions import ParseError
from ilias_mcp.ilias.client import ILIASClient
from ilias_mcp.providers.kit import KITProvider

BASE = "https://fake-ilias.example"

_ITEM_HTML = """
<div class="il-item il-std-item">
  <div class="media-body">
    <h4 class="il-item-title"><a href="https://fake-ilias.example/goto.php/crs/42">Test Course</a></h4>
  </div>
</div>
"""

_NO_ITEMS_HTML = "<html><body>not a repository listing</body></html>"


def _logged_in_client() -> ILIASClient:
    client = ILIASClient(KITProvider(base_url=BASE))
    client._logged_in = True  # bypass the real login flow for this unit test
    return client


class _FakeProvider:
    """Stands in for a real AuthProvider so re-auth tests can control
    is_logged_in()/login() directly, without driving the real (multi-hop,
    HTML-scraping) Shibboleth flow."""

    name = "fake"

    def __init__(self, base_url: str, initially_logged_in: bool) -> None:
        self.base_url = base_url
        self.login_calls = 0
        self._logged_in = initially_logged_in

    def login(self, session, credentials) -> None:
        self.login_calls += 1
        self._logged_in = True

    def is_logged_in(self, session) -> bool:
        return self._logged_in


def _client_with_expired_session(initially_logged_in: bool) -> tuple[ILIASClient, _FakeProvider]:
    provider = _FakeProvider(BASE, initially_logged_in)
    client = ILIASClient(provider)
    client._logged_in = True
    client._credentials = {"username": "u", "password": "p"}
    return client, provider


@responses.activate
def test_list_my_courses_defaults_to_full_membership_overview():
    responses.add(responses.GET, f"{BASE}/ilias.php", body=_ITEM_HTML, status=200)
    client = _logged_in_client()

    client.list_my_courses()

    request_url = responses.calls[0].request.url
    assert "baseClass=ilMembershipOverviewGUI" in request_url
    assert "ilDashboardGUI" not in request_url


@responses.activate
def test_list_my_courses_favorites_only_uses_dashboard_widget():
    responses.add(responses.GET, f"{BASE}/ilias.php", body=_ITEM_HTML, status=200)
    client = _logged_in_client()

    client.list_my_courses(favorites_only=True)

    request_url = responses.calls[0].request.url
    assert "baseClass=ilDashboardGUI" in request_url
    assert "cmd=show" in request_url


@responses.activate
def test_list_my_courses_reauths_once_when_session_expired():
    client, provider = _client_with_expired_session(initially_logged_in=False)
    responses.add(responses.GET, f"{BASE}/ilias.php", body=_NO_ITEMS_HTML, status=200)
    responses.add(responses.GET, f"{BASE}/ilias.php", body=_ITEM_HTML, status=200)

    nodes = client.list_my_courses()

    assert provider.login_calls == 1
    assert len(nodes) == 1


@responses.activate
def test_list_my_courses_reraises_if_reauth_does_not_fix_it():
    client, provider = _client_with_expired_session(initially_logged_in=False)
    responses.add(responses.GET, f"{BASE}/ilias.php", body=_NO_ITEMS_HTML, status=200)
    responses.add(responses.GET, f"{BASE}/ilias.php", body=_NO_ITEMS_HTML, status=200)

    with pytest.raises(ParseError):
        client.list_my_courses()

    assert provider.login_calls == 1  # retried exactly once, no loop


@responses.activate
def test_list_my_courses_does_not_reauth_when_session_still_valid():
    client, provider = _client_with_expired_session(initially_logged_in=True)
    responses.add(responses.GET, f"{BASE}/ilias.php", body=_NO_ITEMS_HTML, status=200)

    with pytest.raises(ParseError):
        client.list_my_courses()

    assert provider.login_calls == 0  # a real markup issue, not session expiry
