"""Controlled Plaid historical Bank Transaction backfill for RootedOps.

The default flow is read-only staging through a temporary Plaid Hosted Link Item.
A separate prepare/commit gate can then create only reviewed historical native
ERPNext Bank Transaction records. It never creates accounting vouchers or performs
reconciliation, and it never replaces the production Plaid Item/token/account IDs.
"""

from collections import Counter
from datetime import date
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from uuid import uuid4

import frappe
import requests
from frappe.desk.doctype.tag.tag import add_tag
from frappe.utils import getdate, today

from rootedops_payroll.services.plaid_history_matching import (
    assign_db_safe_transaction_ids,
    classify_transaction_overlap,
    deterministic_plan_hash,
    match_candidate_accounts,
    plaid_bank_transaction_fields,
    plaid_transaction_tags,
    validate_backfill_classifications,
)


DEFAULT_DAYS_REQUESTED = 730
DEFAULT_URL_LIFETIME_SECONDS = 3600
SESSION_ID_RE = re.compile(r"^[0-9a-f]{32}$")

BACKFILL_PROFILES = {
    "high_plains_2026": {
        "bank": "High Plains Bank (HPBGO)",
        "institution_id": "ins_115322",
        "start_date": "2026-01-01",
        "bank_accounts": [
            "Dank Mushrooms Checking - High Plains Bank",
            "Dank Mushrooms Withholding - High Plains Bank",
        ],
    },
    "elevations_2026": {
        "bank": "Elevations Credit Union",
        "institution_id": "ins_110005",
        "start_date": "2026-01-01",
        "bank_accounts": [
            "Raymond Danks Elevations Checking - Elevations Credit Union",
            "Raymond Danks Elevations Withholding Savings - Elevations Credit Union",
        ],
    },
}


class PlaidHistoricalBackfillError(RuntimeError):
    pass


class PlaidAPIError(PlaidHistoricalBackfillError):
    def __init__(self, path, response):
        self.path = path
        self.status_code = response.status_code
        try:
            payload = response.json()
        except Exception:
            payload = {}
        self.error_type = payload.get("error_type")
        self.error_code = payload.get("error_code")
        self.error_message = payload.get("error_message")
        self.request_id = payload.get("request_id")
        super().__init__(
            f"{path} failed: HTTP {self.status_code}; "
            f"{self.error_type or 'UNKNOWN'} / {self.error_code or 'UNKNOWN'}; "
            f"{self.error_message or 'no message'}; request_id={self.request_id or 'unknown'}"
        )


def _fingerprint(value):
    if not value:
        return None
    return sha256(str(value).encode()).hexdigest()[:12]


def _profile(name):
    try:
        return BACKFILL_PROFILES[name]
    except KeyError as exc:
        raise PlaidHistoricalBackfillError(
            f"Unknown profile {name!r}; expected one of {sorted(BACKFILL_PROFILES)}"
        ) from exc


def _session_dir():
    path = Path(frappe.get_site_path("private", "rootedops", "plaid_history"))
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        path.chmod(0o700)
    except OSError:
        pass
    return path


def _session_path(session_id):
    if not SESSION_ID_RE.fullmatch(str(session_id or "")):
        raise PlaidHistoricalBackfillError("Invalid historical Plaid session ID")
    return _session_dir() / f"{session_id}.json"


def _report_path(session_id):
    return _session_dir() / f"{session_id}.dry_run.json"


def _receipt_path(session_id):
    return _session_dir() / f"{session_id}.import_receipt.json"


def _atomic_private_json_write(path, payload):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    data = json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n"
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        try:
            path.chmod(0o600)
        except OSError:
            pass
    finally:
        if temporary.exists():
            temporary.unlink()


def _load_state(session_id):
    path = _session_path(session_id)
    if not path.exists():
        raise PlaidHistoricalBackfillError(f"Historical Plaid session {session_id} was not found")
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _save_state(state):
    _atomic_private_json_write(_session_path(state["session_id"]), state)


def _plaid_context():
    settings = frappe.get_single("Plaid Settings")
    if not settings.enabled:
        raise PlaidHistoricalBackfillError("ERPNext Plaid Settings are disabled")
    secret = settings.get_password("plaid_secret")
    if not settings.plaid_client_id or not secret:
        raise PlaidHistoricalBackfillError("ERPNext Plaid credentials are incomplete")
    return {
        "base_url": f"https://{settings.plaid_env}.plaid.com",
        "environment": settings.plaid_env,
        "client_id": settings.plaid_client_id,
        "secret": secret,
    }


def _plaid_post(context, path, payload, timeout=60):
    body = {
        "client_id": context["client_id"],
        "secret": context["secret"],
        **payload,
    }
    response = requests.post(
        context["base_url"] + path,
        json=body,
        timeout=timeout,
    )
    if response.status_code != 200:
        raise PlaidAPIError(path, response)
    try:
        return response.json()
    except Exception as exc:
        raise PlaidHistoricalBackfillError(f"{path} returned a non-JSON response") from exc


