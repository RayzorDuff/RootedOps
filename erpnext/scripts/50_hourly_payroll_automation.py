"""RootedOps ERPNext hourly payroll automation.

Phase 3 currently implemented:
- Attendance-based hourly payroll
- Gross pay from submitted Attendance working hours
- Employee Social Security
- Employee Medicare
- Employer Social Security (reported in return payload)
- Employer Medicare (reported in return payload)
- Federal withholding for 2026 weekly payroll using IRS Pub. 15-T
  Percentage Method tables for 2020-or-later Form W-4 inputs
- Colorado withholding for 2026 using DR 1098
- Persistent employee federal / Colorado tax profile storage on Employee custom fields
- Payroll liability summary generation
- Journal Entry preview payload generation
- Optional draft Journal Entry creation

Still not implemented here:
- Additional Medicare tax > $200,000 annual wages
- 2019-or-earlier federal W-4 handling
- Employer tax posting automation beyond draft JE creation
- Multi-slip payroll entry batching

Run inside bench console with:
    exec(open("/home/frappe/frappe-bench/sites/50_hourly_payroll_automation.py").read(), globals())
"""

from contextlib import contextmanager

import frappe
from frappe.utils import cint, date_diff, flt, getdate
from hrms.payroll.doctype.salary_slip.salary_slip import SalarySlip
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


SS_WAGE_BASE_2026 = 184500.0
SS_RATE = 0.062
MEDICARE_RATE = 0.0145
COLORADO_RATE_2026 = 0.044

PAY_PERIODS_PER_YEAR = {
    "Weekly": 52,
    "Bi-Weekly": 26,
    "Biweekly": 26,
    "Semimonthly": 24,
    "Semi-Monthly": 24,
    "Monthly": 12,
    "Quarterly": 4,
    "Semi-Annually": 2,
    "Semiannually": 2,
    "Annually": 1,
    "Daily": 260,
}

FEDERAL_WEEKLY_TABLES_2026 = {
    "standard": {
        "married_filing_jointly": [
            (0.00, 619.00, 0.00, 0.00, 0.00),
            (619.00, 1096.00, 0.00, 0.10, 619.00),
            (1096.00, 2558.00, 47.70, 0.12, 1096.00),
            (2558.00, 4685.00, 223.14, 0.22, 2558.00),
            (4685.00, 8380.00, 691.08, 0.24, 4685.00),
            (8380.00, 10474.00, 1577.88, 0.32, 8380.00),
            (10474.00, 15402.00, 2247.96, 0.35, 10474.00),
            (15402.00, None, 3972.76, 0.37, 15402.00),
        ],
        "single_or_married_filing_separately": [
            (0.00, 310.00, 0.00, 0.00, 0.00),
            (310.00, 548.00, 0.00, 0.10, 310.00),
            (548.00, 1279.00, 23.80, 0.12, 548.00),
            (1279.00, 2342.00, 111.52, 0.22, 1279.00),
            (2342.00, 4190.00, 345.38, 0.24, 2342.00),
            (4190.00, 5237.00, 788.90, 0.32, 4190.00),
            (5237.00, 12629.00, 1123.94, 0.35, 5237.00),
            (12629.00, None, 3711.14, 0.37, 12629.00),
        ],
        "head_of_household": [
            (0.00, 464.00, 0.00, 0.00, 0.00),
            (464.00, 805.00, 0.00, 0.10, 464.00),
            (805.00, 1762.00, 34.10, 0.12, 805.00),
            (1762.00, 2497.00, 148.94, 0.22, 1762.00),
            (2497.00, 4344.00, 310.64, 0.24, 2497.00),
            (4344.00, 5391.00, 753.92, 0.32, 4344.00),
            (5391.00, 12784.00, 1088.96, 0.35, 5391.00),
            (12784.00, None, 3676.51, 0.37, 12784.00),
        ],
    },
    "step2": {
        "married_filing_jointly": [
            (0.00, 310.00, 0.00, 0.00, 0.00),
            (310.00, 548.00, 0.00, 0.10, 310.00),
            (548.00, 1279.00, 23.80, 0.12, 548.00),
            (1279.00, 2342.00, 111.52, 0.22, 1279.00),
            (2342.00, 4190.00, 345.38, 0.24, 2342.00),
            (4190.00, 5237.00, 788.90, 0.32, 4190.00),
            (5237.00, 7701.00, 1123.94, 0.35, 5237.00),
            (7701.00, None, 1986.34, 0.37, 7701.00),
        ],
        "single_or_married_filing_separately": [
            (0.00, 155.00, 0.00, 0.00, 0.00),
            (155.00, 274.00, 0.00, 0.10, 155.00),
            (274.00, 639.00, 11.90, 0.12, 274.00),
            (639.00, 1171.00, 55.70, 0.22, 639.00),
            (1171.00, 2095.00, 172.74, 0.24, 1171.00),
            (2095.00, 2619.00, 394.50, 0.32, 2095.00),
            (2619.00, 6314.00, 562.18, 0.35, 2619.00),
            (6314.00, None, 1855.43, 0.37, 6314.00),
        ],
        "head_of_household": [
            (0.00, 232.00, 0.00, 0.00, 0.00),
            (232.00, 402.00, 0.00, 0.10, 232.00),
            (402.00, 881.00, 17.00, 0.12, 402.00),
            (881.00, 1249.00, 74.48, 0.22, 881.00),
            (1249.00, 2172.00, 155.44, 0.24, 1249.00),
            (2172.00, 2696.00, 376.96, 0.32, 2172.00),
            (2696.00, 6392.00, 544.64, 0.35, 2696.00),
            (6392.00, None, 1838.24, 0.37, 6392.00),
        ],
    },
}


