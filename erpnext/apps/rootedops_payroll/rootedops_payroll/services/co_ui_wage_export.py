"""Local, controlled Colorado UI wage-data staging export.

IMPORTANT: This is NOT a certified MyUI Employer+ upload layout. Export is a
secure intermediary to map to the state's current Delimited specification PDF.
Never commit generated files; they contain unmasked Social Security numbers.
"""
from __future__ import annotations

import csv
import os
import re
import tempfile
from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import frappe
from frappe.utils import getdate

CENT = Decimal("0.01")
QUARTERS = {1: (1, 3), 2: (4, 6), 3: (7, 9), 4: (10, 12)}


def _money(value):
    return Decimal(str(value or 0)).quantize(CENT, rounding=ROUND_HALF_UP)


def _get_ssn(employee):
    """Read Employee's actual SSN, supporting password-type custom fields."""
    meta = frappe.get_meta("Employee")
    for fieldname in ("ssn", "social_security_number", "custom_ssn"):
        df = meta.get_field(fieldname)
        if not df:
            continue
        if df.fieldtype == "Password":
            value = frappe.get_password("Employee", employee, fieldname, raise_exception=False)
        else:
            value = frappe.db.get_value("Employee", employee, fieldname)
        ssn = re.sub(r"\D", "", str(value or ""))
        if len(ssn) == 9 and ssn != "000000000":
            return ssn
    frappe.throw(f"Missing valid SSN for Employee {employee}. Correct the protected Employee record; no file exported.")


def export(company, year, quarter, output_path):
    """Stage per-employee quarterly wages with source data and employment flags.

    Run on trusted ERPNext server only. File mode 0600. Does not file a return.
    """
    year, quarter = int(year), int(quarter)
    if quarter not in QUARTERS or year < 2000 or year > 2100:
        frappe.throw("Enter year YYYY and quarter 1, 2, 3 or 4")
    if not frappe.db.exists("Company", company):
        frappe.throw("Unknown ERPNext Company")
    start_month, end_month = QUARTERS[quarter]
    first = date(year, start_month, 1)
    next_month = date(year + (end_month == 12), end_month % 12 + 1, 1)
    last = date.fromordinal(next_month.toordinal() - 1)
    slips = frappe.get_all(
        "Salary Slip",
        filters={"company": company, "docstatus": 1,
                 "posting_date": ["between", [first, last]]},
        fields=["name", "employee", "employee_name", "gross_pay",
                "posting_date", "start_date", "end_date"],
        order_by="employee asc, posting_date asc",
    )
    if not slips:
        frappe.throw("No submitted Salary Slips with posting dates in the quarter; no file created.")
    grouped = defaultdict(list)
    for slip in slips:
        grouped[slip.employee].append(slip)
    result = []
    total = Decimal("0.00")
    for employee in sorted(grouped):
        entries = grouped[employee]
        name = frappe.db.get_value("Employee", employee, "employee_name") or entries[0].employee_name
        parts = (name or "").strip().split()
        if len(parts) < 2:
            frappe.throw(f"Cannot split first/last name for Employee {employee}")
        first_name, last_name = parts[0], parts[-1]
        middle_initial = parts[1][0] if len(parts) > 2 else ""
        wages = sum((_money(s.gross_pay) for s in entries), Decimal("0.00"))
        if wages < 0:
            frappe.throw(f"Negative quarter gross for Employee {employee}")
        flags = []
        for m in range(start_month, end_month + 1):
            twelfth = date(year, m, 12)
            # This is an audit candidate based on period containing 12th.
            # Employer must review against actual payroll/employment records.
            flags.append(int(any(
                getdate(s.start_date) <= twelfth <= getdate(s.end_date)
                and _money(s.gross_pay) > 0 for s in entries
            )))
        result.append({
            "employer": company, "year": year, "quarter": quarter,
            "employee_id": employee, "ssn": _get_ssn(employee),
            "last_name": last_name, "first_name": first_name,
            "middle_initial": middle_initial,
            "ui_gross_wages": f"{wages:.2f}",
            "employment_month_1_review": flags[0],
            "employment_month_2_review": flags[1],
            "employment_month_3_review": flags[2],
            "source_salary_slips": ";".join(s.name for s in entries),
        })
        total += wages

    output = Path(output_path)
    if not output.is_absolute():
        frappe.throw("output_path must be an absolute path inside the trusted ERPNext server")
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        frappe.throw("Output already exists; use a new private path")
    fd, temporary = tempfile.mkstemp(prefix=".ui-wage-", suffix=".tmp", dir=str(output.parent))
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(result[0]))
            writer.writeheader()
            writer.writerows(result)
        os.chmod(temporary, 0o600)
        os.replace(temporary, output)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    # Only metadata, no names or SSNs, in console/log.
    return {"path": str(output), "employee_count": len(result),
            "gross_wages_total": f"{total:.2f}",
            "upload_ready": False,
            "notice": "Sensitive staging CSV: validate/map to current CDLE Delimited file specification before upload."}