def _current_live_item(profile, context):
    access_token = frappe.db.get_value("Bank", profile["bank"], "plaid_access_token")
    if not access_token:
        raise PlaidHistoricalBackfillError(f"{profile['bank']} has no live Plaid access token")
    response = _plaid_post(context, "/item/get", {"access_token": access_token})
    item = response.get("item") or {}
    if item.get("institution_id") != profile["institution_id"]:
        raise PlaidHistoricalBackfillError(
            f"Live {profile['bank']} Item institution changed: expected "
            f"{profile['institution_id']}, got {item.get('institution_id')}"
        )
    item_error = item.get("error") or {}
    if item_error:
        raise PlaidHistoricalBackfillError(
            f"Live {profile['bank']} Plaid Item is no longer healthy: "
            f"{item_error.get('error_type') or 'UNKNOWN'} / "
            f"{item_error.get('error_code') or 'UNKNOWN'}; "
            f"{item_error.get('error_message') or 'no message'}"
        )
    return access_token, item


def _extract_item_add_result(link_token_response):
    sessions = link_token_response.get("link_sessions") or []
    for session in reversed(sessions):
        results = session.get("results") or {}
        item_results = results.get("item_add_results") or []
        if item_results:
            if len(item_results) != 1:
                raise PlaidHistoricalBackfillError(
                    "Historical backfill expects exactly one Item from the Hosted Link session"
                )
            return item_results[0], session

        # Compatibility fallback for legacy Hosted Link responses.
        on_success = session.get("on_success") or {}
        if on_success.get("public_token"):
            metadata = on_success.get("metadata") or {}
            return {
                "public_token": on_success.get("public_token"),
                "institution": metadata.get("institution"),
                "accounts": metadata.get("accounts") or [],
            }, session
    return None, sessions[-1] if sessions else None


def _ensure_candidate_token(state, context, allow_institution_mismatch=False):
    if state.get("candidate_access_token"):
        return state

    link_result = _plaid_post(
        context,
        "/link/token/get",
        {"link_token": state["link_token"]},
    )
    item_result, link_session = _extract_item_add_result(link_result)
    if not item_result:
        status = None
        if link_session:
            status = link_session.get("finished_at") or "started"
        raise PlaidHistoricalBackfillError(
            "Hosted Link has not completed successfully yet"
            + (f" (session status: {status})" if status else "")
        )

    institution = item_result.get("institution") or {}
    linked_institution_id = institution.get("institution_id")
    state["linked_institution_id"] = linked_institution_id
    state["linked_institution_name"] = institution.get("name")

    if linked_institution_id != state["expected_institution_id"] and not allow_institution_mismatch:
        _save_state(state)
        raise PlaidHistoricalBackfillError(
            f"Hosted Link connected {institution.get('name') or linked_institution_id}, but this "
            f"session expects institution {state['expected_institution_id']}. Do not inspect or import it; "
            "run cleanup_session(..., confirm=True) while the Link result is still available."
        )

    public_token = item_result.get("public_token")
    if not public_token:
        raise PlaidHistoricalBackfillError("Completed Hosted Link session did not return a public token")

    exchange = _plaid_post(
        context,
        "/item/public_token/exchange",
        {"public_token": public_token},
    )
    state["candidate_access_token"] = exchange.get("access_token")
    state["candidate_item_id"] = exchange.get("item_id")
    state["candidate_access_token_fingerprint"] = _fingerprint(exchange.get("access_token"))
    state["candidate_item_id_fingerprint"] = _fingerprint(exchange.get("item_id"))
    state["link_completed_at"] = link_session.get("finished_at") if link_session else None
    _save_state(state)
    return state


def _plaid_accounts(context, access_token):
    response = _plaid_post(context, "/accounts/get", {"access_token": access_token})
    return response.get("accounts") or []


def _canonical_live_accounts(profile, context, live_access_token):
    live_accounts = {
        account.get("account_id"): account
        for account in _plaid_accounts(context, live_access_token)
    }
    result = []
    for bank_account_name in profile["bank_accounts"]:
        row = frappe.db.get_value(
            "Bank Account",
            bank_account_name,
            ["integration_id", "mask", "account_type", "account_subtype"],
            as_dict=True,
        )
        if not row:
            raise PlaidHistoricalBackfillError(f"Canonical Bank Account not found: {bank_account_name}")
        live = live_accounts.get(row.integration_id) or {}
        result.append(
            {
                "bank_account": bank_account_name,
                "account_id": row.integration_id,
                "mask": live.get("mask") or row.mask,
                "type": live.get("type") or row.account_type,
                "subtype": live.get("subtype") or row.account_subtype,
                "name": live.get("name"),
                "official_name": live.get("official_name"),
            }
        )
    return result