EMPLOYEE_TAX_CUSTOM_FIELDS = {
    "Employee": [
        {
            "fieldname": "rootedops_payroll_section",
            "label": "RootedOps Payroll",
            "fieldtype": "Section Break",
            "insert_after": "salary_currency",
            "collapsible": 1,
        },
        {
            "fieldname": "rootedops_federal_filing_status",
            "label": "Federal Filing Status",
            "fieldtype": "Select",
            "options": "\nSingle\nMarried Filing Jointly\nMarried Filing Separately\nHead of Household",
            "insert_after": "rootedops_payroll_section",
        },
        {
            "fieldname": "rootedops_federal_step2_checked",
            "label": "Federal W-4 Step 2 Checked",
            "fieldtype": "Check",
            "insert_after": "rootedops_federal_filing_status",
            "default": "0",
        },
        {
            "fieldname": "rootedops_federal_step3_annual_credits",
            "label": "Federal W-4 Step 3 Annual Credits",
            "fieldtype": "Currency",
            "insert_after": "rootedops_federal_step2_checked",
            "default": "0",
        },
        {
            "fieldname": "rootedops_federal_step4a_other_income",
            "label": "Federal W-4 Step 4(a) Other Income",
            "fieldtype": "Currency",
            "insert_after": "rootedops_federal_step3_annual_credits",
            "default": "0",
        },
        {
            "fieldname": "rootedops_federal_step4b_deductions",
            "label": "Federal W-4 Step 4(b) Deductions",
            "fieldtype": "Currency",
            "insert_after": "rootedops_federal_step4a_other_income",
            "default": "0",
        },
        {
            "fieldname": "rootedops_federal_step4c_extra_withholding",
            "label": "Federal W-4 Step 4(c) Extra Withholding Per Pay Period",
            "fieldtype": "Currency",
            "insert_after": "rootedops_federal_step4b_deductions",
            "default": "0",
        },
        {
            "fieldname": "rootedops_federal_exempt",
            "label": "Federal Withholding Exempt",
            "fieldtype": "Check",
            "insert_after": "rootedops_federal_step4c_extra_withholding",
            "default": "0",
        },
        {
            "fieldname": "rootedops_colorado_column_break",
            "label": "",
            "fieldtype": "Column Break",
            "insert_after": "rootedops_federal_exempt",
        },
        {
            "fieldname": "rootedops_colorado_filing_status",
            "label": "Colorado Filing Status",
            "fieldtype": "Select",
            "options": "\nSingle\nMarried Filing Jointly\nMarried Filing Separately\nHead of Household",
            "insert_after": "rootedops_colorado_column_break",
        },
        {
            "fieldname": "rootedops_colorado_dr0004_line2_override",
            "label": "Colorado DR 0004 Line 2 Override",
            "fieldtype": "Check",
            "insert_after": "rootedops_colorado_filing_status",
            "default": "0",
        },
        {
            "fieldname": "rootedops_colorado_dr0004_line2",
            "label": "Colorado DR 0004 Line 2",
            "fieldtype": "Currency",
            "insert_after": "rootedops_colorado_dr0004_line2_override",
            "default": "0",
        },
        {
            "fieldname": "rootedops_colorado_dr0004_line3",
            "label": "Colorado DR 0004 Line 3 Additional Withholding",
            "fieldtype": "Currency",
            "insert_after": "rootedops_colorado_dr0004_line2",
            "default": "0",
        },
        {
            "fieldname": "rootedops_colorado_exempt",
            "label": "Colorado Withholding Exempt",
            "fieldtype": "Check",
            "insert_after": "rootedops_colorado_dr0004_line3",
            "default": "0",
        },
        {
            "fieldname": "rootedops_hourly_rate",
            "label": "RootedOps Hourly Rate",
            "fieldtype": "Currency",
            "insert_after": "rootedops_colorado_exempt",
        },
    ]
}


def ensure_employee_tax_profile_custom_fields():
    create_custom_fields(EMPLOYEE_TAX_CUSTOM_FIELDS, update=True)
    frappe.db.commit()
    return True


def employee_tax_custom_fieldnames():
    return [
        "rootedops_federal_filing_status",
        "rootedops_federal_step2_checked",
        "rootedops_federal_step3_annual_credits",
        "rootedops_federal_step4a_other_income",
        "rootedops_federal_step4b_deductions",
        "rootedops_federal_step4c_extra_withholding",
        "rootedops_federal_exempt",
        "rootedops_colorado_filing_status",
        "rootedops_colorado_dr0004_line2_override",
        "rootedops_colorado_dr0004_line2",
        "rootedops_colorado_dr0004_line3",
        "rootedops_colorado_exempt",
        "rootedops_hourly_rate",
    ]


def get_employee_tax_profile(employee):
    ensure_employee_tax_profile_custom_fields()

    values = frappe.db.get_value(
        "Employee",
        employee,
        employee_tax_custom_fieldnames(),
        as_dict=True,
    ) or {}

    colorado_line2_override = cint(values.get("rootedops_colorado_dr0004_line2_override") or 0)
    colorado_line2_value = flt(values.get("rootedops_colorado_dr0004_line2") or 0.0, 2)

    federal_profile = {
        "filing_status": values.get("rootedops_federal_filing_status") or None,
        "step2_checked": cint(values.get("rootedops_federal_step2_checked") or 0),
        "step3_annual_credits": flt(values.get("rootedops_federal_step3_annual_credits") or 0.0, 2),
        "step4a_other_income": flt(values.get("rootedops_federal_step4a_other_income") or 0.0, 2),
        "step4b_deductions": flt(values.get("rootedops_federal_step4b_deductions") or 0.0, 2),
        "step4c_extra_withholding": flt(values.get("rootedops_federal_step4c_extra_withholding") or 0.0, 2),
        "exempt": cint(values.get("rootedops_federal_exempt") or 0),
    }

    colorado_profile = {
        "filing_status": values.get("rootedops_colorado_filing_status") or None,
        "dr0004_line2": colorado_line2_value if colorado_line2_override else None,
        "dr0004_line2_override": colorado_line2_override,
        "dr0004_line3": flt(values.get("rootedops_colorado_dr0004_line3") or 0.0, 2),
        "exempt": cint(values.get("rootedops_colorado_exempt") or 0),
    }

    hourly_rate = values.get("rootedops_hourly_rate")
    hourly_rate = None if hourly_rate in (None, "") else flt(hourly_rate, 2)

    return {
        "employee": employee,
        "hourly_rate": hourly_rate,
        "federal_profile": federal_profile,
        "colorado_profile": colorado_profile,
        "raw": values,
    }


