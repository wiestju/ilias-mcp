import pytest
import responses

from ilias_mcp.exceptions import DownloadError, ParseError
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

_EMPTY_FORUM_HTML = """
<table id="recf_2905709">
  <tbody>
    <tr class="tblrow1"><td class="ilCenter" colspan="4">Keine Einträge</td></tr>
  </tbody>
</table>
"""

_FORUM_POST_HTML = """
<div class="ilFrmPostRow">
  <div class="ilFrmPostTitle">Prof. Dr. Test</div>
  <div class="ilFrmPostContent">Die Klausur findet nun am 15.02. statt.</div>
</div>
"""

_EMPTY_EXERCISE_HTML = """
<div class="panel-body">
  <div class="alert alert-info" role="status">Keine Übungseinheiten vorhanden.</div>
</div>
"""


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
def test_list_my_courses_retries_even_when_is_logged_in_says_fine():
    # is_logged_in() isn't trustworthy as a gate for reacting to an already
    # -observed failure (see _force_relogin's docstring) — a ParseError
    # forces exactly one relogin+retry regardless of what it reports.
    client, provider = _client_with_expired_session(initially_logged_in=True)
    responses.add(responses.GET, f"{BASE}/ilias.php", body=_NO_ITEMS_HTML, status=200)
    responses.add(responses.GET, f"{BASE}/ilias.php", body=_ITEM_HTML, status=200)

    nodes = client.list_my_courses()

    assert provider.login_calls == 1
    assert len(nodes) == 1


@responses.activate
def test_list_forum_threads_parses_empty_forum():
    responses.add(responses.GET, f"{BASE}/ilias.php", body=_EMPTY_FORUM_HTML, status=200)
    client = _logged_in_client()

    assert client.list_forum_threads("2905709") == []


@responses.activate
def test_list_forum_threads_reauths_on_expired_session():
    client, provider = _client_with_expired_session(initially_logged_in=False)
    responses.add(responses.GET, f"{BASE}/ilias.php", body=_NO_ITEMS_HTML, status=200)
    responses.add(responses.GET, f"{BASE}/ilias.php", body=_EMPTY_FORUM_HTML, status=200)

    threads = client.list_forum_threads("2905709")

    assert provider.login_calls == 1
    assert threads == []


@responses.activate
def test_read_forum_thread_parses_posts():
    thread_url = f"{BASE}/ilias.php?thr_pk=456&cmd=viewThread"
    responses.add(responses.GET, thread_url, body=_FORUM_POST_HTML, status=200)
    client = _logged_in_client()

    posts = client.read_forum_thread(thread_url)

    assert posts == [
        {"author": "Prof. Dr. Test", "content": "Die Klausur findet nun am 15.02. statt."}
    ]


@responses.activate
def test_list_exercise_assignments_parses_empty_exercise():
    responses.add(responses.GET, f"{BASE}/ilias.php", body=_EMPTY_EXERCISE_HTML, status=200)
    client = _logged_in_client()

    assert client.list_exercise_assignments("2911807") == []


@responses.activate
def test_list_exercise_assignments_reauths_on_expired_session():
    client, provider = _client_with_expired_session(initially_logged_in=False)
    responses.add(responses.GET, f"{BASE}/ilias.php", body=_NO_ITEMS_HTML, status=200)
    responses.add(responses.GET, f"{BASE}/ilias.php", body=_EMPTY_EXERCISE_HTML, status=200)

    assignments = client.list_exercise_assignments("2911807")

    assert provider.login_calls == 1
    assert assignments == []


@responses.activate
def test_download_file_retries_once_on_html_response(tmp_path):
    # is_logged_in()==True here on purpose: this reproduces a real, live
    # incident (2026-08-24) where a download briefly returned an HTML page
    # instead of the file even though the session looked valid — the
    # proactive is_logged_in() check alone would have missed this.
    client, provider = _client_with_expired_session(initially_logged_in=True)
    responses.add(
        responses.GET,
        f"{BASE}/goto.php/file/42/download",
        body="<html>not the file</html>",
        status=200,
        content_type="text/html",
    )
    responses.add(
        responses.GET,
        f"{BASE}/goto.php/file/42/download",
        body=b"%PDF-1.4 fake pdf bytes",
        status=200,
        content_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="real.pdf"'},
    )

    path = client.download_file("42", tmp_path)

    assert provider.login_calls == 1  # forced re-login despite is_logged_in() saying fine
    assert path.name == "real.pdf"
    assert path.read_bytes() == b"%PDF-1.4 fake pdf bytes"


@responses.activate
def test_download_file_raises_download_error_if_retry_also_fails(tmp_path):
    client, provider = _client_with_expired_session(initially_logged_in=True)
    responses.add(
        responses.GET,
        f"{BASE}/goto.php/file/42/download",
        body="<html>still not the file</html>",
        status=200,
        content_type="text/html",
    )
    responses.add(
        responses.GET,
        f"{BASE}/goto.php/file/42/download",
        body="<html>still not the file</html>",
        status=200,
        content_type="text/html",
    )

    with pytest.raises(DownloadError, match="Retried once"):
        client.download_file("42", tmp_path)

    assert provider.login_calls == 1  # retried exactly once, no infinite loop
