from __future__ import annotations

from .shibboleth import ShibbolethAuthProvider


class KITProvider(ShibbolethAuthProvider):
    """Login provider for KIT's ILIAS instance (ilias.studium.kit.edu) via
    the KIT-Konto / Shibboleth Identity Provider (idp.scc.kit.edu).

    Field names and the redirect chain were verified against the live,
    unauthenticated login page and IdP login form on 2026-08-14 — see
    tests/fixtures/kit_login_page.html and kit_idp_login_form.html.
    """

    name = "kit"
    display_name = "KIT (Karlsruhe Institute of Technology)"
    default_base_url = "https://ilias.studium.kit.edu"
    # KIT's IdP uses the standard Shibboleth IdP field names, so no overrides
    # of username_field_name/password_field_name are needed.