def _transactions_update_status(context, access_token):
    """Use the modern read endpoint only to distinguish initial from full historical readiness."""
    response = _plaid_post(
        context,
        "/transactions/sync",
        {"access_token": access_token, "count": 1},
    )
    return response.get("transactions_update_status")


def _fetch_transactions(context, access_token, account_id, start_date, end_date):
    transactions = []
    offset = 0
    while True:
        response = _plaid_post(
            context,
            "/transactions/get",
            {
                "access_token": access_token,
                "start_date": start_date,
                "end_date": end_date,
                "options": {
                    "account_ids": [account_id],
                    "count": 500,
                    "offset": offset,
                },
            },
        )
        batch = response.get("transactions") or []
        transactions.extend(batch)
        total = response.get("total_transactions", len(transactions))
        if not batch or len(transactions) >= total:
            return transactions
        offset = len(transactions)


def _existing_bank_transactions(bank_account):
    rows = frappe.db.get_all(
        "Bank Transaction",
        filters={"bank_account": bank_account, "docstatus": ["!=", 2]},
        fields=[
            "name",
            "bank_account",
            "date",
            "deposit",
            "withdrawal",
            "transaction_id",
            "transaction_type",
            "reference_number",
            "description",
        ],
        order_by="date asc, name asc",
    )
    for row in rows:
        row["date"] = str(row.get("date") or "")
    return rows


def _candidate_record(bank_account, transaction):
    fields = plaid_bank_transaction_fields(transaction)
    return {
        "bank_account": bank_account,
        **fields,
        "pending": bool(transaction.get("pending")),
        "authorized_date": transaction.get("authorized_date"),
        "merchant_name": transaction.get("merchant_name"),
        "tags": plaid_transaction_tags(transaction),
    }


def _summary_for_classifications(classifications):
    statuses = Counter(row.get("status") for row in classifications)
    months = Counter()
    for row in classifications:
        if row.get("date"):
            months[str(row["date"])[:7]] += 1
    return {
        "status_counts": dict(sorted(statuses.items())),
        "monthly_counts": dict(sorted(months.items())),
    }


def create_hosted_link(profile="high_plains_2026", days_requested=DEFAULT_DAYS_REQUESTED, url_lifetime_seconds=DEFAULT_URL_LIFETIME_SECONDS):
    """Create a temporary 730-day Hosted Link session without changing ERPNext Plaid records."""
    profile_config = _profile(profile)
    days_requested = int(days_requested)
    url_lifetime_seconds = int(url_lifetime_seconds)
    if not 1 <= days_requested <= 730:
        raise PlaidHistoricalBackfillError("days_requested must be between 1 and 730")
    if not 1 <= url_lifetime_seconds <= 21 * 24 * 60 * 60:
        raise PlaidHistoricalBackfillError("url_lifetime_seconds must be between 1 second and 21 days")

    context = _plaid_context()
    live_access_token, live_item = _current_live_item(profile_config, context)
    session_id = uuid4().hex

    response = _plaid_post(
        context,
        "/link/token/create",
        {
            "user": {"client_user_id": f"rootedops-history-{session_id}"},
            "client_name": "RootedOps Historical Bank Backfill",
            "products": ["transactions"],
            "country_codes": ["US"],
            "language": "en",
            "transactions": {"days_requested": days_requested},
            "hosted_link": {"url_lifetime_seconds": url_lifetime_seconds},
        },
    )

    if not response.get("hosted_link_url") or not response.get("link_token"):
        raise PlaidHistoricalBackfillError("Plaid did not return a Hosted Link URL and link token")

    state = {
        "schema_version": 1,
        "session_id": session_id,
        "profile": profile,
        "bank": profile_config["bank"],
        "canonical_bank_accounts": profile_config["bank_accounts"],
        "expected_institution_id": profile_config["institution_id"],
        "requested_start_date": profile_config["start_date"],
        "days_requested": days_requested,
        "environment": context["environment"],
        "link_token": response["link_token"],
        "link_expiration": response.get("expiration"),
        "request_id": response.get("request_id"),
        "live_access_token_fingerprint": _fingerprint(live_access_token),
        "live_item_id_fingerprint": _fingerprint(live_item.get("item_id")),
    }
    _save_state(state)
    frappe.db.rollback()

    return {
        "session_id": session_id,
        "profile": profile,
        "bank": profile_config["bank"],
        "expected_institution_id": profile_config["institution_id"],
        "days_requested": days_requested,
        "hosted_link_url": response["hosted_link_url"],
        "expiration": response.get("expiration"),
        "production_item_fingerprint": state["live_item_id_fingerprint"],
        "instructions": (
            "Open hosted_link_url, connect the expected institution and the same canonical accounts, "
            "then run inspect_session with this session_id. No ERPNext Bank/Bank Account/Bank Transaction "
            "record has been changed."
        ),
    }