def update_employee_tax_profile(
    employee,
    hourly_rate=None,
    federal_profile=None,
    colorado_profile=None,
):
    ensure_employee_tax_profile_custom_fields()

    updates = {}

    if hourly_rate is not None:
        updates["rootedops_hourly_rate"] = flt(hourly_rate, 2)

    federal_profile = federal_profile or {}
    colorado_profile = colorado_profile or {}

    if "filing_status" in federal_profile:
        updates["rootedops_federal_filing_status"] = federal_profile.get("filing_status")
    if "step2_checked" in federal_profile:
        updates["rootedops_federal_step2_checked"] = cint(federal_profile.get("step2_checked") or 0)
    if "step3_annual_credits" in federal_profile:
        updates["rootedops_federal_step3_annual_credits"] = flt(federal_profile.get("step3_annual_credits") or 0.0, 2)
    if "step4a_other_income" in federal_profile:
        updates["rootedops_federal_step4a_other_income"] = flt(federal_profile.get("step4a_other_income") or 0.0, 2)
    if "step4b_deductions" in federal_profile:
        updates["rootedops_federal_step4b_deductions"] = flt(federal_profile.get("step4b_deductions") or 0.0, 2)
    if "step4c_extra_withholding" in federal_profile:
        updates["rootedops_federal_step4c_extra_withholding"] = flt(federal_profile.get("step4c_extra_withholding") or 0.0, 2)
    if "exempt" in federal_profile:
        updates["rootedops_federal_exempt"] = cint(federal_profile.get("exempt") or 0)

    if "filing_status" in colorado_profile:
        updates["rootedops_colorado_filing_status"] = colorado_profile.get("filing_status")

    if "dr0004_line2" in colorado_profile:
        value = colorado_profile.get("dr0004_line2")
        if value in (None, ""):
            updates["rootedops_colorado_dr0004_line2_override"] = 0
            updates["rootedops_colorado_dr0004_line2"] = 0.0
        else:
            updates["rootedops_colorado_dr0004_line2_override"] = 1
            updates["rootedops_colorado_dr0004_line2"] = flt(value, 2)

    if "dr0004_line2_override" in colorado_profile:
        updates["rootedops_colorado_dr0004_line2_override"] = cint(colorado_profile.get("dr0004_line2_override") or 0)

    if "dr0004_line3" in colorado_profile:
        updates["rootedops_colorado_dr0004_line3"] = flt(colorado_profile.get("dr0004_line3") or 0.0, 2)

    if "exempt" in colorado_profile:
        updates["rootedops_colorado_exempt"] = cint(colorado_profile.get("exempt") or 0)

    if not updates:
        return get_employee_tax_profile(employee)

    for fieldname, value in updates.items():
        frappe.db.set_value("Employee", employee, fieldname, value, update_modified=False)

    frappe.db.commit()
    return get_employee_tax_profile(employee)


def seed_test_employee_tax_profile():
    return update_employee_tax_profile(
        employee="HR-EMP-00001",
        hourly_rate=20.0,
        federal_profile={
            "filing_status": "Single",
            "step2_checked": 0,
            "step3_annual_credits": 0.0,
            "step4a_other_income": 0.0,
            "step4b_deductions": 0.0,
            "step4c_extra_withholding": 0.0,
            "exempt": 0,
        },
        colorado_profile={
            "filing_status": "Single",
            "dr0004_line2": None,
            "dr0004_line3": 0.0,
            "exempt": 0,
        },
    )


def get_present_attendance_rows(employee, start_date, end_date):
    return frappe.get_all(
        "Attendance",
        filters={
            "employee": employee,
            "attendance_date": ["between", [start_date, end_date]],
            "docstatus": 1,
            "status": "Present",
        },
        fields=["name", "attendance_date", "working_hours"],
        order_by="attendance_date asc",
    )


def attendance_summary(employee, start_date, end_date):
    rows = get_present_attendance_rows(employee, start_date, end_date)
    total_hours = sum(flt(row.working_hours) for row in rows)
    payment_days = len({str(row.attendance_date) for row in rows})
    total_working_days = date_diff(getdate(end_date), getdate(start_date)) + 1
    absent_days = max(0, total_working_days - payment_days)

    return {
        "rows": rows,
        "hours": flt(total_hours, 2),
        "payment_days": flt(payment_days, 2),
        "total_working_days": flt(total_working_days, 2),
        "absent_days": flt(absent_days, 2),
    }


def get_pay_periods_per_year(payroll_frequency):
    if payroll_frequency not in PAY_PERIODS_PER_YEAR:
        frappe.throw(f"Unsupported payroll_frequency: {payroll_frequency}")
    return PAY_PERIODS_PER_YEAR[payroll_frequency]


def normalized_federal_filing_status(value):
    raw = (value or "").strip().lower().replace("-", " ").replace("_", " ")

    mapping = {
        "single": "single_or_married_filing_separately",
        "married filing separately": "single_or_married_filing_separately",
        "single or married filing separately": "single_or_married_filing_separately",
        "married filing jointly": "married_filing_jointly",
        "mfj": "married_filing_jointly",
        "qualifying surviving spouse": "married_filing_jointly",
        "qss": "married_filing_jointly",
        "head of household": "head_of_household",
        "hoh": "head_of_household",
    }

    if raw not in mapping:
        frappe.throw(
            "Unsupported federal filing_status. Use one of: "
            "'single', 'married filing jointly', 'married filing separately', "
            "'single or married filing separately', or 'head of household'."
        )

    return mapping[raw]


def normalized_colorado_filing_status(value):
    raw = (value or "").strip().lower().replace("-", " ").replace("_", " ")

    if raw in ("married filing jointly", "mfj", "qualifying surviving spouse", "qss"):
        return "married_filing_jointly"

    if raw in (
        "single",
        "married filing separately",
        "single or married filing separately",
        "head of household",
        "hoh",
    ):
        return "other"

    frappe.throw(
        "Unsupported Colorado filing_status. Use one of: "
        "'single', 'married filing jointly', 'married filing separately', "
        "'single or married filing separately', or 'head of household'."
    )


def ytd_gross_before_period(employee, start_date, exclude_slip_name=None):
    rows = frappe.get_all(
        "Salary Slip",
        filters={
            "employee": employee,
            "docstatus": ["<", 2],
            "end_date": ["<", start_date],
        },
        fields=["name", "gross_pay"],
    )

    total = 0.0
    for row in rows:
        if exclude_slip_name and row.name == exclude_slip_name:
            continue
        total += flt(row.gross_pay)

    return flt(total, 2)


def ss_employee_amount(current_gross, ytd_before):
    taxable_remaining = max(0.0, SS_WAGE_BASE_2026 - flt(ytd_before))
    taxable_now = min(flt(current_gross), taxable_remaining)
    return flt(taxable_now * SS_RATE, 2)


def medicare_employee_amount(current_gross):
    return flt(flt(current_gross) * MEDICARE_RATE, 2)


def ss_employer_amount(current_gross, ytd_before):
    taxable_remaining = max(0.0, SS_WAGE_BASE_2026 - flt(ytd_before))
    taxable_now = min(flt(current_gross), taxable_remaining)
    return flt(taxable_now * SS_RATE, 2)


