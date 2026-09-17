from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re


_WHITESPACE_RE = re.compile(r"\s+")
_NON_WORD_RE = re.compile(r"[^\w]+", re.UNICODE)


SAFE_IMPORT_MATCH_STATUSES = {
    "exact_transaction_id_match",
    "strong_fallback_match",
}
SAFE_IMPORT_STATUSES = SAFE_IMPORT_MATCH_STATUSES | {"new"}


BANK_TRANSACTION_ID_MAX_LENGTH = 140
_DB_SAFE_SUFFIX_PREFIX = "~cs-"
_DB_SAFE_DIGEST_LENGTH = 16


def _db_unique_key(value):
    """Approximate ERPNext/MariaDB's case-insensitive transaction_id uniqueness for Plaid IDs.

    Plaid transaction IDs are opaque ASCII strings in practice. ERPNext's Bank Transaction
    transaction_id column on this deployment uses utf8mb4_unicode_ci, so identifiers that
    differ only by letter case collide at the database UNIQUE index even though Plaid treats
    them as distinct opaque IDs.
    """
    return str(value or "").casefold()


def _collision_storage_transaction_id(source_transaction_id):
    """Return a deterministic DB-safe ID while retaining as much raw Plaid ID as possible."""
    source = str(source_transaction_id or "").strip()
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()[:_DB_SAFE_DIGEST_LENGTH]
    suffix = f"{_DB_SAFE_SUFFIX_PREFIX}{digest}"
    keep = BANK_TRANSACTION_ID_MAX_LENGTH - len(suffix)
    if keep <= 0:
        raise ValueError("Configured Bank Transaction transaction_id length cannot hold collision suffix")
    return f"{source[:keep]}{suffix}"


def assign_db_safe_transaction_ids(new_rows, existing_transaction_ids=()):
    """Assign deterministic transaction IDs compatible with a case-insensitive UNIQUE index.

    The provider's exact transaction ID remains in ``source_transaction_id``. Normally the
    ERPNext storage ID is identical. If two distinct provider IDs compare equal under the
    database's case-insensitive collation, every member of that collision group receives a
    deterministic ``~cs-<hash>`` suffix. Exact provider-ID reuse against an existing record
    remains a hard error rather than being renamed.
    """
    rows = [dict(row) for row in new_rows]
    existing = [str(value or "").strip() for value in existing_transaction_ids if str(value or "").strip()]
    existing_exact = set(existing)
    existing_keys = {_db_unique_key(value) for value in existing}

    groups = defaultdict(list)
    for index, row in enumerate(rows):
        source = str(row.get("transaction_id") or "").strip()
        if not source:
            raise ValueError("Candidate transaction has no provider transaction ID")
        if source in existing_exact:
            raise ValueError(f"Candidate provider transaction ID already exists in ERPNext: {source}")
        groups[_db_unique_key(source)].append(index)

    assigned_keys = set(existing_keys)
    collision_groups = []
    transformed = 0

    for key in sorted(groups):
        indexes = groups[key]
        needs_transform = len(indexes) > 1 or key in existing_keys
        group_sources = [str(rows[index].get("transaction_id") or "").strip() for index in indexes]

        if needs_transform:
            collision_groups.append(sorted(group_sources))

        for index, source in sorted(zip(indexes, group_sources), key=lambda pair: pair[1]):
            storage = _collision_storage_transaction_id(source) if needs_transform else source
            storage_key = _db_unique_key(storage)
            if storage_key in assigned_keys:
                raise ValueError(
                    "Unable to derive a unique ERPNext transaction ID for provider transaction "
                    f"{source}; derived ID collides under database collation"
                )
            assigned_keys.add(storage_key)
            row = rows[index]
            row["source_transaction_id"] = source
            row["storage_transaction_id"] = storage
            if storage != source:
                transformed += 1

    return {
        "rows": rows,
        "transformed_count": transformed,
        "collision_groups": collision_groups,
    }


def plaid_transaction_tags(transaction):
    """Return the tags added by ERPNext v16's native Plaid importer."""
    category = transaction.get("category") or []
    tags = list(category) if isinstance(category, (list, tuple)) else []
    category_id = transaction.get("category_id")
    if tags and category_id:
        tags.append(f"Plaid Cat. {category_id}")
    return tags


