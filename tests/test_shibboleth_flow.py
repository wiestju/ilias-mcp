from pathlib import Path

import requests
import responses
from bs4 import BeautifulSoup

from ilias_mcp.providers.kit import KITProvider
from ilias_mcp.providers.shibboleth import _first_submit_control, _form_fields

FIXTURES = Path(__file__).parent / "fixtures"
BASE = "https://fake-ilias.example"
IDP = "https://fake-idp.example"


def _credential_form():
    """The IdP login form from a real (unauthenticated) fetch of KIT's
    Shibboleth IdP on 2026-08-14 — see tests/fixtures/kit_idp_login_form.html.
    """
    html = (FIXTURES / "kit_idp_login_form.html").read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "lxml")
    form = soup.find("form", attrs={"action": lambda v: v and "SSO" in v})
    assert form is not None, "fixture no longer contains the expected IdP login form"
    return form


def test_form_fields_extracts_csrf_and_credential_inputs():
    fields = _form_fields(_credential_form())

    assert fields.get("csrf_token")
    assert fields["j_username"] == ""
    assert fields["j_password"] == ""


def test_first_submit_control_is_event_id_proceed():
    name, _value = _first_submit_control(_credential_form())

    assert name == "_eventId_proceed"


@responses.activate
def test_full_login_flow_drives_real_credential_form_and_synthetic_bounce():
    """End-to-end multi-hop login against the real KIT IdP login form plus a
    synthetic SAML-response-relay hop (no real fixture available for that
    part), verifying ShibbolethAuthProvider drives the whole chain correctly
    across two distinct hosts (IdP vs. ILIAS) — mirroring the real
    idp.scc.kit.edu / ilias.studium.kit.edu split, which is what makes the
    "have we returned to the SP?" host check in login() meaningful.
    """
    idp_login_html = (FIXTURES / "kit_idp_login_form.html").read_text(encoding="utf-8")

    # ILIAS bounces the SP-initiated request over to the (separate-host) IdP.
    responses.add(
        responses.GET,
        f"{BASE}/shib_login.php",
        status=302,
        headers={"Location": f"{IDP}/idp/profile/SAML2/Redirect/SSO?execution=e1s1"},
    )
    responses.add(
        responses.GET, f"{IDP}/idp/profile/SAML2/Redirect/SSO", body=idp_login_html, status=200
    )
    # After credentials are accepted, the IdP serves an auto-submitting
    # SAML-response-relay form with an absolute action back to ILIAS's ACS
    # endpoint (this matches the real form observed in a live login: an
    # absolute, cross-host URL rather than a relative path).
    responses.add(
        responses.POST,
        f"{IDP}/idp/profile/SAML2/Redirect/SSO",
        body=(
            f'<html><body><form method="post" action="{BASE}/Shibboleth.sso/SAML2/POST">'
            '<input type="hidden" name="SAMLResponse" value="abc"/>'
            '<input type="hidden" name="RelayState" value="xyz"/>'
            '<button type="submit" name="_eventId_proceed"></button>'
            "</form></body></html>"
        ),
        status=200,
    )
    responses.add(
        responses.POST,
        f"{BASE}/Shibboleth.sso/SAML2/POST",
        body="<html><body>Welcome to the dashboard</body></html>",
        status=200,
    )
    responses.add(
        responses.GET,
        f"{BASE}/ilias.php",
        body="<html><body>Dashboard, no login form here</body></html>",
        status=200,
    )

    provider = KITProvider(base_url=BASE)
    session = requests.Session()

    provider.login(session, {"username": "xy1234", "password": "secret"})

    # No exception means: credential form was recognized and filled in, the
    # synthetic SAML-relay hop was auto-submitted, login stopped as soon as
    # it landed back on the ILIAS host (rather than continuing to auto-submit
    # unrelated forms like the page's search box), and is_logged_in() then
    # found no login form on the (mocked) personal desktop.
    credential_submission = next(
        call.request for call in responses.calls if call.request.url.startswith(f"{IDP}/idp")
        and call.request.method == "POST"
    )
    assert "j_username=xy1234" in credential_submission.body
    assert "j_password=secret" in credential_submission.body
    # The search-form host-check fix: we must not have hit ilias.php more
    # than once (the is_logged_in check) — a regression here would mean the
    # loop kept auto-submitting unrelated forms after already reaching ILIAS.
    ilias_php_calls = [c for c in responses.calls if c.request.url.startswith(f"{BASE}/ilias.php")]
    assert len(ilias_php_calls) == 1