def medicare_employer_amount(current_gross):
    return flt(flt(current_gross) * MEDICARE_RATE, 2)


def lookup_federal_weekly_row_2026(adjusted_wage_amount, filing_status, step2_checked):
    schedule_key = "step2" if cint(step2_checked) else "standard"
    rows = FEDERAL_WEEKLY_TABLES_2026[schedule_key][filing_status]
    wage = flt(adjusted_wage_amount, 2)

    for lower, upper, base_tax, rate, excess_over in rows:
        if upper is None:
            if wage >= lower:
                return {
                    "lower": lower,
                    "upper": upper,
                    "base_tax": base_tax,
                    "rate": rate,
                    "excess_over": excess_over,
                }
        else:
            if wage >= lower and wage < upper:
                return {
                    "lower": lower,
                    "upper": upper,
                    "base_tax": base_tax,
                    "rate": rate,
                    "excess_over": excess_over,
                }

    frappe.throw(
        f"Unable to find weekly federal withholding row for adjusted wage {wage}, "
        f"filing_status {filing_status}, step2_checked {step2_checked}"
    )


def calculate_federal_withholding_2026_weekly(gross, federal_profile=None):
    profile = federal_profile or {}

    if cint(profile.get("exempt", 0)):
        return {
            "withholding": 0.0,
            "detail": {
                "method": "irs_2026_weekly_percentage_method",
                "exempt": 1,
            },
        }

    filing_status = normalized_federal_filing_status(profile.get("filing_status", "single"))
    step2_checked = cint(profile.get("step2_checked", 0))
    step3_annual_credits = flt(profile.get("step3_annual_credits", 0.0), 2)
    step4a_other_income = flt(profile.get("step4a_other_income", 0.0), 2)
    step4b_deductions = flt(profile.get("step4b_deductions", 0.0), 2)
    step4c_extra_withholding = flt(profile.get("step4c_extra_withholding", 0.0), 2)

    pay_periods = 52

    line_1a = flt(gross, 2)
    line_1d = flt(step4a_other_income / pay_periods, 2)
    line_1e = flt(line_1a + line_1d, 2)
    line_1g = flt(step4b_deductions / pay_periods, 2)
    line_1h = max(0.0, flt(line_1e - line_1g, 2))

    row = lookup_federal_weekly_row_2026(
        adjusted_wage_amount=line_1h,
        filing_status=filing_status,
        step2_checked=step2_checked,
    )

    line_2d = flt(line_1h - row["excess_over"], 2)
    line_2e = flt(line_2d * row["rate"], 2)
    line_2f = flt(row["base_tax"] + line_2e, 2)

    line_3b = flt(step3_annual_credits / pay_periods, 2)
    line_3c = max(0.0, flt(line_2f - line_3b, 2))

    line_4a = step4c_extra_withholding
    line_4b = flt(line_3c + line_4a, 2)

    return {
        "withholding": flt(max(0.0, line_4b), 2),
        "detail": {
            "method": "irs_2026_weekly_percentage_method",
            "filing_status": filing_status,
            "step2_checked": step2_checked,
            "step3_annual_credits": step3_annual_credits,
            "step4a_other_income": step4a_other_income,
            "step4b_deductions": step4b_deductions,
            "step4c_extra_withholding": step4c_extra_withholding,
            "line_1a_gross": line_1a,
            "line_1d_other_income_per_period": line_1d,
            "line_1e": line_1e,
            "line_1g_deductions_per_period": line_1g,
            "line_1h_adjusted_wage_amount": line_1h,
            "line_2_row": row,
            "line_2d_excess_wage": line_2d,
            "line_2e_percentage_tax": line_2e,
            "line_2f_tentative_withholding": line_2f,
            "line_3b_credits_per_period": line_3b,
            "line_3c_after_credits": line_3c,
            "line_4b_final_withholding": flt(max(0.0, line_4b), 2),
        },
    }


def calculate_colorado_withholding_2026(gross, payroll_frequency, colorado_profile=None):
    profile = colorado_profile or {}

    if cint(profile.get("exempt", 0)):
        return {
            "withholding": 0.0,
            "detail": {
                "method": "colorado_dr1098_2026",
                "exempt": 1,
            },
        }

    pay_periods = get_pay_periods_per_year(payroll_frequency)
    filing_status = normalized_colorado_filing_status(profile.get("filing_status", "single"))

    line_1a = flt(gross, 2)
    line_1b = pay_periods
    line_1c = flt(line_1a * line_1b, 2)

    dr0004_line2_override = cint(profile.get("dr0004_line2_override", 0))
    dr0004_line2 = profile.get("dr0004_line2", None)

    if dr0004_line2_override and dr0004_line2 not in (None, ""):
        line_2a = flt(dr0004_line2, 2)
    else:
        line_2a = 11000.0 if filing_status == "married_filing_jointly" else 5500.0

    line_2b = max(0.0, flt(line_1c - line_2a, 2))
    line_2c = flt(line_2b * COLORADO_RATE_2026, 2)
    line_2d = flt(line_2c / line_1b, 2)
    line_2e = flt(profile.get("dr0004_line3", 0.0), 2)
    line_2f = flt(line_2d + line_2e, 2)

    return {
        "withholding": flt(max(0.0, line_2f), 2),
        "detail": {
            "method": "colorado_dr1098_2026",
            "filing_status": filing_status,
            "line_1a_gross": line_1a,
            "line_1b_pay_periods": line_1b,
            "line_1c_annualized_wages": line_1c,
            "line_2a_subtraction_amount": line_2a,
            "line_2a_override_used": dr0004_line2_override,
            "line_2b": line_2b,
            "line_2c_tax_at_4_4_percent": line_2c,
            "line_2d_per_period_tax": line_2d,
            "line_2e_additional_withholding": line_2e,
            "line_2f_final_withholding": flt(max(0.0, line_2f), 2),
        },
    }


def get_employee_doc(employee):
    return frappe.get_doc("Employee", employee)


def get_employee_payroll_context(employee, company=None):
    emp = get_employee_doc(employee)
    resolved_company = company or emp.company

    payroll_payable_account = None
    cost_center = None

    if getattr(emp, "payroll_cost_center", None):
        cost_center = emp.payroll_cost_center

    if not cost_center and getattr(emp, "department", None):
        department = frappe.db.get_value(
            "Department",
            emp.department,
            ["payroll_cost_center"],
            as_dict=True,
        )
        if department and department.payroll_cost_center:
            cost_center = department.payroll_cost_center

    company_doc = frappe.get_doc("Company", resolved_company)
    payroll_payable_account = getattr(company_doc, "default_payroll_payable_account", None)

    return {
        "employee_doc": emp,
        "company": resolved_company,
        "currency": getattr(emp, "salary_currency", None) or "USD",
        "payroll_payable_account": payroll_payable_account,
        "cost_center": cost_center,
    }


