#!/usr/bin/env python3
"""Read-only Workspace directory lookup; run on administrator's desktop.
Keep OAuth files outside the repository. Output is private operational data.
"""
import argparse
import json
import os
from pathlib import Path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPE = "https://www.googleapis.com/auth/admin.directory.user.readonly"

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--token", type=Path, required=True)
    parser.add_argument("--domain", required=True)
    parser.add_argument("--control-email", required=True)
    parser.add_argument("--workspace-email", required=True)
    args = parser.parse_args()
    os.umask(0o077)
    if args.credentials.resolve() == args.token.resolve():
        parser.error("Credentials and token must be separate files")
    for path in (args.credentials, args.token):
        if path.exists() and (path.is_symlink() or path.stat().st_mode & 0o077):
            parser.error("OAuth files must be private regular files (chmod 600)")
    emails = [args.control_email.strip().lower(), args.workspace_email.strip().lower()]
    if emails[0] == emails[1] or any(e.count("@") != 1 or e.split("@")[1] != args.domain.lower() for e in emails):
        parser.error("Require distinct primary addresses in the approved domain")
    credentials = None
    if args.token.exists():
        credentials = Credentials.from_authorized_user_file(str(args.token), [SCOPE])
    if credentials and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
    if not credentials or not credentials.valid:
        flow = InstalledAppFlow.from_client_secrets_file(str(args.credentials), [SCOPE])
        credentials = flow.run_local_server(host="127.0.0.1", port=0)
    args.token.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(args.token, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as handle:
        handle.write(credentials.to_json())
    service = build("admin", "directory_v1", credentials=credentials, cache_discovery=False)
    records = []
    for email in emails:
        record = service.users().get(userKey=email, fields="id,primaryEmail,suspended,archived,customerId,name(fullName)").execute()
        if record.get("primaryEmail", "").lower() != email or record.get("suspended") is not False or record.get("archived") is not False:
            raise SystemExit("Refusing alias, inactive or incomplete directory record")
        identifier = record.get("id", "")
        if not identifier.isascii() or not identifier.isdigit() or not 10 <= len(identifier) <= 32:
            raise SystemExit("Unexpected directory identifier")
        records.append(record)
    if not records[0].get("customerId") or records[0]["customerId"] != records[1].get("customerId") or records[0]["id"] == records[1]["id"]:
        raise SystemExit("Directory control and target must be distinct members of the same customer")
    print(json.dumps({"control_email": emails[0], "control_identifier": records[0]["id"],
                      "workspace_email": emails[1], "google_identifier": records[1]["id"],
                      "display_name": records[1].get("name", {}).get("fullName", emails[1])}))

if __name__ == "__main__":
    main()