def inspect_session(session_id, start_date=None, end_date=None):
    """Exchange the completed temporary Item and produce a no-write overlap/dedup dry run."""
    state = _load_state(session_id)
    profile = _profile(state["profile"])
    context = _plaid_context()
    live_access_token, live_item = _current_live_item(profile, context)

    if _fingerprint(live_access_token) != state.get("live_access_token_fingerprint"):
        raise PlaidHistoricalBackfillError(
            "The production Plaid access token changed after this staging session was created. Stop and investigate."
        )
    if _fingerprint(live_item.get("item_id")) != state.get("live_item_id_fingerprint"):
        raise PlaidHistoricalBackfillError(
            "The production Plaid Item changed after this staging session was created. Stop and investigate."
        )

    state = _ensure_candidate_token(state, context)
    candidate_token = state["candidate_access_token"]
    if candidate_token == live_access_token:
        raise PlaidHistoricalBackfillError("Candidate and production Plaid access tokens are unexpectedly identical")

    candidate_item_response = _plaid_post(context, "/item/get", {"access_token": candidate_token})
    candidate_item = candidate_item_response.get("item") or {}
    if candidate_item.get("institution_id") != profile["institution_id"]:
        raise PlaidHistoricalBackfillError("Candidate Item institution no longer matches the staging profile")
    candidate_error = candidate_item.get("error") or {}
    if candidate_error:
        raise PlaidHistoricalBackfillError(
            "Candidate Plaid Item is not healthy: "
            f"{candidate_error.get('error_type') or 'UNKNOWN'} / "
            f"{candidate_error.get('error_code') or 'UNKNOWN'}; "
            f"{candidate_error.get('error_message') or 'no message'}"
        )

    start_date = str(getdate(start_date or profile["start_date"]))
    end_date = str(getdate(end_date or today()))
    if getdate(start_date) > getdate(end_date):
        raise PlaidHistoricalBackfillError("start_date must be on or before end_date")

    canonical_accounts = _canonical_live_accounts(profile, context, live_access_token)
    candidate_accounts = _plaid_accounts(context, candidate_token)
    mappings = match_candidate_accounts(canonical_accounts, candidate_accounts)

    account_reports = []
    report_transactions = []
    readiness_error = None
    update_status = _transactions_update_status(context, candidate_token)
    transactions_ready = update_status == "HISTORICAL_UPDATE_COMPLETE"
    if not transactions_ready:
        readiness_error = {
            "transactions_update_status": update_status,
            "message": (
                "Plaid has not confirmed the full requested historical pull yet. "
                "Do not interpret currently available recent transactions as the institution's history limit."
            ),
        }

    for mapping in mappings:
        if not transactions_ready:
            account_reports.append({**mapping, "transaction_summary": None})
            continue
        if mapping["status"] != "mapped":
            account_reports.append({**mapping, "transaction_summary": None})
            continue

        try:
            transactions = _fetch_transactions(
                context,
                candidate_token,
                mapping["candidate_account_id"],
                start_date,
                end_date,
            )
        except PlaidAPIError as exc:
            if exc.error_code in {"PRODUCT_NOT_READY", "TRANSACTIONS_NOT_READY"}:
                transactions_ready = False
                readiness_error = {
                    "error_type": exc.error_type,
                    "error_code": exc.error_code,
                    "error_message": exc.error_message,
                    "request_id": exc.request_id,
                }
                account_reports.append({**mapping, "transaction_summary": None})
                continue
            raise

        nonpending = [tx for tx in transactions if not tx.get("pending")]
        candidate_records = [
            _candidate_record(mapping["bank_account"], tx)
            for tx in nonpending
        ]
        existing = _existing_bank_transactions(mapping["bank_account"])
        classifications = classify_transaction_overlap(candidate_records, existing)
        summary = _summary_for_classifications(classifications)
        summary.update(
            {
                "plaid_total": len(transactions),
                "nonpending_total": len(nonpending),
                "pending_total": len(transactions) - len(nonpending),
                "earliest_candidate_date": min((r["date"] for r in candidate_records), default=None),
                "latest_candidate_date": max((r["date"] for r in candidate_records), default=None),
                "existing_erpnext_total": len(existing),
            }
        )
        account_reports.append({**mapping, "transaction_summary": summary})
        report_transactions.extend(classifications)

    report = {
        "schema_version": 1,
        "generated_on": str(today()),
        "session_id": session_id,
        "profile": state["profile"],
        "bank": profile["bank"],
        "expected_institution_id": profile["institution_id"],
        "production_item_id_fingerprint": _fingerprint(live_item.get("item_id")),
        "candidate_item_id_fingerprint": _fingerprint(candidate_item.get("item_id")),
        "requested_range": {"start_date": start_date, "end_date": end_date},
        "transactions_ready": transactions_ready,
        "transactions_update_status": update_status,
        "readiness_error": readiness_error,
        "account_mappings": account_reports,
        "candidate_transactions": report_transactions,
        "safety": {
            "bank_transaction_writes": 0,
            "bank_account_writes": 0,
            "bank_writes": 0,
            "journal_entry_writes": 0,
            "production_plaid_token_changed": False,
        },
    }
    report_path = _report_path(session_id)
    _atomic_private_json_write(report_path, report)
    state["last_report_path"] = str(report_path)
    state["last_inspected_range"] = {"start_date": start_date, "end_date": end_date}
    _save_state(state)
    frappe.db.rollback()

    overall_statuses = Counter(row.get("status") for row in report_transactions)
    return {
        "session_id": session_id,
        "profile": state["profile"],
        "bank": profile["bank"],
        "production_item_fingerprint": _fingerprint(live_item.get("item_id")),
        "candidate_item_fingerprint": _fingerprint(candidate_item.get("item_id")),
        "production_item_unchanged": True,
        "transactions_ready": transactions_ready,
        "transactions_update_status": update_status,
        "readiness_error": readiness_error,
        "account_mappings": account_reports,
        "overall_transaction_status_counts": dict(sorted(overall_statuses.items())),
        "dry_run_report": str(report_path),
        "bank_transaction_writes": 0,
        "next_step": (
            "Review this output and the private dry-run report. Do not import yet."
            if transactions_ready
            else "Historical Transactions are still initializing at Plaid; rerun inspect_session later."
        ),
    }