def get_active_salary_structure_assignment(employee, start_date):
    assignment = frappe.db.get_value(
        "Salary Structure Assignment",
        filters={
            "employee": employee,
            "docstatus": 1,
            "from_date": ["<=", start_date],
        },
        fieldname=["name", "salary_structure", "base"],
        as_dict=True,
        order_by="from_date desc, creation desc",
    )

    if not assignment:
        frappe.throw(
            f"No submitted Salary Structure Assignment found for employee {employee} on or before {start_date}."
        )

    return assignment


def get_existing_draft_slip(employee, start_date, end_date):
    slips = frappe.get_all(
        "Salary Slip",
        filters={
            "employee": employee,
            "start_date": start_date,
            "end_date": end_date,
            "docstatus": 0,
        },
        pluck="name",
        order_by="creation desc",
    )
    return slips[0] if slips else None


def get_existing_submitted_slip(employee, start_date, end_date):
    slips = frappe.get_all(
        "Salary Slip",
        filters={
            "employee": employee,
            "start_date": start_date,
            "end_date": end_date,
            "docstatus": 1,
        },
        pluck="name",
        order_by="creation desc",
    )
    return slips[0] if slips else None


@contextmanager
def custom_salary_slip_save_mode():
    originals = {
        "set_salary_structure_assignment": SalarySlip.set_salary_structure_assignment,
        "calculate_net_pay": SalarySlip.calculate_net_pay,
        "get_working_days_details": SalarySlip.get_working_days_details,
        "compute_year_to_date": SalarySlip.compute_year_to_date,
        "calculate_component_amounts": getattr(SalarySlip, "calculate_component_amounts", None),
        "pull_sal_struct": getattr(SalarySlip, "pull_sal_struct", None),
    }

    def _noop(self, *args, **kwargs):
        return None

    try:
        SalarySlip.set_salary_structure_assignment = _noop
        SalarySlip.calculate_net_pay = _noop
        SalarySlip.get_working_days_details = _noop
        SalarySlip.compute_year_to_date = _noop

        if originals["calculate_component_amounts"]:
            SalarySlip.calculate_component_amounts = _noop
        if originals["pull_sal_struct"]:
            SalarySlip.pull_sal_struct = _noop

        yield
    finally:
        SalarySlip.set_salary_structure_assignment = originals["set_salary_structure_assignment"]
        SalarySlip.calculate_net_pay = originals["calculate_net_pay"]
        SalarySlip.get_working_days_details = originals["get_working_days_details"]
        SalarySlip.compute_year_to_date = originals["compute_year_to_date"]

        if originals["calculate_component_amounts"]:
            SalarySlip.calculate_component_amounts = originals["calculate_component_amounts"]
        if originals["pull_sal_struct"]:
            SalarySlip.pull_sal_struct = originals["pull_sal_struct"]


def ensure_draft_salary_slip(employee, start_date, end_date, payroll_frequency="Weekly", company=None):
    submitted = get_existing_submitted_slip(employee, start_date, end_date)
    if submitted:
        frappe.throw(
            f"Submitted Salary Slip already exists for {employee} {start_date} to {end_date}: {submitted}"
        )

    existing = get_existing_draft_slip(employee, start_date, end_date)
    if existing:
        return frappe.get_doc("Salary Slip", existing)

    payroll_context = get_employee_payroll_context(employee, company=company)
    assignment = get_active_salary_structure_assignment(employee, start_date)

    slip = frappe.get_doc(
        {
            "doctype": "Salary Slip",
            "employee": employee,
            "company": payroll_context["company"],
            "start_date": start_date,
            "end_date": end_date,
            "payroll_frequency": payroll_frequency,
            "currency": payroll_context["currency"],
            "salary_structure": assignment.salary_structure,
        }
    )

    if hasattr(slip, "salary_structure_assignment"):
        slip.salary_structure_assignment = assignment.name

    with custom_salary_slip_save_mode():
        slip.insert(ignore_permissions=True)

    slip.reload()
    return slip


def set_assignment_fields(slip, employee, start_date):
    assignment = get_active_salary_structure_assignment(employee, start_date)
    slip.salary_structure = assignment.salary_structure
    if hasattr(slip, "salary_structure_assignment"):
        slip.salary_structure_assignment = assignment.name
    return assignment


def set_context_fields_on_slip(slip, employee, start_date, end_date, payroll_frequency, company=None):
    payroll_context = get_employee_payroll_context(employee, company=company)
    summary = attendance_summary(employee, start_date, end_date)
    assignment = set_assignment_fields(slip, employee, start_date)

    slip.employee = employee
    slip.company = payroll_context["company"]
    slip.start_date = start_date
    slip.end_date = end_date
    slip.payroll_frequency = payroll_frequency
    slip.currency = payroll_context["currency"]

    if payroll_context["payroll_payable_account"] and hasattr(slip, "payroll_payable_account"):
        slip.payroll_payable_account = payroll_context["payroll_payable_account"]

    if payroll_context["cost_center"] and hasattr(slip, "cost_center"):
        slip.cost_center = payroll_context["cost_center"]

    if hasattr(slip, "payment_days"):
        slip.payment_days = summary["payment_days"]
    if hasattr(slip, "total_working_days"):
        slip.total_working_days = summary["total_working_days"]
    if hasattr(slip, "leave_without_pay"):
        slip.leave_without_pay = 0
    if hasattr(slip, "absent_days"):
        slip.absent_days = summary["absent_days"]
    if hasattr(slip, "total_working_hours"):
        slip.total_working_hours = summary["hours"]

    return payroll_context, summary, assignment


def replace_child_table(doc, table_fieldname, rows):
    doc.set(table_fieldname, [])
    for row in rows:
        doc.append(table_fieldname, row)


def build_earnings_rows(gross):
    return [
        {
            "salary_component": "Hourly Wage",
            "abbr": "HOUR",
            "amount": flt(gross, 2),
            "default_amount": flt(gross, 2),
            "depends_on_payment_days": 0,
        }
    ]


