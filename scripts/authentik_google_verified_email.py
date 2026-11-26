#!/usr/bin/env python3
"""Safely install a Google-source verified-email mapping in authentik.

Default is dry-run. This script only creates/attaches an OAuth Source *user*
property mapping. It does NOT create users, mail accounts, app permissions,
or change any existing MailFlow/WordPress identities.

Authentication is a short-lived admin API token entered interactively; the
token is never placed on the process command line or printed.
"""
from __future__ import annotations

import argparse
import getpass
import json
import pathlib
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request

SOURCE_SLUG = "google-edanks"
MAPPING_NAME = "RootedOps - Google Workspace edanks.com verified email"
BASE_URL = "https://auth.danks.store"
EXPRESSION_PATH = pathlib.Path(__file__).resolve().parents[1] / "config" / "authentik" / "google_edanks_verified_email.py"


class ApiError(RuntimeError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ApiError("Unexpected HTTP redirect: refusing to forward credentials")


class AuthentikApi:
    def __init__(self, base_url: str, token: str):
        if base_url != BASE_URL:
            raise ApiError(f"Only the expected production origin {BASE_URL} is permitted")
        if not token.strip():
            raise ApiError("API token is required")
        self.base = base_url + "/api/v3"
        self.token = token.strip()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=ssl.create_default_context()),
            NoRedirect(),
        )

    def request(self, method: str, path: str, payload: dict | None = None) -> dict:
        if not path.startswith("/") or path.startswith("//") or "://" in path:
            raise ApiError("Unsafe API path")
        raw = None if payload is None else json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.base + path,
            data=raw,
            method=method,
            headers={
                "Authorization": "Bearer " + self.token,
                "Accept": "application/json",
                **({"Content-Type": "application/json"} if payload is not None else {}),
            },
        )
        try:
            with self.opener.open(req, timeout=20) as res:
                if res.status not in (200, 201):
                    raise ApiError(f"HTTP {res.status} on {method} {path}")
                return json.load(res)
        except urllib.error.HTTPError as err:
            # Do not leak API responses; errors can include sensitive config.
            raise ApiError(f"HTTP {err.code} on {method} {path}") from None
        except urllib.error.URLError as err:
            raise ApiError(f"Network/TLS failure on {method} {path}: {err.reason}") from None

    def oauth_mappings(self) -> list[dict]:
        results: list[dict] = []
        page = 1
        while True:
            data = self.request("GET", f"/propertymappings/source/oauth/?page_size=100&page={page}")
            rows = data.get("results")
            if not isinstance(rows, list):
                raise ApiError("Unexpected mapping API response")
            results.extend(rows)
            if not data.get("next"):
                break
            page += 1
            if page > 100:
                raise ApiError("Mapping pagination exceeded safety limit")
        return results


def plan(source: dict, mappings: list[dict], expression: str) -> dict:
    if source.get("slug") != SOURCE_SLUG:
        raise ApiError("Expected Google source slug not found")
    if source.get("provider_type") != "google":
        raise ApiError("Source is not a Google OAuth source; refusing change")
    selected = source.get("user_property_mappings")
    if not isinstance(selected, list) or not all(isinstance(x, str) for x in selected):
        raise ApiError("Source user property mappings missing or malformed")

    matches = [m for m in mappings if m.get("name") == MAPPING_NAME]
    if len(matches) > 1:
        raise ApiError("Duplicate mapping names; reconcile manually")
    current = matches[0] if matches else None
    if current and current.get("expression", "").strip() != expression.strip():
        raise ApiError("Existing mapping expression differs; manual review required")
    pk = current.get("pk") if current else None
    if current and (not isinstance(pk, str) or not pk):
        raise ApiError("Existing mapping UUID malformed")
    return {
        "create": current is None,
        "attach": current is None or pk not in selected,
        "mapping_pk": pk,
        "existing_mappings": list(selected),
        "mapping_count": len(selected),
    }


def run(api: AuthentikApi, expression: str, apply: bool) -> None:
    source = api.request("GET", f"/sources/oauth/{SOURCE_SLUG}/")
    current = plan(source, api.oauth_mappings(), expression)

    print(f"Verified source: {SOURCE_SLUG} (Google OAuth)")
    print(f"Existing user mappings preserved: {current['mapping_count']}")
    print(f"Mapping creation needed: {current['create']}")
    print(f"Mapping attachment needed: {current['attach']}")
    if not apply:
        print("DRY RUN: no changes performed. Re-run with --apply to install.")
        return
    if not current["create"] and not current["attach"]:
        print("ALREADY CONFIGURED: no changes performed.")
        return

    mapping_pk = current["mapping_pk"]
    if current["create"]:
        created = api.request(
            "POST", "/propertymappings/source/oauth/",
            {"name": MAPPING_NAME, "expression": expression},
        )
        mapping_pk = created.get("pk")
        if not isinstance(mapping_pk, str) or not mapping_pk:
            raise ApiError("Mapping created but response lacked UUID; inspect admin UI before retry")
        print("Created verified-email source mapping.")

    # Re-read the source to avoid overwriting another admin's changed associations.
    source_after = api.request("GET", f"/sources/oauth/{SOURCE_SLUG}/")
    selected_after = source_after.get("user_property_mappings")
    if not isinstance(selected_after, list) or not all(isinstance(x, str) for x in selected_after):
        raise ApiError("Source mappings changed unexpectedly; review before attaching")
    if mapping_pk not in selected_after:
        api.request(
            "PATCH", f"/sources/oauth/{SOURCE_SLUG}/",
            {"user_property_mappings": selected_after + [mapping_pk]},
        )
        print("Attached source mapping without removing existing mappings.")
    verification = api.request("GET", f"/sources/oauth/{SOURCE_SLUG}/")
    if mapping_pk not in verification.get("user_property_mappings", []):
        raise ApiError("Mapping attachment did not verify")
    print("CONFIGURED: mapping is attached. No user accounts or entitlements were changed.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write changes after safe preflight")
    args = parser.parse_args()
    expression = EXPRESSION_PATH.read_text(encoding="utf-8")
    try:
        token = getpass.getpass("authentik admin API token (hidden): ")
        api = AuthentikApi(BASE_URL, token)
        run(api, expression, args.apply)
    except (ApiError, KeyboardInterrupt, EOFError) as err:
        print(f"STOP: {err or 'interrupted'}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