def _load_dry_run_report(session_id):
    path = _report_path(session_id)
    if not path.exists():
        raise PlaidHistoricalBackfillError(
            "No dry-run report exists for this session; run inspect_session first"
        )
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _coverage_boundaries(profile):
    boundaries = {}
    for bank_account in profile["bank_accounts"]:
        earliest = frappe.db.sql(
            """
            SELECT MIN(date)
            FROM `tabBank Transaction`
            WHERE bank_account = %s
              AND docstatus != 2
            """,
            (bank_account,),
        )[0][0]
        if not earliest:
            raise PlaidHistoricalBackfillError(
                f"Canonical Bank Account {bank_account!r} has no existing Bank Transaction coverage"
            )
        boundaries[bank_account] = str(earliest)
    return boundaries


def _canonical_plan_transaction(row):
    return {
        "bank_account": row.get("bank_account"),
        "date": str(row.get("date") or ""),
        "deposit": str(row.get("deposit") or "0"),
        "withdrawal": str(row.get("withdrawal") or "0"),
        "currency": row.get("currency") or "",
        "transaction_id": row.get("transaction_id") or "",
        "source_transaction_id": row.get("source_transaction_id") or row.get("transaction_id") or "",
        "storage_transaction_id": row.get("storage_transaction_id") or row.get("transaction_id") or "",
        "transaction_type": row.get("transaction_type") or "",
        "reference_number": row.get("reference_number") or "",
        "description": row.get("description") or "",
        "tags": sorted(row.get("tags") or []),
        "status": row.get("status"),
        "match_method": row.get("match_method"),
        "existing_names": sorted(row.get("existing_names") or []),
    }


