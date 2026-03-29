import frappe
from frappe.utils import cint

APPLY = False

CONFIG = [
    {
        "company": "Dank Mushrooms, LLC",
        "bank": "High Plains Bank",
        "accounts": [
            {
                "label": "Checking",
                "existing_gl_account_name": "Dank Mushrooms Checking - DML",
                "bank_account_name": "Dank Mushrooms Checking - High Plains Bank",
                "bank_account_no": None,
                "is_default": 1,
            },
            {
                "label": "Withholding",
                "existing_gl_account_name": "Dank Mushrooms Withholding - DML",
                "bank_account_name": "Dank Mushrooms Withholding - High Plains Bank",
                "bank_account_no": None,
                "is_default": 0,
            },
        ],
    },
    {
        "company": "Raymond Danks",
        "bank": "Elevations Credit Union",
        "accounts": [
            {
                "label": "Checking",
                "gl_account_base_name": "Elevations Checking",
                "bank_account_name": "Raymond Danks Elevations Checking",
                "bank_account_no": None,
                "is_default": 1,
            },
            {
                "label": "Withholding Savings",
                "gl_account_base_name": "Elevations Withholding Savings",
                "bank_account_name": "Raymond Danks Elevations Withholding Savings",
                "bank_account_no": None,
                "is_default": 0,
            },
        ],
    },
]


def meta_has(doctype, fieldname):
    return frappe.get_meta(doctype).has_field(fieldname)


def get_company_abbr(company):
    return frappe.db.get_value("Company", company, "abbr")


def expected_account_name(company, account_base_name):
    abbr = get_company_abbr(company)
    return f"{account_base_name} - {abbr}"


def get_company_row(company):
    fields = ["name", "abbr"]
    if meta_has("Company", "default_bank_account"):
        fields.append("default_bank_account")
    if meta_has("Company", "default_payroll_payable_account"):
        fields.append("default_payroll_payable_account")
    return frappe.db.get_value("Company", company, fields, as_dict=True)


def find_bank_parent(company):
    # Prefer a Bank group node first
    group_bank = frappe.get_all(
        "Account",
        filters={
            "company": company,
            "root_type": "Asset",
            "is_group": 1,
            "account_type": "Bank",
        },
        fields=["name"],
        order_by="name asc",
        limit=1,
    )
    if group_bank:
        return group_bank[0]["name"]

    # Then infer from an existing bank leaf
    existing_bank_leaf = frappe.get_all(
        "Account",
        filters={
            "company": company,
            "root_type": "Asset",
            "account_type": "Bank",
            "is_group": 0,
        },
        fields=["name", "parent_account"],
        order_by="name asc",
        limit=1,
    )
    if existing_bank_leaf and existing_bank_leaf[0].get("parent_account"):
        return existing_bank_leaf[0]["parent_account"]

    abbr = get_company_abbr(company)
    common_names = [
        f"Bank Accounts - {abbr}",
        f"Current Assets - {abbr}",
    ]
    for name in common_names:
        if frappe.db.exists("Account", name):
            return name

    asset_parent = frappe.get_all(
        "Account",
        filters={
            "company": company,
            "root_type": "Asset",
            "is_group": 1,
        },
        fields=["name"],
        order_by="name asc",
        limit=1,
    )
    if asset_parent:
        return asset_parent[0]["name"]

    raise Exception(f"Could not find a parent Asset account for company {company}")


def ensure_bank(bank_name):
    if frappe.db.exists("Bank", bank_name):
        print(f"[OK] Bank exists: {bank_name}")
        return bank_name, False

    if not APPLY:
        print(f"[DRY RUN] Would create Bank: {bank_name}")
        return bank_name, True

    doc = frappe.get_doc({
        "doctype": "Bank",
        "bank_name": bank_name,
    })
    doc.insert(ignore_permissions=True)
    print(f"[CREATE] Bank: {doc.name}")
    return doc.name, True


def ensure_existing_gl_account(company, account_name):
    if frappe.db.exists("Account", account_name):
        print(f"[OK] GL Account exists: {account_name}")
        return account_name, False
    raise Exception(f"Configured existing GL account not found for {company}: {account_name}")


def ensure_gl_bank_account(company, account_base_name):
    expected_name = expected_account_name(company, account_base_name)

    if frappe.db.exists("Account", expected_name):
        print(f"[OK] GL Account exists: {expected_name}")
        return expected_name, False

    if frappe.db.exists("Account", account_base_name):
        print(f"[OK] GL Account exists (legacy/base name): {account_base_name}")
        return account_base_name, False

    parent_account = find_bank_parent(company)

    if not APPLY:
        print(
            f"[DRY RUN] Would create Account: {account_base_name} "
            f"(expected final: {expected_name}) under {parent_account}"
        )
        return expected_name, True

    doc = frappe.get_doc({
        "doctype": "Account",
        "account_name": account_base_name,
        "company": company,
        "parent_account": parent_account,
        "root_type": "Asset",
        "report_type": "Balance Sheet",
        "account_type": "Bank",
        "is_group": 0,
    })
    doc.insert(ignore_permissions=True)
    print(f"[CREATE] Account: {doc.name}")
    return doc.name, True


def find_bank_account_by_gl(company, gl_account):
    rows = frappe.get_all(
        "Bank Account",
        filters={
            "company": company,
            "account": gl_account,
            "is_company_account": 1,
        },
        fields=["name", "bank", "account", "company", "is_default"],
        limit=1,
    )
    return rows[0] if rows else None


