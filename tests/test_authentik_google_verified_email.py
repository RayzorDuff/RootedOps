"""Offline regression checks for authentik Google OAuth verified-email automation."""
import importlib.util
import pathlib
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("authentik_google_verified_email", ROOT / "scripts" / "authentik_google_verified_email.py")
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)

EXPR = (ROOT / "config" / "authentik" / "google_edanks_verified_email.py").read_text()
SRC = {"slug": "google-edanks", "provider_type": "google", "user_property_mappings": ["existing-pk"]}


def evaluate(info):
    scope = {"info": info}
    exec(EXPR, scope)
    return scope  # Note: top-level return requires wrapping into function.


def evaluate_expression(info):
    compiled = "def mapping(info):\n" + "".join("    " + line for line in EXPR.splitlines(keepends=True))
    ns = {}
    exec(compiled, ns)
    return ns["mapping"](info)


class ClientHeaderTests(unittest.TestCase):
    def test_api_uses_cloudflare_accepted_user_agent_without_exposing_token(self):
        class FakeResponse:
            status = 200
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self):
                return b'{"ok": true}'

        api = mod.AuthentikApi(mod.BASE_URL, "test-private-token")
        with patch.object(api.opener, "open", return_value=FakeResponse()) as opener:
            # The fake response only validates request construction, no network.
            result = api.request("GET", "/sources/oauth/google-edanks/")
            self.assertEqual(result["ok"], True)
            sent = opener.call_args.args[0]
            self.assertEqual(sent.get_header("User-agent"), "curl/8.0.1")
            self.assertEqual(sent.get_header("Authorization"), "Bearer test-private-token")


class VerifiedEmailTests(unittest.TestCase):
    def test_google_verified_is_passed_through(self):
        self.assertEqual(evaluate_expression({"email": "  CORMAC@EDANKS.COM  ", "email_verified": True}),
                         {"attributes": {"email_verified_address": "cormac@edanks.com"}})

    def test_google_v1_verified_email_claim(self):
        self.assertEqual(evaluate_expression({"email": "cormac@edanks.com", "verified_email": True}),
                         {"attributes": {"email_verified_address": "cormac@edanks.com"}})
        self.assertEqual(evaluate_expression({"email": "cormac@edanks.com", "verified_email": False}),
                         {"attributes": {"email_verified_address": ""}})

    def test_negative_cases_fail_closed(self):
        for value in (False, None, "true", 1):
            with self.subTest(value=value):
                self.assertEqual(evaluate_expression({"email": "cormac@edanks.com", "email_verified": value}),
                                 {"attributes": {"email_verified_address": ""}})
        self.assertEqual(evaluate_expression({"email": "cormac@gmail.com", "email_verified": True}),
                         {"attributes": {"email_verified_address": ""}})
        self.assertEqual(evaluate_expression({"email": "cormac@evil-edanks.com", "email_verified": True}),
                         {"attributes": {"email_verified_address": ""}})
        self.assertEqual(evaluate_expression({}), {"attributes": {"email_verified_address": ""}})

    def test_planning_never_overwrites_other_mappings(self):
        p = mod.plan(SRC, [], EXPR)
        self.assertTrue(p["create"])
        self.assertEqual(p["existing_mappings"], ["existing-pk"])
        existing = {"name": mod.MAPPING_NAME, "expression": EXPR, "pk": "mapping-uuid"}
        p = mod.plan({**SRC, "user_property_mappings": ["existing-pk", "mapping-uuid"]}, [existing], EXPR)
        self.assertFalse(p["create"])
        self.assertFalse(p["attach"])

    def test_conflicting_expression_fails(self):
        existing = {"name": mod.MAPPING_NAME, "expression": "return {'email_verified': True}", "pk": "mapping-uuid"}
        with self.assertRaises(mod.ApiError):
            mod.plan(SRC, [existing], EXPR)

    def test_wrong_source_and_invalid_mappings_fail(self):
        for altered in ({**SRC, "provider_type": "apple"}, {**SRC, "slug": "google-rootedpsyche"},
                        {**SRC, "user_property_mappings": None}):
            with self.assertRaises(mod.ApiError):
                mod.plan(altered, [], EXPR)


class FakeApi:
    def __init__(self):
        self.source = {**SRC}
        self.mappings = []
        self.mutations = []
    def oauth_mappings(self):
        return self.mappings
    def request(self, method, path, payload=None):
        if method == "GET" and path == "/sources/oauth/google-edanks/":
            return self.source
        if method == "POST":
            self.mutations.append((method, path, payload))
            row = {**payload, "pk": "map-id"}
            self.mappings.append(row)
            return row
        if method == "PATCH":
            self.mutations.append((method, path, payload))
            self.source = {**self.source, **payload}
            return self.source
        raise ValueError((method, path))


class ApplyTests(unittest.TestCase):
    def test_dry_run_idempotent_apply_preserves_existing(self):
        api = FakeApi()
        mod.run(api, EXPR, False)
        self.assertEqual(api.mutations, [])
        mod.run(api, EXPR, True)
        self.assertEqual(api.source["user_property_mappings"], ["existing-pk", "map-id"])
        self.assertEqual(len(api.mutations), 2)
        mod.run(api, EXPR, True)
        self.assertEqual(len(api.mutations), 2)


if __name__ == "__main__":
    unittest.main()