def _build_import_plan(session_id, report):
    state = _load_state(session_id)
    profile = _profile(state["profile"])

    if not report.get("transactions_ready") or report.get("transactions_update_status") != "HISTORICAL_UPDATE_COMPLETE":
        raise PlaidHistoricalBackfillError(
            "Plaid historical Transactions are not confirmed complete for this session"
        )

    mappings = report.get("account_mappings") or []
    mapping_accounts = {row.get("bank_account") for row in mappings}
    expected_accounts = set(profile["bank_accounts"])
    if mapping_accounts != expected_accounts or any(row.get("status") != "mapped" for row in mappings):
        raise PlaidHistoricalBackfillError(
            "Every canonical Bank Account must have exactly one mapped candidate account before import"
        )

    if frappe.db.get_single_value("Plaid Settings", "automatic_sync"):
        raise PlaidHistoricalBackfillError(
            "Disable Plaid automatic synchronization before preparing or committing a historical import"
        )

    boundaries = _coverage_boundaries(profile)
    try:
        validation = validate_backfill_classifications(
            report.get("candidate_transactions") or [],
            boundaries,
        )
    except ValueError as exc:
        raise PlaidHistoricalBackfillError(str(exc)) from exc

    # Bank Transaction.transaction_id is globally UNIQUE. On this ERPNext/MariaDB
    # deployment the column uses a case-insensitive collation, while Plaid IDs are
    # opaque and case-sensitive. Pull all existing IDs so the reviewed plan can
    # deterministically allocate DB-safe storage IDs before any financial write.
    existing_transaction_ids = frappe.db.get_all(
        "Bank Transaction",
        filters={"transaction_id": ["is", "set"]},
        pluck="transaction_id",
        limit_page_length=0,
    )
    try:
        assigned = assign_db_safe_transaction_ids(
            validation["new_rows"],
            existing_transaction_ids=existing_transaction_ids,
        )
    except ValueError as exc:
        raise PlaidHistoricalBackfillError(str(exc)) from exc

    assigned_by_source = {
        row["source_transaction_id"]: row
        for row in assigned["rows"]
    }
    report_rows = []
    for row in (report.get("candidate_transactions") or []):
        row = dict(row)
        if row.get("status") == "new":
            source = str(row.get("transaction_id") or "").strip()
            allocated = assigned_by_source[source]
            row["source_transaction_id"] = allocated["source_transaction_id"]
            row["storage_transaction_id"] = allocated["storage_transaction_id"]
        report_rows.append(row)

    storage_ids = [row["storage_transaction_id"] for row in assigned["rows"]]
    if storage_ids:
        collisions = frappe.db.get_all(
            "Bank Transaction",
            filters={"transaction_id": ["in", storage_ids]},
            fields=["name", "bank_account", "transaction_id"],
            limit_page_length=0,
        )
        if collisions:
            raise PlaidHistoricalBackfillError(
                "A planned ERPNext storage transaction ID now exists; rerun prepare_import: "
                + ", ".join(row.name for row in collisions[:10])
            )

    plan_transactions = sorted(
        (_canonical_plan_transaction(row) for row in report_rows),
        key=lambda row: (
            row["bank_account"],
            row["date"],
            row["transaction_id"],
            row["status"] or "",
        ),
    )
    plan_payload = {
        "schema_version": 1,
        "session_id": session_id,
        "profile": state["profile"],
        "bank": profile["bank"],
        "production_item_id_fingerprint": report.get("production_item_id_fingerprint"),
        "candidate_item_id_fingerprint": report.get("candidate_item_id_fingerprint"),
        "requested_range": report.get("requested_range"),
        "transactions_update_status": report.get("transactions_update_status"),
        "coverage_boundaries": boundaries,
        "account_mappings": [
            {
                "bank_account": row.get("bank_account"),
                "current_account_id": row.get("current_account_id"),
                "candidate_account_id": row.get("candidate_account_id"),
                "method": row.get("method"),
            }
            for row in sorted(mappings, key=lambda row: row.get("bank_account") or "")
        ],
        "status_counts": validation["status_counts"],
        "per_account_status_counts": validation["per_account_status_counts"],
        "new_count": validation["new_count"],
        "db_safe_transaction_ids": {
            "transformed_count": assigned["transformed_count"],
            "collision_groups": assigned["collision_groups"],
        },
        "transactions": plan_transactions,
    }
    plan_hash = deterministic_plan_hash(plan_payload)
    new_rows = assigned["rows"]
    return plan_hash, plan_payload, new_rows


def prepare_import(session_id, start_date=None, end_date=None):
    """Recompute and validate a deterministic no-write import plan for operator review."""
    inspect_session(session_id, start_date=start_date, end_date=end_date)
    report = _load_dry_run_report(session_id)
    plan_hash, plan, new_rows = _build_import_plan(session_id, report)
    frappe.db.rollback()

    account_new_counts = Counter(row.get("bank_account") for row in new_rows)
    account_ranges = {}
    for account in sorted(account_new_counts):
        dates = sorted(str(row.get("date")) for row in new_rows if row.get("bank_account") == account)
        account_ranges[account] = {
            "new_count": account_new_counts[account],
            "earliest_new_date": dates[0] if dates else None,
            "latest_new_date": dates[-1] if dates else None,
            "existing_coverage_begins": plan["coverage_boundaries"][account],
        }

    return {
        "session_id": session_id,
        "profile": plan["profile"],
        "plan_hash": plan_hash,
        "new_count": len(new_rows),
        "requested_range": plan["requested_range"],
        "status_counts": plan["status_counts"],
        "per_account": account_ranges,
        "db_safe_transaction_ids": plan["db_safe_transaction_ids"],
        "production_item_unchanged": True,
        "bank_transaction_writes": 0,
        "next_step": (
            "Review this exact plan hash/count. Then call commit_import with the same plan_hash, "
            "expected_new_count, and confirm=true."
        ),
    }


def _assert_production_plaid_unchanged(state, profile, context):
    live_access_token, live_item = _current_live_item(profile, context)
    if _fingerprint(live_access_token) != state.get("live_access_token_fingerprint"):
        raise PlaidHistoricalBackfillError("Production Plaid access token changed during historical import")
    if _fingerprint(live_item.get("item_id")) != state.get("live_item_id_fingerprint"):
        raise PlaidHistoricalBackfillError("Production Plaid Item changed during historical import")
    return live_item