def build_deduction_rows(ss_employee, medicare_employee, federal_withholding=0.0, colorado_withholding=0.0):
    rows = [
        {
            "salary_component": "Social Security",
            "abbr": "SS",
            "amount": flt(ss_employee, 2),
            "default_amount": flt(ss_employee, 2),
            "depends_on_payment_days": 0,
        },
        {
            "salary_component": "Medicare",
            "abbr": "MED",
            "amount": flt(medicare_employee, 2),
            "default_amount": flt(medicare_employee, 2),
            "depends_on_payment_days": 0,
        },
    ]

    if flt(federal_withholding):
        rows.append(
            {
                "salary_component": "Federal Withholding",
                "abbr": "FEDWH",
                "amount": flt(federal_withholding, 2),
                "default_amount": flt(federal_withholding, 2),
                "depends_on_payment_days": 0,
            }
        )

    if flt(colorado_withholding):
        rows.append(
            {
                "salary_component": "Colorado Withholding",
                "abbr": "COWH",
                "amount": flt(colorado_withholding, 2),
                "default_amount": flt(colorado_withholding, 2),
                "depends_on_payment_days": 0,
            }
        )

    return rows


def set_manual_totals(slip):
    earnings_sum = flt(sum(flt(row.amount) for row in slip.earnings), 2)
    deductions_sum = flt(sum(flt(row.amount) for row in slip.deductions), 2)
    net_pay = flt(earnings_sum - deductions_sum, 2)

    if hasattr(slip, "gross_pay"):
        slip.gross_pay = earnings_sum
    if hasattr(slip, "total_deduction"):
        slip.total_deduction = deductions_sum
    if hasattr(slip, "net_pay"):
        slip.net_pay = net_pay
    if hasattr(slip, "rounded_total"):
        slip.rounded_total = net_pay
    if hasattr(slip, "base_gross_pay"):
        slip.base_gross_pay = earnings_sum
    if hasattr(slip, "base_total_deduction"):
        slip.base_total_deduction = deductions_sum
    if hasattr(slip, "base_net_pay"):
        slip.base_net_pay = net_pay

    return {
        "gross_pay": earnings_sum,
        "total_deduction": deductions_sum,
        "net_pay": net_pay,
    }


def normalize_saved_child_rows(slip):
    changed = 0

    for row in list(slip.earnings) + list(slip.deductions):
        target_amount = flt(getattr(row, "amount", 0.0), 2)

        updates = {}
        if cint(getattr(row, "depends_on_payment_days", 0)) != 0:
            updates["depends_on_payment_days"] = 0

        if flt(getattr(row, "default_amount", 0.0), 2) != target_amount:
            updates["default_amount"] = target_amount

        if updates:
            for fieldname, value in updates.items():
                frappe.db.set_value(row.doctype, row.name, fieldname, value, update_modified=False)
            changed += 1

    if changed:
        slip.reload()

    return changed


def save_custom_salary_slip(slip, employee, start_date):
    set_assignment_fields(slip, employee, start_date)

    with custom_salary_slip_save_mode():
        slip.save(ignore_permissions=True)

    slip.reload()
    normalize_saved_child_rows(slip)

    set_manual_totals(slip)
    with custom_salary_slip_save_mode():
        slip.save(ignore_permissions=True)

    slip.reload()
    normalize_saved_child_rows(slip)
    return slip


def validate_custom_math(slip, expected_gross, expected_net):
    actual_gross = flt(getattr(slip, "gross_pay", 0.0), 2)
    actual_net = flt(getattr(slip, "net_pay", 0.0), 2)

    issues = []
    if actual_gross != flt(expected_gross, 2):
        issues.append(f"gross_pay expected {flt(expected_gross, 2)} but got {actual_gross}")
    if actual_net != flt(expected_net, 2):
        issues.append(f"net_pay expected {flt(expected_net, 2)} but got {actual_net}")

    return issues


def diagnose_salary_slip_math(slip_name):
    slip = frappe.get_doc("Salary Slip", slip_name)

    earnings = [
        {
            "salary_component": row.salary_component,
            "amount": flt(row.amount, 2),
            "default_amount": flt(getattr(row, "default_amount", 0.0), 2),
            "depends_on_payment_days": cint(getattr(row, "depends_on_payment_days", 0)),
        }
        for row in slip.earnings
    ]

    deductions = [
        {
            "salary_component": row.salary_component,
            "amount": flt(row.amount, 2),
            "default_amount": flt(getattr(row, "default_amount", 0.0), 2),
            "depends_on_payment_days": cint(getattr(row, "depends_on_payment_days", 0)),
        }
        for row in slip.deductions
    ]

    return {
        "slip_name": slip.name,
        "salary_structure": getattr(slip, "salary_structure", None),
        "salary_structure_assignment": getattr(slip, "salary_structure_assignment", None),
        "payment_days": flt(getattr(slip, "payment_days", 0.0), 2),
        "total_working_days": flt(getattr(slip, "total_working_days", 0.0), 2),
        "gross_pay_field": flt(getattr(slip, "gross_pay", 0.0), 2),
        "total_deduction_field": flt(getattr(slip, "total_deduction", 0.0), 2),
        "net_pay_field": flt(getattr(slip, "net_pay", 0.0), 2),
        "earnings_sum": flt(sum(flt(row.amount) for row in slip.earnings), 2),
        "deductions_sum": flt(sum(flt(row.amount) for row in slip.deductions), 2),
        "earnings": earnings,
        "deductions": deductions,
    }


# ---------------------------------------------------------------------------
# Liability and Journal Entry helpers
# ---------------------------------------------------------------------------

def summarize_payroll_liabilities(payroll_result):
    employee_taxes = {
        "social_security_employee": flt(payroll_result.get("ss_employee", 0.0), 2),
        "medicare_employee": flt(payroll_result.get("medicare_employee", 0.0), 2),
        "federal_withholding": flt(payroll_result.get("federal_withholding", 0.0), 2),
        "colorado_withholding": flt(payroll_result.get("colorado_withholding", 0.0), 2),
    }

    employer_taxes = {
        "social_security_employer": flt(payroll_result.get("ss_employer", 0.0), 2),
        "medicare_employer": flt(payroll_result.get("medicare_employer", 0.0), 2),
    }

    employee_tax_total = flt(sum(employee_taxes.values()), 2)
    employer_tax_total = flt(sum(employer_taxes.values()), 2)
    gross = flt(payroll_result.get("gross", 0.0), 2)
    net_pay = flt(payroll_result.get("net_pay", 0.0), 2)

    return {
        "gross_wages": gross,
        "net_pay": net_pay,
        "employee_taxes": employee_taxes,
        "employee_tax_total": employee_tax_total,
        "employer_taxes": employer_taxes,
        "employer_tax_total": employer_tax_total,
        "total_payroll_expense": flt(gross + employer_tax_total, 2),
        "total_liability_before_cash": flt(employee_tax_total + employer_tax_total, 2),
    }