def validate_backfill_classifications(classifications, coverage_boundaries):
    """Validate that a classified overlap set is safe for a historical-only import.

    New transactions must be strictly before the first existing transaction for the
    canonical Bank Account. Existing matches must be on/after that boundary. Any
    weaker or conflicting classification blocks the import.
    """
    rows = [dict(row) for row in classifications]
    status_counts = Counter(row.get("status") for row in rows)
    unsupported = sorted(set(status_counts) - SAFE_IMPORT_STATUSES)
    if unsupported:
        raise ValueError(
            "Unsafe transaction classifications present: " + ", ".join(unsupported)
        )

    new_ids = set()
    new_rows = []
    per_account = defaultdict(lambda: Counter())

    for row in rows:
        account = row.get("bank_account")
        if account not in coverage_boundaries:
            raise ValueError(f"No existing-coverage boundary for {account!r}")
        boundary = coverage_boundaries[account]
        boundary = boundary if isinstance(boundary, date) else date.fromisoformat(str(boundary))
        try:
            transaction_date = date.fromisoformat(str(row.get("date") or ""))
        except ValueError as exc:
            raise ValueError(f"Invalid transaction date for {account!r}: {row.get('date')!r}") from exc

        status = row.get("status")
        per_account[account][status] += 1
        if status == "new":
            if transaction_date >= boundary:
                raise ValueError(
                    f"New transaction for {account!r} on {transaction_date} is not before "
                    f"existing coverage {boundary}"
                )
            transaction_id = str(row.get("transaction_id") or "").strip()
            if not transaction_id:
                raise ValueError(f"New transaction for {account!r} has no provider transaction ID")
            if transaction_id in new_ids:
                raise ValueError(f"Duplicate candidate transaction ID in import set: {transaction_id}")
            new_ids.add(transaction_id)
            if money(row.get("deposit")) == 0 and money(row.get("withdrawal")) == 0:
                raise ValueError(f"New transaction {transaction_id} has zero deposit and withdrawal")
            new_rows.append(row)
        elif transaction_date < boundary:
            raise ValueError(
                f"Existing match for {account!r} on {transaction_date} is before "
                f"existing coverage {boundary}"
            )

    return {
        "status_counts": dict(sorted(status_counts.items())),
        "new_rows": new_rows,
        "new_count": len(new_rows),
        "new_transaction_ids": sorted(new_ids),
        "per_account_status_counts": {
            account: dict(sorted(counts.items()))
            for account, counts in sorted(per_account.items())
        },
    }


def deterministic_plan_hash(payload):
    """Hash a JSON-compatible import plan using stable key/list ordering."""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def normalize_text(value):
    """Normalize provider text for deterministic comparison without fuzzy matching."""
    if value is None:
        return ""
    text = str(value).strip().casefold()
    text = _NON_WORD_RE.sub(" ", text)
    return _WHITESPACE_RE.sub(" ", text).strip()


def money(value):
    if value in (None, ""):
        return Decimal("0.00")
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"Invalid monetary value: {value!r}") from exc


def plaid_bank_transaction_fields(transaction):
    """Return the native ERPNext field values used by the v16 Plaid importer."""
    amount = money(transaction.get("amount"))
    payment_meta = transaction.get("payment_meta") or {}

    if amount >= 0:
        deposit = Decimal("0.00")
        withdrawal = amount
    else:
        deposit = abs(amount)
        withdrawal = Decimal("0.00")

    transaction_type = (
        transaction.get("transaction_code")
        or payment_meta.get("payment_method")
        or ""
    )
    reference_number = (
        transaction.get("check_number")
        or payment_meta.get("reference_number")
        or transaction.get("name")
        or ""
    )

    return {
        "date": str(transaction.get("date") or ""),
        "deposit": deposit,
        "withdrawal": withdrawal,
        "currency": transaction.get("iso_currency_code") or "",
        "transaction_id": transaction.get("transaction_id") or "",
        "transaction_type": transaction_type,
        "reference_number": reference_number,
        "description": transaction.get("name") or "",
    }


def _account_name_key(account):
    return normalize_text(account.get("official_name") or account.get("name"))


def _account_type_key(account):
    return (
        str(account.get("mask") or ""),
        normalize_text(account.get("type")),
        normalize_text(account.get("subtype")),
    )


def match_candidate_accounts(canonical_accounts, candidate_accounts):
    """
    Match replacement-Item Plaid accounts to canonical ERPNext Bank Accounts.

    The function is deliberately conservative. A candidate account is never assigned
    to more than one canonical account, and ambiguous matches remain unresolved.
    """
    candidates = [dict(account) for account in candidate_accounts]
    used = set()
    results = []

    for canonical in canonical_accounts:
        canonical = dict(canonical)
        available = [c for c in candidates if c.get("account_id") not in used]
        type_key = _account_type_key(canonical)
        name_key = _account_name_key(canonical)

        levels = [
            (
                "mask_type_subtype_name",
                [
                    c
                    for c in available
                    if _account_type_key(c) == type_key
                    and _account_name_key(c) == name_key
                    and bool(name_key)
                ],
            ),
            (
                "mask_type_subtype",
                [c for c in available if _account_type_key(c) == type_key and bool(type_key[0])],
            ),
            (
                "name_type_subtype",
                [
                    c
                    for c in available
                    if _account_name_key(c) == name_key
                    and normalize_text(c.get("type")) == normalize_text(canonical.get("type"))
                    and normalize_text(c.get("subtype")) == normalize_text(canonical.get("subtype"))
                    and bool(name_key)
                ],
            ),
        ]

        selected = None
        method = None
        ambiguous = []
        for level_name, matches in levels:
            if len(matches) == 1:
                selected = matches[0]
                method = level_name
                break
            if len(matches) > 1:
                ambiguous = matches
                method = f"ambiguous_{level_name}"
                break

        if selected:
            used.add(selected.get("account_id"))
            results.append(
                {
                    "bank_account": canonical.get("bank_account"),
                    "current_account_id": canonical.get("account_id"),
                    "candidate_account_id": selected.get("account_id"),
                    "status": "mapped",
                    "method": method,
                    "candidate_mask": selected.get("mask"),
                    "candidate_name": selected.get("name"),
                    "candidate_official_name": selected.get("official_name"),
                    "candidate_type": selected.get("type"),
                    "candidate_subtype": selected.get("subtype"),
                }
            )
        else:
            results.append(
                {
                    "bank_account": canonical.get("bank_account"),
                    "current_account_id": canonical.get("account_id"),
                    "candidate_account_id": None,
                    "status": "ambiguous" if ambiguous else "unresolved",
                    "method": method or "no_unique_metadata_match",
                    "candidate_ids": [c.get("account_id") for c in ambiguous],
                }
            )

    return results