def commit_import(session_id, plan_hash, expected_new_count, confirm=False):
    """Create and submit only the exact reviewed historical Bank Transaction plan, then commit."""
    if str(confirm).lower() not in {"1", "true", "yes"}:
        raise PlaidHistoricalBackfillError("commit_import requires confirm=True")
    expected_new_count = int(expected_new_count)
    if expected_new_count <= 0:
        raise PlaidHistoricalBackfillError("expected_new_count must be greater than zero")

    state = _load_state(session_id)
    profile = _profile(state["profile"])
    context = _plaid_context()

    # Re-fetch and reclassify immediately before any write using the exact
    # reviewed date window. This also verifies both production and candidate
    # Plaid Items remain healthy.
    reviewed_range = state.get("last_inspected_range") or {}
    inspect_session(
        session_id,
        start_date=reviewed_range.get("start_date"),
        end_date=reviewed_range.get("end_date"),
    )
    report = _load_dry_run_report(session_id)
    current_hash, plan, new_rows = _build_import_plan(session_id, report)
    if current_hash != str(plan_hash):
        frappe.db.rollback()
        raise PlaidHistoricalBackfillError(
            f"Import plan changed: reviewed {plan_hash}, current {current_hash}. "
            "Run prepare_import again and review the new plan."
        )
    if len(new_rows) != expected_new_count:
        frappe.db.rollback()
        raise PlaidHistoricalBackfillError(
            f"Import count changed: expected {expected_new_count}, current {len(new_rows)}"
        )

    mapping_ids = {
        row["bank_account"]: row["current_account_id"]
        for row in plan["account_mappings"]
    }
    for bank_account, expected_integration_id in mapping_ids.items():
        current_integration_id = frappe.db.get_value("Bank Account", bank_account, "integration_id")
        if current_integration_id != expected_integration_id:
            frappe.db.rollback()
            raise PlaidHistoricalBackfillError(
                f"Production Plaid account ID changed for {bank_account}; aborting import"
            )

    created_names = []
    try:
        for row in sorted(
            new_rows,
            key=lambda item: (item.get("bank_account") or "", str(item.get("date") or ""), item.get("transaction_id") or ""),
        ):
            doc = frappe.get_doc(
                {
                    "doctype": "Bank Transaction",
                    "date": getdate(row["date"]),
                    "bank_account": row["bank_account"],
                    "deposit": row["deposit"],
                    "withdrawal": row["withdrawal"],
                    "currency": row["currency"],
                    "transaction_id": row.get("storage_transaction_id") or row["transaction_id"],
                    "transaction_type": row.get("transaction_type") or "",
                    "reference_number": row.get("reference_number") or "",
                    "description": row.get("description") or "",
                }
            )
            doc.insert()
            doc.submit()
            for tag in row.get("tags") or []:
                add_tag(tag, "Bank Transaction", doc.name)
            created_names.append(doc.name)

        if len(created_names) != expected_new_count:
            raise PlaidHistoricalBackfillError(
                f"Created {len(created_names)} Bank Transactions, expected {expected_new_count}"
            )

        created = frappe.db.get_all(
            "Bank Transaction",
            filters={"name": ["in", created_names]},
            fields=[
                "name",
                "bank_account",
                "date",
                "deposit",
                "withdrawal",
                "transaction_id",
                "docstatus",
                "status",
                "allocated_amount",
            ],
            limit_page_length=0,
        )
        if len(created) != expected_new_count:
            raise PlaidHistoricalBackfillError(
                f"Post-write verification found {len(created)} records, expected {expected_new_count}"
            )
        bad = [
            row for row in created
            if row.docstatus != 1 or row.status != "Unreconciled" or float(row.allocated_amount or 0) != 0.0
        ]
        if bad:
            raise PlaidHistoricalBackfillError(
                "Post-write verification found a historical Bank Transaction that is not submitted/unreconciled/unallocated: "
                + ", ".join(row.name for row in bad[:10])
            )

        child_rows = frappe.db.count(
            "Bank Transaction Payments",
            filters={"parent": ["in", created_names]},
        )
        if child_rows:
            raise PlaidHistoricalBackfillError(
                f"Post-write verification found {child_rows} unexpected reconciliation child rows"
            )

        _assert_production_plaid_unchanged(state, profile, context)
        for bank_account, expected_integration_id in mapping_ids.items():
            if frappe.db.get_value("Bank Account", bank_account, "integration_id") != expected_integration_id:
                raise PlaidHistoricalBackfillError(
                    f"Production Plaid account ID changed for {bank_account} during import"
                )

        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        raise

    per_account = Counter(row.bank_account for row in created)
    dates_by_account = {}
    for account in sorted(per_account):
        dates = sorted(str(row.date) for row in created if row.bank_account == account)
        dates_by_account[account] = {
            "created": per_account[account],
            "earliest": dates[0],
            "latest": dates[-1],
        }

    receipt = {
        "schema_version": 1,
        "session_id": session_id,
        "profile": state["profile"],
        "plan_hash": current_hash,
        "created_count": len(created_names),
        "created_names": sorted(created_names),
        "per_account": dates_by_account,
        "production_item_id_fingerprint": plan["production_item_id_fingerprint"],
        "candidate_item_id_fingerprint": plan["candidate_item_id_fingerprint"],
        "account_mappings": plan["account_mappings"],
        "db_safe_transaction_ids": plan["db_safe_transaction_ids"],
        "transaction_id_mappings": [
            {
                "bank_transaction": row.name,
                "stored_transaction_id": row.transaction_id,
                "source_transaction_id": next(
                    (candidate.get("source_transaction_id") for candidate in new_rows
                     if (candidate.get("storage_transaction_id") or candidate.get("transaction_id")) == row.transaction_id),
                    row.transaction_id,
                ),
            }
            for row in sorted(created, key=lambda item: item.name)
        ],
        "reconciliation_writes": 0,
        "accounting_voucher_writes": 0,
    }
    receipt_path = _receipt_path(session_id)
    receipt_warning = None
    try:
        _atomic_private_json_write(receipt_path, receipt)
        state["import_receipt_path"] = str(receipt_path)
        state["import_plan_hash"] = current_hash
        state["imported_count"] = len(created_names)
        _save_state(state)
    except Exception as exc:
        # The database commit has already succeeded. Never misrepresent a
        # receipt-file failure as a rolled-back financial import.
        receipt_warning = f"Bank Transactions committed, but private receipt write failed: {exc}"

    return {
        "session_id": session_id,
        "profile": state["profile"],
        "plan_hash": current_hash,
        "created_count": len(created_names),
        "per_account": dates_by_account,
        "all_created_submitted_unreconciled": True,
        "reconciliation_writes": 0,
        "accounting_voucher_writes": 0,
        "production_item_unchanged": True,
        "receipt_path": str(receipt_path) if not receipt_warning else None,
        "receipt_warning": receipt_warning,
        "next_step": "Run post-import coverage verification, then cleanup_session to remove only the temporary Plaid Item.",
    }