def get_default_account_by_keywords(company, keywords, account_type=None, root_type=None):
    filters = {"company": company, "is_group": 0, "disabled": 0}

    if account_type:
        filters["account_type"] = account_type
    if root_type:
        filters["root_type"] = root_type

    accounts = frappe.get_all(
        "Account",
        filters=filters,
        fields=["name", "account_name", "account_number", "account_type", "root_type"],
        order_by="name asc",
    )

    lowered_keywords = [k.lower() for k in keywords]
    for acct in accounts:
        haystack = " ".join(
            [
                acct.name or "",
                acct.account_name or "",
                acct.account_number or "",
                acct.account_type or "",
                acct.root_type or "",
            ]
        ).lower()
        if all(k in haystack for k in lowered_keywords):
            return acct.name

    return None


def get_payroll_account_map(company, payroll_payable_account=None):
    company_doc = frappe.get_doc("Company", company)

    expense_account = get_default_account_by_keywords(
        company,
        keywords=["payroll"],
        root_type="Expense",
    ) or get_default_account_by_keywords(
        company,
        keywords=["salary"],
        root_type="Expense",
    )

    if not expense_account:
        expense_account = getattr(company_doc, "default_payroll_payable_account", None)

    payroll_payable = payroll_payable_account or getattr(company_doc, "default_payroll_payable_account", None)

    federal_payable = (
        get_default_account_by_keywords(company, ["federal", "withholding"], root_type="Liability")
        or get_default_account_by_keywords(company, ["federal", "tax"], root_type="Liability")
    )
    colorado_payable = (
        get_default_account_by_keywords(company, ["colorado", "withholding"], root_type="Liability")
        or get_default_account_by_keywords(company, ["state", "withholding"], root_type="Liability")
    )
    ss_payable = (
        get_default_account_by_keywords(company, ["social", "security"], root_type="Liability")
        or get_default_account_by_keywords(company, ["fica", "ss"], root_type="Liability")
    )
    medicare_payable = (
        get_default_account_by_keywords(company, ["medicare"], root_type="Liability")
        or get_default_account_by_keywords(company, ["fica", "medicare"], root_type="Liability")
    )

    return {
        "payroll_expense_account": expense_account,
        "payroll_payable_account": payroll_payable,
        "federal_withholding_payable_account": federal_payable,
        "colorado_withholding_payable_account": colorado_payable,
        "social_security_payable_account": ss_payable,
        "medicare_payable_account": medicare_payable,
    }


def build_payroll_journal_entry_preview(payroll_result):
    slip = frappe.get_doc("Salary Slip", payroll_result["slip_name"])
    company = slip.company
    cost_center = getattr(slip, "cost_center", None)
    posting_date = slip.end_date
    payroll_payable_account = getattr(slip, "payroll_payable_account", None)

    liability = summarize_payroll_liabilities(payroll_result)
    account_map = get_payroll_account_map(company, payroll_payable_account=payroll_payable_account)

    if not account_map["payroll_expense_account"]:
        frappe.throw("Could not resolve a payroll expense account for Journal Entry preview.")
    if not account_map["payroll_payable_account"]:
        frappe.throw("Could not resolve a payroll payable account for Journal Entry preview.")

    lines = []

    def add_line(account, debit=0.0, credit=0.0, remark=None):
        if not account:
            return
        debit = flt(debit, 2)
        credit = flt(credit, 2)
        if not debit and not credit:
            return

        line = {
            "account": account,
            "debit_in_account_currency": debit,
            "credit_in_account_currency": credit,
            "reference_type": "Salary Slip",
            "reference_name": slip.name,
        }
        if cost_center:
            line["cost_center"] = cost_center
        if remark:
            line["user_remark"] = remark
        lines.append(line)

    # Debits
    add_line(
        account_map["payroll_expense_account"],
        debit=liability["gross_wages"],
        remark="Gross wages expense",
    )

    employer_tax_total = liability["employer_tax_total"]
    if employer_tax_total:
        add_line(
            account_map["payroll_expense_account"],
            debit=employer_tax_total,
            remark="Employer payroll tax expense",
        )

    # Credits
    add_line(
        account_map["payroll_payable_account"],
        credit=liability["net_pay"],
        remark="Net payroll payable to employee",
    )

    ss_total = flt(
        liability["employee_taxes"]["social_security_employee"] +
        liability["employer_taxes"]["social_security_employer"],
        2,
    )
    if ss_total:
        add_line(
            account_map["social_security_payable_account"] or account_map["payroll_payable_account"],
            credit=ss_total,
            remark="Social Security payable",
        )

    medicare_total = flt(
        liability["employee_taxes"]["medicare_employee"] +
        liability["employer_taxes"]["medicare_employer"],
        2,
    )
    if medicare_total:
        add_line(
            account_map["medicare_payable_account"] or account_map["payroll_payable_account"],
            credit=medicare_total,
            remark="Medicare payable",
        )

    fed = liability["employee_taxes"]["federal_withholding"]
    if fed:
        add_line(
            account_map["federal_withholding_payable_account"] or account_map["payroll_payable_account"],
            credit=fed,
            remark="Federal withholding payable",
        )

    co = liability["employee_taxes"]["colorado_withholding"]
    if co:
        add_line(
            account_map["colorado_withholding_payable_account"] or account_map["payroll_payable_account"],
            credit=co,
            remark="Colorado withholding payable",
        )

    total_debit = flt(sum(flt(d.get("debit_in_account_currency", 0.0)) for d in lines), 2)
    total_credit = flt(sum(flt(d.get("credit_in_account_currency", 0.0)) for d in lines), 2)

    return {
        "voucher_type": "Journal Entry",
        "company": company,
        "posting_date": posting_date,
        "user_remark": f"Payroll accrual for {slip.employee} {slip.start_date} to {slip.end_date}",
        "accounts": lines,
        "total_debit": total_debit,
        "total_credit": total_credit,
        "is_balanced": total_debit == total_credit,
        "account_map": account_map,
        "liability_summary": liability,
    }


