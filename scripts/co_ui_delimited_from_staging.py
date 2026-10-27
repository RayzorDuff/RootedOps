#!/usr/bin/env python3
"""Convert RootedOps' private wage staging CSV to CDLE MyUI Delimited format.

Based on the user-provided Colorado CDLE FileFormatDELIM specification,
pp. 4 and 6-9: fourteen fields, no header, one row per employee.
Runs locally, without database access. Input/output contain SSNs; never commit.
"""
import argparse
import csv
import os
import re
import sys
import tempfile
from decimal import Decimal, InvalidOperation
from pathlib import Path


def prepare_rows(source, account, flags_ack):
    if not re.fullmatch(r"[0-9]{8}", account):
        raise ValueError("Employer account number must be exactly 8 digits")
    with open(source, newline="", encoding="utf-8") as fp:
        records = list(csv.DictReader(fp))
    if not records:
        raise ValueError("Staging CSV is empty")
    year_quarter = {(r["year"], r["quarter"]) for r in records}
    companies = {r["employer"] for r in records}
    if len(year_quarter) != 1 or len(companies) != 1:
        raise ValueError("Staging CSV contains more than one quarter/company")
    (year, quarter), = year_quarter
    if not (re.fullmatch(r"20[0-9]{2}", year) and quarter in ("1", "2", "3", "4")):
        raise ValueError("Invalid year or quarter")
    period = year + quarter.zfill(2)
    rows, total, seen = [], Decimal("0.00"), set()
    for r in records:
        ssn = re.sub(r"[^0-9]", "", r["ssn"])
        if len(ssn) != 9 or ssn in seen:
            raise ValueError("An SSN is invalid or repeated; no output created")
        seen.add(ssn)
        wage = Decimal(r["ui_gross_wages"])
        if not wage.is_finite() or wage < 0 or wage.as_tuple().exponent < -2:
            raise ValueError("Wages must be nonnegative with two decimal places")
        flags = [r[f"employment_month_{i}_review"] for i in (1, 2, 3)]
        if any(v not in ("0", "1") for v in flags):
            raise ValueError("Month employment indicators must be 0 or 1")
        if not flags_ack:
            # Deliberately omit names and SSNs from console diagnostics.
            print("Employee {}: candidate 12th-month flags {}".format(
                r["employee_id"], "/".join(flags)))
            continue
        names = [r["last_name"], r["first_name"]]
        if any(not n or len(n) > 30 or not re.fullmatch(r"[A-Za-z' -]+", n) for n in names):
            raise ValueError("First/last name violates CDLE constraints")
        mi = r.get("middle_initial", "")
        if mi and not re.fullmatch(r"[A-Za-z]", mi):
            raise ValueError("Invalid middle initial")
        rows.append([
            account, "00000", period, *flags, ssn,
            r["last_name"], r["first_name"], mi,
            f"{wage:.2f}", "", "N", "0",
        ])
        total += wage
    if not flags_ack:
        return None, len(records), sum((Decimal(r["ui_gross_wages"]) for r in records), Decimal("0.00"))
    if len(rows) != len(records) or any(len(row) != 14 for row in rows):
        raise ValueError("Unexpected output row structure")
    return rows, len(records), total, total


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Private staging CSV path")
    parser.add_argument("--output", type=Path, help="New private CDLE upload file path")
    parser.add_argument("--ean", required=True, help="8-digit Colorado UI employer number")
    parser.add_argument("--confirm-month-flags", action="store_true", help="I verified the 12th-of-month indicators against payroll records")
    args = parser.parse_args()
    if args.confirm_month_flags != bool(args.output):
        parser.error("Use --output together with --confirm-month-flags; omit both for preview")
    rows, count, wages, _ = prepare_rows(args.input, args.ean, args.confirm_month_flags)
    if not args.confirm_month_flags:
        print(f"Preview: {count} employee records; quarter gross wages {wages:.2f}. Verify each candidate flag before generating.")
        return
    if args.output.suffix.lower() not in (".csv", ".txt"):
        parser.error("Output must be .csv or .txt")
    if args.output.exists():
        parser.error("Output file exists: refusing overwrite")
    fd, temp = tempfile.mkstemp(prefix=".co-ui-", dir=str(args.output.parent))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file, lineterminator="\r\n")
            writer.writerows(rows)
        os.replace(temp, args.output)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    print(f"CDLE file created: {args.output}; employees: {count}; gross wages: {wages:.2f}; 14 columns; no header")
    print("Review portal import preview before certifying; never commit or share SSN-bearing file.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, InvalidOperation, OSError) as exc:
        print(f"Export failed: {exc}", file=sys.stderr)
        sys.exit(1)