def session_status(session_id):
    """Return non-secret local staging state and current Hosted Link completion status."""
    state = _load_state(session_id)
    context = _plaid_context()
    link_result = _plaid_post(context, "/link/token/get", {"link_token": state["link_token"]})
    item_result, link_session = _extract_item_add_result(link_result)
    frappe.db.rollback()
    return {
        "session_id": session_id,
        "profile": state["profile"],
        "bank": state["bank"],
        "link_expiration": state.get("link_expiration"),
        "completed": bool(item_result),
        "linked_institution": (item_result or {}).get("institution"),
        "candidate_item_fingerprint": state.get("candidate_item_id_fingerprint"),
        "has_candidate_access_token": bool(state.get("candidate_access_token")),
        "last_report_path": state.get("last_report_path"),
        "link_session_started_at": (link_session or {}).get("started_at"),
        "link_session_finished_at": (link_session or {}).get("finished_at"),
    }


def cleanup_session(session_id, confirm=False):
    """Remove only the temporary candidate Plaid Item and then delete local staging files."""
    if str(confirm).lower() not in {"1", "true", "yes"}:
        raise PlaidHistoricalBackfillError("cleanup_session requires confirm=True")

    state = _load_state(session_id)
    profile = _profile(state["profile"])
    context = _plaid_context()
    live_access_token, live_item = _current_live_item(profile, context)

    if _fingerprint(live_access_token) != state.get("live_access_token_fingerprint"):
        raise PlaidHistoricalBackfillError(
            "Production Plaid token changed since session creation; refusing candidate cleanup until investigated"
        )
    if _fingerprint(live_item.get("item_id")) != state.get("live_item_id_fingerprint"):
        raise PlaidHistoricalBackfillError(
            "Production Plaid Item changed since session creation; refusing candidate cleanup until investigated"
        )

    candidate_removed = False
    candidate_fingerprint = state.get("candidate_item_id_fingerprint")
    try:
        state = _ensure_candidate_token(state, context, allow_institution_mismatch=True)
    except PlaidHistoricalBackfillError as exc:
        if "has not completed successfully yet" not in str(exc):
            raise

    candidate_token = state.get("candidate_access_token")
    if candidate_token:
        if candidate_token == live_access_token:
            raise PlaidHistoricalBackfillError("Refusing to remove the production Plaid Item")
        candidate_item = _plaid_post(context, "/item/get", {"access_token": candidate_token}).get("item") or {}
        if candidate_item.get("item_id") == live_item.get("item_id"):
            raise PlaidHistoricalBackfillError("Refusing to remove the production Plaid Item")
        candidate_fingerprint = _fingerprint(candidate_item.get("item_id"))
        _plaid_post(context, "/item/remove", {"access_token": candidate_token})
        candidate_removed = True

    session_path = _session_path(session_id)
    report_path = _report_path(session_id)
    receipt_path = _receipt_path(session_id)
    if report_path.exists():
        report_path.unlink()
    if session_path.exists():
        session_path.unlink()
    frappe.db.rollback()

    return {
        "session_id": session_id,
        "candidate_item_fingerprint": candidate_fingerprint,
        "candidate_item_removed": candidate_removed,
        "production_item_fingerprint": _fingerprint(live_item.get("item_id")),
        "production_item_unchanged": True,
        "local_session_files_removed": True,
        "import_receipt_preserved": receipt_path.exists(),
        "import_receipt_path": str(receipt_path) if receipt_path.exists() else None,
    }
