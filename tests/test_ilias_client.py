import responses

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


def _logged_in_client() -> ILIASClient:
    client = ILIASClient(KITProvider(base_url=BASE))
    client._logged_in = True  # bypass the real login flow for this unit test
    return client


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