def _transaction_keys(record):
    base = (
        record.get("bank_account") or "",
        str(record.get("date") or ""),
        money(record.get("deposit")),
        money(record.get("withdrawal")),
    )
    description = normalize_text(record.get("description"))
    reference = normalize_text(record.get("reference_number"))
    transaction_type = normalize_text(record.get("transaction_type"))

    return {
        "strong": base + (description, reference, transaction_type),
        "secondary": base + (description, reference),
        "amount_date": base,
        "has_identity_text": bool(description or reference),
    }


def classify_transaction_overlap(candidate_records, existing_records):
    """
    Classify candidate historical transactions without relying on amount/date alone.

    Results are conservative:
    * exact Plaid IDs are authoritative only when they point to the same canonical account;
    * deterministic text/reference/type groups are duplicates only when multiplicity agrees;
    * amount/date-only matches are always ambiguous, never silently discarded;
    * otherwise the candidate is new.
    """
    existing = [dict(record) for record in existing_records]
    candidates = [dict(record) for record in candidate_records]

    existing_by_id = {
        record.get("transaction_id"): record
        for record in existing
        if record.get("transaction_id")
    }
    remaining_existing = {id(record): record for record in existing}
    classifications = {}

    for idx, candidate in enumerate(candidates):
        txid = candidate.get("transaction_id")
        if not txid or txid not in existing_by_id:
            continue
        match = existing_by_id[txid]
        if match.get("bank_account") == candidate.get("bank_account"):
            status = "exact_transaction_id_match"
        else:
            status = "transaction_id_account_conflict"
        classifications[idx] = {
            "status": status,
            "existing_names": [match.get("name")],
            "match_method": "transaction_id",
        }
        remaining_existing.pop(id(match), None)

    remaining_candidate_indexes = [i for i in range(len(candidates)) if i not in classifications]

    for key_name, status_name in (
        ("strong", "strong_fallback_match"),
        ("secondary", "secondary_fallback_match"),
    ):
        candidate_groups = defaultdict(list)
        existing_groups = defaultdict(list)

        for idx in remaining_candidate_indexes:
            keys = _transaction_keys(candidates[idx])
            if keys["has_identity_text"]:
                candidate_groups[keys[key_name]].append(idx)

        for record in remaining_existing.values():
            keys = _transaction_keys(record)
            if keys["has_identity_text"]:
                existing_groups[keys[key_name]].append(record)

        matched_candidate_indexes = set()
        matched_existing_ids = set()

        for key, indexes in candidate_groups.items():
            matches = existing_groups.get(key, [])
            if not matches:
                continue
            if len(indexes) == len(matches):
                names = [record.get("name") for record in matches]
                for idx in indexes:
                    classifications[idx] = {
                        "status": status_name,
                        "existing_names": names,
                        "match_method": key_name,
                        "group_multiplicity": len(indexes),
                    }
                    matched_candidate_indexes.add(idx)
                matched_existing_ids.update(id(record) for record in matches)

        if matched_candidate_indexes:
            remaining_candidate_indexes = [
                idx for idx in remaining_candidate_indexes if idx not in matched_candidate_indexes
            ]
            for record_id in matched_existing_ids:
                remaining_existing.pop(record_id, None)

    amount_date_existing = defaultdict(list)
    for record in remaining_existing.values():
        amount_date_existing[_transaction_keys(record)["amount_date"]].append(record)

    for idx in remaining_candidate_indexes:
        candidate = candidates[idx]
        key = _transaction_keys(candidate)["amount_date"]
        matches = amount_date_existing.get(key, [])
        if matches:
            classifications[idx] = {
                "status": "ambiguous_amount_date_match",
                "existing_names": [record.get("name") for record in matches],
                "match_method": "amount_date_only",
                "existing_match_count": len(matches),
            }
        else:
            classifications[idx] = {
                "status": "new",
                "existing_names": [],
                "match_method": None,
            }

    return [
        {
            **candidate,
            **classifications[idx],
        }
        for idx, candidate in enumerate(candidates)
    ]
