from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from bs4.element import Tag

from ..exceptions import LoginError
from .base import AuthProvider

# Set ILIAS_MCP_DEBUG_DUMP=1 to write every hop of the login flow to
# ./debug_dumps/ (gitignored). Invaluable when an IdP adds a step (MFA,
# consent, ...) that the generic auto-submit loop below doesn't expect yet.
_DEBUG_DUMP_DIR = Path("debug_dumps")


def _dump(hop: int, resp: requests.Response) -> None:
    if os.environ.get("ILIAS_MCP_DEBUG_DUMP") != "1":
        return
    _DEBUG_DUMP_DIR.mkdir(exist_ok=True)
    (_DEBUG_DUMP_DIR / f"hop_{hop:02d}.html").write_text(resp.text, encoding="utf-8")
    (_DEBUG_DUMP_DIR / f"hop_{hop:02d}.url.txt").write_text(resp.url, encoding="utf-8")


def _form_fields(form: Tag) -> dict[str, str]:
    data: dict[str, str] = {}
    for inp in form.find_all("input"):
        name = inp.get("name")
        if not name:
            continue
        itype = (inp.get("type") or "text").lower()
        if itype in ("checkbox", "radio"):
            if inp.has_attr("checked"):
                data[name] = inp.get("value", "on")
            continue
        if itype in ("submit", "button", "image", "reset", "file"):
            continue
        data[name] = inp.get("value", "")
    return data


def _first_submit_control(form: Tag) -> tuple[str, str] | None:
    for tag in form.find_all(["button", "input"]):
        default_type = "submit" if tag.name == "button" else "text"
        itype = (tag.get("type") or default_type).lower()
        if itype == "submit" and tag.get("name"):
            return tag["name"], tag.get("value", "")
    return None


def _submit_form(
    session: requests.Session,
    response: requests.Response,
    form: Tag,
    overrides: Mapping[str, str] | None = None,
) -> requests.Response:
    url = urljoin(response.url, form.get("action") or response.url)
    method = (form.get("method") or "get").lower()
    data = _form_fields(form)
    submit = _first_submit_control(form)
    if submit is not None:
        data[submit[0]] = submit[1]
    if overrides:
        data.update(overrides)
    if method == "post":
        return session.post(url, data=data)
    return session.get(url, params=data)


class ShibbolethAuthProvider(AuthProvider):
    """Generic login provider for ILIAS instances that authenticate via a
    Shibboleth/SAML2 Identity Provider (the standard setup at most German
    universities).

    The flow, verified against KIT's public (unauthenticated) pages:

    1. GET ``{base_url}/shib_login.php`` — ILIAS redirects into the SAML2
       SSO flow, which itself redirects to the IdP's login form.
    2. The IdP's login form is submitted with the username/password fields.
    3. The IdP responds with one or more auto-submitting intermediary forms
       (SAML response relay back to the SP, local-storage bounce, attribute
       release consent, ...). Each is submitted as-is with its default field
       values until we land back on a plain page.
    4. ``AuthProvider.is_logged_in`` confirms the ILIAS session is authenticated.

    Subclass and set ``default_base_url`` (and, if a given IdP deviates from
    standard Shibboleth IdP field names, ``username_field_name`` /
    ``password_field_name``) to support another institution.
    """

    credential_fields = ("username", "password")

    #: Field names on the IdP's own login form (Shibboleth IdP default: j_username/j_password).
    username_field_name: str = "j_username"
    password_field_name: str = "j_password"
    #: Path (relative to base_url) that kicks off the SP-initiated SSO flow.
    shib_login_path: str = "/shib_login.php"
    #: Safety cap on auto-submitted intermediary hops before giving up.
    max_hops: int = 8

    def login(self, session: requests.Session, credentials: Mapping[str, str]) -> None:
        try:
            username = credentials["username"]
            password = credentials["password"]
        except KeyError as exc:
            raise LoginError(f"Missing credential field: {exc}") from exc

        resp = session.get(f"{self.base_url}{self.shib_login_path}")
        _dump(0, resp)
        credentials_submitted = False

        for hop in range(1, self.max_hops + 1):
            soup = BeautifulSoup(resp.text, "lxml")
            form = soup.find("form")
            if form is None:
                break  # plain page, no further auto-submit possible

            if form.find("input", attrs={"name": self.username_field_name}):
                if credentials_submitted:
                    raise LoginError(
                        f"{self.display_name}: the IdP asked for the login form again "
                        "after credentials were already submitted — likely wrong "
                        "username/password."
                    )
                resp = _submit_form(
                    session,
                    resp,
                    form,
                    overrides={
                        self.username_field_name: username,
                        self.password_field_name: password,
                    },
                )
                credentials_submitted = True
            else:
                # Generic auto-submit hop: SAML response relay, storage
                # bounce, attribute-release consent with pre-checked
                # defaults, etc. — same thing a browser's onload JS does.
                resp = _submit_form(session, resp, form)

            _dump(hop, resp)

        if not self.is_logged_in(session):
            raise LoginError(
                f"Login via {self.display_name} did not result in an authenticated "
                "ILIAS session. Check your credentials, or the IdP flow may have "
                "changed (e.g. an extra MFA/consent step). Rerun with "
                "ILIAS_MCP_DEBUG_DUMP=1 to capture each hop's HTML into ./debug_dumps/."
            )