def create_payroll_journal_entry_draft(payroll_result):
    preview = build_payroll_journal_entry_preview(payroll_result)

    if not preview["is_balanced"]:
        frappe.throw(
            f"Journal Entry preview is not balanced: debit={preview['total_debit']} credit={preview['total_credit']}"
        )

    je = frappe.get_doc(
        {
            "doctype": "Journal Entry",
            "voucher_type": preview["voucher_type"],
            "company": preview["company"],
            "posting_date": preview["posting_date"],
            "user_remark": preview["user_remark"],
            "accounts": preview["accounts"],
        }
    )
    je.insert(ignore_permissions=True)
    frappe.db.commit()

    return {
        "journal_entry_name": je.name,
        "posting_date": je.posting_date,
        "company": je.company,
        "total_debit": preview["total_debit"],
        "total_credit": preview["total_credit"],
        "is_balanced": preview["is_balanced"],
        "account_map": preview["account_map"],
        "liability_summary": preview["liability_summary"],
    }


def payroll_register_row(payroll_result):
    liability = summarize_payroll_liabilities(payroll_result)
    return {
        "slip_name": payroll_result["slip_name"],
        "gross_wages": liability["gross_wages"],
        "net_pay": liability["net_pay"],
        "ss_employee": liability["employee_taxes"]["social_security_employee"],
        "medicare_employee": liability["employee_taxes"]["medicare_employee"],
        "federal_withholding": liability["employee_taxes"]["federal_withholding"],
        "colorado_withholding": liability["employee_taxes"]["colorado_withholding"],
        "ss_employer": liability["employer_taxes"]["social_security_employer"],
        "medicare_employer": liability["employer_taxes"]["medicare_employer"],
        "employee_tax_total": liability["employee_tax_total"],
        "employer_tax_total": liability["employer_tax_total"],
        "total_payroll_expense": liability["total_payroll_expense"],
    }


def rebuild_hourly_salary_slip(
    employee,
    start_date,
    end_date,
    hourly_rate=None,
    payroll_frequency="Weekly",
    company=None,
    federal_withholding=None,
    colorado_withholding=None,
    federal_profile=None,
    colorado_profile=None,
    use_employee_tax_profile=True,
):
    stored_profile = get_employee_tax_profile(employee) if use_employee_tax_profile else None

    if hourly_rate is None:
        if stored_profile and stored_profile.get("hourly_rate") is not None:
            hourly_rate = stored_profile["hourly_rate"]
        else:
            frappe.throw(
                f"No hourly_rate provided and no RootedOps Hourly Rate stored on Employee {employee}."
            )

    if federal_withholding is None and not federal_profile and stored_profile:
        candidate = stored_profile.get("federal_profile") or {}
        if candidate.get("filing_status"):
            federal_profile = candidate

    if colorado_withholding is None and not colorado_profile and stored_profile:
        candidate = stored_profile.get("colorado_profile") or {}
        if candidate.get("filing_status"):
            colorado_profile = candidate

    slip = ensure_draft_salary_slip(
        employee=employee,
        start_date=start_date,
        end_date=end_date,
        payroll_frequency=payroll_frequency,
        company=company,
    )

    _, summary, assignment = set_context_fields_on_slip(
        slip=slip,
        employee=employee,
        start_date=start_date,
        end_date=end_date,
        payroll_frequency=payroll_frequency,
        company=company,
    )

    gross = flt(summary["hours"] * flt(hourly_rate), 2)
    ytd_before = ytd_gross_before_period(employee, start_date, exclude_slip_name=slip.name)

    ss_employee = ss_employee_amount(gross, ytd_before)
    medicare_employee = medicare_employee_amount(gross)
    ss_employer = ss_employer_amount(gross, ytd_before)
    medicare_employer = medicare_employer_amount(gross)

    federal_detail = None
    colorado_detail = None

    if federal_withholding is None:
        if federal_profile:
            if payroll_frequency != "Weekly":
                frappe.throw(
                    "Federal withholding automation in this script is currently implemented "
                    "for weekly payroll only."
                )
            fed = calculate_federal_withholding_2026_weekly(gross, federal_profile=federal_profile)
            federal_withholding = fed["withholding"]
            federal_detail = fed["detail"]
        else:
            federal_withholding = 0.0
    else:
        federal_withholding = flt(federal_withholding, 2)

    if colorado_withholding is None:
        if colorado_profile:
            co = calculate_colorado_withholding_2026(
                gross,
                payroll_frequency=payroll_frequency,
                colorado_profile=colorado_profile,
            )
            colorado_withholding = co["withholding"]
            colorado_detail = co["detail"]
        else:
            colorado_withholding = 0.0
    else:
        colorado_withholding = flt(colorado_withholding, 2)

    earnings_rows = build_earnings_rows(gross)
    deduction_rows = build_deduction_rows(
        ss_employee=ss_employee,
        medicare_employee=medicare_employee,
        federal_withholding=federal_withholding,
        colorado_withholding=colorado_withholding,
    )

    replace_child_table(slip, "earnings", earnings_rows)
    replace_child_table(slip, "deductions", deduction_rows)

    manual_totals = set_manual_totals(slip)
    slip = save_custom_salary_slip(slip, employee, start_date)

    issues = validate_custom_math(
        slip=slip,
        expected_gross=manual_totals["gross_pay"],
        expected_net=manual_totals["net_pay"],
    )

    result = {
        "slip_name": slip.name,
        "hours": summary["hours"],
        "payment_days": summary["payment_days"],
        "total_working_days": summary["total_working_days"],
        "absent_days": summary["absent_days"],
        "hourly_rate": flt(hourly_rate, 2),
        "gross": gross,
        "ss_employee": ss_employee,
        "medicare_employee": medicare_employee,
        "federal_withholding": flt(federal_withholding, 2),
        "colorado_withholding": flt(colorado_withholding, 2),
        "ss_employer": ss_employer,
        "medicare_employer": medicare_employer,
        "ytd_gross_before_period": ytd_before,
        "salary_structure_used": assignment.salary_structure,
        "salary_structure_assignment_used": assignment.name,
        "gross_pay_field": flt(getattr(slip, "gross_pay", 0.0), 2),
        "total_deduction_field": flt(getattr(slip, "total_deduction", 0.0), 2),
        "net_pay": flt(getattr(slip, "net_pay", 0.0), 2),
        "stored_employee_tax_profile_used": stored_profile if use_employee_tax_profile else None,
        "federal_detail": federal_detail,
        "colorado_detail": colorado_detail,
        "issues": issues,
        "diagnostic": diagnose_salary_slip_math(slip.name),
    }

    result["liability_summary"] = summarize_payroll_liabilities(result)
    result["payroll_register_row"] = payroll_register_row(result)
    result["journal_entry_preview"] = build_payroll_journal_entry_preview(result)

    frappe.db.commit()
    return result
