import frappe
from frappe.utils import flt

COMPANIES = [
    {
        "company": "Dank Mushrooms, LLC",
        "checking_gl_account": "Dank Mushrooms Checking - DML",
        "withholding_bank_gl_account": "Dank Mushrooms Withholding - DML",
    },
    {
        "company": "Raymond Danks",
        "checking_gl_account": "Elevations Checking - RD",
        "withholding_bank_gl_account": "Elevations Withholding Savings - RD",
    },
]


def meta_has(doctype, fieldname):
    return frappe.get_meta(doctype).has_field(fieldname)


def get_company_defaults(company):
    fields = ["name", "abbr"]
    optional = [
        "default_bank_account",
        "default_payroll_payable_account",
        "default_receivable_account",
        "default_payable_account",
        "cost_center",
    ]
    for f in optional:
        if meta_has("Company", f):
            fields.append(f)
    return frappe.db.get_value("Company", company, fields, as_dict=True)


def get_accounts(company, root_type=None):
    filters = {"company": company, "is_group": 0, "disabled": 0}
    if root_type:
        filters["root_type"] = root_type
    return frappe.get_all(
        "Account",
        filters=filters,
        fields=["name", "account_name", "account_number", "account_type", "root_type"],
        order_by="name asc",
    )


def find_by_keywords(accounts, keyword_groups):
    matches = []
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
        for keywords in keyword_groups:
            if all(k.lower() in haystack for k in keywords):
                matches.append(acct)
                break
    return matches


def get_bank_account_masters(company):
    return frappe.get_all(
        "Bank Account",
        filters={"company": company},
        fields=["name", "bank", "account", "is_company_account", "is_default"],
        order_by="name asc",
    )


def account_exists(name):
    return bool(name and frappe.db.exists("Account", name))


def bank_account_exists(name):
    return bool(name and frappe.db.exists("Bank Account", name))


def audit_company(company_cfg):
    company = company_cfg["company"]
    print("\n" + "=" * 100)
    print(f"COMPANY: {company}")
    print("=" * 100)

    defaults = get_company_defaults(company)
    print("\nCompany defaults:")
    print(defaults)

    expense_accounts = get_accounts(company, root_type="Expense")
    liability_accounts = get_accounts(company, root_type="Liability")
    asset_accounts = get_accounts(company, root_type="Asset")

    print("\nConfigured bank GL accounts expected:")
    print({
        "checking_gl_account": company_cfg["checking_gl_account"],
        "withholding_bank_gl_account": company_cfg["withholding_bank_gl_account"],
        "checking_exists": account_exists(company_cfg["checking_gl_account"]),
        "withholding_bank_exists": account_exists(company_cfg["withholding_bank_gl_account"]),
    })

    print("\nBank Account masters:")
    for row in get_bank_account_masters(company):
        print("  ", row)

    payroll_expense_matches = find_by_keywords(
        expense_accounts,
        [
            ["payroll", "expense"],
            ["wages"],
            ["salary"],
            ["labor"],
            ["nanny", "wages"],
        ],
    )

    payroll_tax_expense_matches = find_by_keywords(
        expense_accounts,
        [
            ["payroll", "tax", "expense"],
            ["employer", "tax"],
            ["payroll", "tax"],
        ],
    )

    payroll_payable_matches = find_by_keywords(
        liability_accounts,
        [
            ["payroll", "payable"],
            ["salary", "payable"],
            ["wages", "payable"],
        ],
    )

    payroll_tax_payable_matches = find_by_keywords(
        liability_accounts,
        [
            ["payroll", "tax", "payable"],
            ["payroll", "tax"],
        ],
    )

    withholding_payable_matches = find_by_keywords(
        liability_accounts,
        [
            ["withholding", "payable"],
            ["payroll", "withholding", "payable"],
            ["federal", "withholding"],
            ["state", "withholding"],
        ],
    )

    print("\nLikely payroll expense accounts:")
    for row in payroll_expense_matches:
        print("  ", row)

    print("\nLikely payroll tax expense accounts:")
    for row in payroll_tax_expense_matches:
        print("  ", row)

    print("\nLikely payroll payable accounts:")
    for row in payroll_payable_matches:
        print("  ", row)

    print("\nLikely payroll tax payable accounts:")
    for row in payroll_tax_payable_matches:
        print("  ", row)

    print("\nLikely withholding payable accounts:")
    for row in withholding_payable_matches:
        print("  ", row)

    try:
        from rootedops_payroll.services.payroll_engine import get_payroll_account_map, unresolved_payroll_accounts

        account_map = get_payroll_account_map(
            company=company,
            payroll_payable_account=defaults.get("default_payroll_payable_account"),
            overrides=None,
        )
        missing = unresolved_payroll_accounts(account_map)

        print("\nCustom payroll engine account map:")
        print(account_map)

        print("\nMissing required account-map keys:")
        print(missing)

    except Exception as e:
        print("\n[ERROR] Could not evaluate custom payroll engine account map:")
        print(repr(e))

    print("\nSanity checks:")
    print({
        "default_bank_account_present": bool(defaults.get("default_bank_account")),
        "default_payroll_payable_present": bool(defaults.get("default_payroll_payable_account")),
        "checking_gl_exists": account_exists(company_cfg["checking_gl_account"]),
        "withholding_bank_gl_exists": account_exists(company_cfg["withholding_bank_gl_account"]),
    })


def run():
    for cfg in COMPANIES:
        if not frappe.db.exists("Company", cfg["company"]):
            print(f"[SKIP] Missing company: {cfg['company']}")
            continue
        audit_company(cfg)


run()
