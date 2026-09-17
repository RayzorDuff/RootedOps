from collections import defaultdict
from decimal import Decimal, InvalidOperation
import re


_WHITESPACE_RE = re.compile(r"\s+")
_NON_WORD_RE = re.compile(r"[^\w]+", re.UNICODE)


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
