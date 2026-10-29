import frappe
from frappe import _
from frappe.utils import cint

from rootedops_payroll.services.signaturegate_deposits import (
    list_signaturegate_cash_deposit_bank_accounts,
    sync_signaturegate_cash_deposit_event,
)


def _require_integration_user() -> None:
    if frappe.session.user == "Guest":
        frappe.throw(_("Authentication is required."), frappe.PermissionError)

    if not frappe.has_permission("Journal Entry", ptype="create"):
        frappe.throw(
            _("The integration user is not permitted to create Journal Entries."),
            frappe.PermissionError,
        )


@frappe.whitelist(methods=["POST"])
def sync_signaturegate_cash_deposit(
    source_key: str,
    deposit_batch_id: str,
    status: str,
    deposit_date: str,
    actual_amount_cents: int,
    expected_amount_cents: int | None = None,
    deposit_slip_number: str | None = None,
    destination_bank_account: str | None = None,
    confirmed_at: str | None = None,
    dry_run: int | bool = 0,
):
    """Create/replay one idempotent SignatureGate deposit accounting event."""
    _require_integration_user()
    return sync_signaturegate_cash_deposit_event(
        source_key=source_key,
        deposit_batch_id=deposit_batch_id,
        status=status,
        deposit_date=deposit_date,
        deposit_slip_number=deposit_slip_number,
        destination_bank_account=destination_bank_account,
        expected_amount_cents=expected_amount_cents,
        actual_amount_cents=actual_amount_cents,
        confirmed_at=confirmed_at,
        dry_run=bool(cint(dry_run)),
    )



@frappe.whitelist(methods=["GET"])
def list_signaturegate_cash_deposit_bank_accounts_api():
    """List active Rooted Psyche Bank Accounts for SignatureGate selectors."""
    _require_integration_user()
    return list_signaturegate_cash_deposit_bank_accounts()