def find_bank_account_by_name(company, bank_account_name):
    if meta_has("Bank Account", "bank_account_name"):
        rows = frappe.get_all(
            "Bank Account",
            filters={
                "company": company,
                "bank_account_name": bank_account_name,
            },
            fields=["name", "bank", "account", "company", "is_default"],
            limit=1,
        )
        if rows:
            return rows[0]

    if meta_has("Bank Account", "account_name"):
        rows = frappe.get_all(
            "Bank Account",
            filters={
                "company": company,
                "account_name": bank_account_name,
            },
            fields=["name", "bank", "account", "company", "is_default"],
            limit=1,
        )
        if rows:
            return rows[0]

    rows = frappe.get_all(
        "Bank Account",
        filters={
            "company": company,
            "name": bank_account_name,
        },
        fields=["name", "bank", "account", "company", "is_default"],
        limit=1,
    )
    return rows[0] if rows else None


def ensure_bank_account(
    company,
    bank_name,
    gl_account,
    bank_account_name,
    bank_account_no=None,
    is_default=0,
):
    existing = find_bank_account_by_gl(company, gl_account) or find_bank_account_by_name(company, bank_account_name)

    if existing:
        changed = False
        if APPLY:
            updates = {}
            if existing.get("bank") != bank_name:
                updates["bank"] = bank_name
            if existing.get("account") != gl_account:
                updates["account"] = gl_account
            if cint(existing.get("is_default")) != cint(is_default):
                updates["is_default"] = cint(is_default)

            if updates:
                frappe.db.set_value("Bank Account", existing["name"], updates, update_modified=False)
                changed = True
                print(f"[UPDATE] Bank Account: {existing['name']} -> {updates}")
            else:
                print(f"[OK] Bank Account exists: {existing['name']}")
        else:
            print(f"[OK] Bank Account exists for {gl_account}: {existing['name']}")
        return existing["name"], changed

    payload = {
        "doctype": "Bank Account",
        "bank": bank_name,
        "account": gl_account,
        "company": company,
        "is_company_account": 1,
        "is_default": cint(is_default),
    }

    # IMPORTANT: this site requires account_name for autoname
    if meta_has("Bank Account", "account_name"):
        payload["account_name"] = bank_account_name

    if meta_has("Bank Account", "bank_account_name"):
        payload["bank_account_name"] = bank_account_name

    if meta_has("Bank Account", "party_type"):
        payload["party_type"] = "Company"
    if meta_has("Bank Account", "party"):
        payload["party"] = company
    if meta_has("Bank Account", "bank_account_no") and bank_account_no:
        payload["bank_account_no"] = bank_account_no

    if not APPLY:
        print(f"[DRY RUN] Would create Bank Account for {gl_account}: {bank_account_name}")
        return bank_account_name, True

    doc = frappe.get_doc(payload)
    doc.insert(ignore_permissions=True)
    print(f"[CREATE] Bank Account: {doc.name}")
    return doc.name, True


def maybe_set_company_default_bank_account(company, bank_account_name):
    if not meta_has("Company", "default_bank_account"):
        print(f"[INFO] Company.default_bank_account not present on this site for {company}")
        return False

    current = frappe.db.get_value("Company", company, "default_bank_account")
    if current == bank_account_name:
        print(f"[OK] Company.default_bank_account already set for {company}")
        return False

    if not APPLY:
        print(f"[DRY RUN] Would set Company.default_bank_account for {company} -> {bank_account_name}")
        return True

    frappe.db.set_value("Company", company, "default_bank_account", bank_account_name, update_modified=False)
    print(f"[UPDATE] Company.default_bank_account for {company} -> {bank_account_name}")
    return True


def show_company_state(company):
    print("\n" + "=" * 90)
    print(f"COMPANY: {company}")
    print("-" * 90)

    print("Company:", get_company_row(company))

    accounts = frappe.get_all(
        "Account",
        filters={
            "company": company,
            "root_type": "Asset",
        },
        fields=["name", "parent_account", "account_type", "is_group"],
        order_by="name asc",
    )
    bankish = [a for a in accounts if a.get("account_type") == "Bank" or "bank" in (a.get("name") or "").lower()]
    print("\nGL bank-related accounts:")
    for row in bankish:
        print("  ", row)

    bank_accounts = frappe.get_all(
        "Bank Account",
        filters={"company": company},
        fields=["name", "bank", "account", "is_company_account", "is_default"],
        order_by="name asc",
    )
    print("\nBank Account masters:")
    for row in bank_accounts:
        print("  ", row)


def resolve_gl_account(company, acct_cfg):
    if acct_cfg.get("existing_gl_account_name"):
        return ensure_existing_gl_account(company, acct_cfg["existing_gl_account_name"])
    return ensure_gl_bank_account(company, acct_cfg["gl_account_base_name"])


def run():
    for cfg in CONFIG:
        company = cfg["company"]
        bank_name = cfg["bank"]

        if not frappe.db.exists("Company", company):
            print(f"[SKIP] Company not found: {company}")
            continue

        show_company_state(company)
        ensure_bank(bank_name)

        default_bank_account_name = None

        for acct in cfg["accounts"]:
            gl_account, _ = resolve_gl_account(company, acct)
            bank_account_name, _ = ensure_bank_account(
                company=company,
                bank_name=bank_name,
                gl_account=gl_account,
                bank_account_name=acct["bank_account_name"],
                bank_account_no=acct.get("bank_account_no"),
                is_default=acct.get("is_default", 0),
            )
            if cint(acct.get("is_default", 0)):
                default_bank_account_name = bank_account_name

        if default_bank_account_name:
            maybe_set_company_default_bank_account(company, default_bank_account_name)

        print("\nPost-run state:")
        show_company_state(company)

    if APPLY:
        frappe.db.commit()
        print("\n[COMMIT] Changes committed.")
    else:
        print("\n[DRY RUN COMPLETE] No changes committed.")


run()
