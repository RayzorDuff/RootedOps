function formatMoney(value) {
  return format_currency(value || 0);
}

function journalEntryLink(name) {
  if (!name) return "None";
  return `<a href="/app/journal-entry/${encodeURIComponent(name)}">${frappe.utils.escape_html(name)}</a>`;
}

function salarySlipLinks(names) {
  return (names || []).map((name) => (
    `<a href="/app/salary-slip/${encodeURIComponent(name)}">${frappe.utils.escape_html(name)}</a>`
  )).join("<br>");
}

frappe.ui.form.on("Payroll Entry", {
  refresh(frm) {
    if (frm.is_new()) return;

    frm.add_custom_button("Preview Attendance Payroll", () => {
      frappe.call({
        method: "rootedops_payroll.api.payroll_entry_actions.preview_attendance_payroll",
        args: { payroll_entry_name: frm.doc.name },
        freeze: true,
        freeze_message: "Previewing attendance payroll..."
      }).then((r) => {
        const data = r.message || {};
        const summary = data.summary || {};
        const liability = summary.consolidated_liability_summary || {};
        const jePreview = summary.consolidated_journal_entry_preview || {};
        const employeeTaxes = liability.employee_taxes || {};
        const employerTaxes = liability.employer_taxes || {};

        frappe.msgprint({
          title: "Attendance Payroll Preview",
          message: `
            <p><b>Employees:</b> ${summary.employee_count || 0}</p>
            <p><b>Gross Wages:</b> ${formatMoney(liability.gross_wages)}</p>
            <p><b>Net Pay:</b> ${formatMoney(liability.net_pay)}</p>
            <hr><p><b>Employee taxes and withholding</b></p>
            <p>Social Security: ${formatMoney(employeeTaxes.social_security_employee)}</p>
            <p>Medicare: ${formatMoney(employeeTaxes.medicare_employee)}</p>
            <p>Federal Withholding: ${formatMoney(employeeTaxes.federal_withholding)}</p>
            <p>Colorado Withholding: ${formatMoney(employeeTaxes.colorado_withholding)}</p>
            <p>Colorado FAMLI: ${formatMoney(employeeTaxes.colorado_famli_employee)}</p>
            <p><b>Employee Taxes:</b> ${formatMoney(liability.employee_tax_total)}</p>
            <hr><p><b>Employer taxes</b></p>
            <p>Social Security: ${formatMoney(employerTaxes.social_security_employer)}</p>
            <p>Medicare: ${formatMoney(employerTaxes.medicare_employer)}</p>
            <p>Colorado UI: ${formatMoney(employerTaxes.colorado_ui_employer)}</p>
            <p>Colorado FAMLI: ${formatMoney(employerTaxes.colorado_famli_employer)}</p>
            <p><b>Employer Taxes:</b> ${formatMoney(liability.employer_tax_total)}</p>
            <p><b>Total Payroll Expense:</b> ${formatMoney(liability.total_payroll_expense)}</p>
            <p><b>JE Balanced:</b> ${jePreview.is_balanced ? "Yes" : "No"}</p>
          `
        });
      });
    }, "RootedOps Payroll");

    frm.add_custom_button("Preview Payroll Cash Flow", () => {
      frappe.call({
        method: "rootedops_payroll.api.payroll_entry_actions.preview_payroll_cash_flow",
        args: { payroll_entry_name: frm.doc.name },
        freeze: true,
        freeze_message: "Previewing payroll cash flow..."
      }).then((r) => {
        const data = r.message || {};
        const summary = data.summary || {};
        const cf = summary.consolidated_cash_flow_preview || {};
        const liability = cf.liability_summary || {};
        const banks = cf.recommended_bank_accounts || {};
        const payment = cf.employee_payment_preview || {};
        const reserve = cf.tax_reserve_transfer_preview || {};
        const remit = cf.tax_remittance_preview || {};
        const employeeTaxes = liability.employee_taxes || {};
        const employerTaxes = liability.employer_taxes || {};

        frappe.msgprint({
          title: "Payroll Cash Flow Preview",
          wide: true,
          message: `
            <p><b>Employees:</b> ${cf.employee_count || summary.employee_count || 0}</p>
            <p><b>Checking Bank:</b> ${frappe.utils.escape_html(banks.checking_bank_account || "Not resolved")}</p>
            <p><b>Withholding Bank:</b> ${frappe.utils.escape_html(banks.withholding_bank_account || "Not resolved")}</p>
            <hr>
            <p><b>Net Pay to Employees:</b> ${formatMoney(liability.net_pay)}</p>
            <p><b>Total Tax Reserve Transfer:</b> ${formatMoney(liability.total_liability_before_cash)}</p>
            <p><b>Employee Taxes:</b> ${formatMoney(liability.employee_tax_total)}</p>
            <p>Employee Colorado FAMLI: ${formatMoney(employeeTaxes.colorado_famli_employee)}</p>
            <p><b>Employer Taxes:</b> ${formatMoney(liability.employer_tax_total)}</p>
            <p>Employer Social Security: ${formatMoney(employerTaxes.social_security_employer)}</p>
            <p>Employer Medicare: ${formatMoney(employerTaxes.medicare_employer)}</p>
            <p>Colorado UI: ${formatMoney(employerTaxes.colorado_ui_employer)}</p>
            <p>Employer Colorado FAMLI: ${formatMoney(employerTaxes.colorado_famli_employer)}</p>
            <hr>
            <p><b>Employee Payment JE Balanced:</b> ${payment.is_balanced ? "Yes" : "No"}</p>
            <p><b>Tax Reserve Transfer JE Balanced:</b> ${reserve.is_balanced ? "Yes" : "No"}</p>
            <p><b>Tax Remittance JE Balanced:</b> ${remit.is_balanced ? "Yes" : "No"}</p>
          `
        });
      });
    }, "RootedOps Payroll");

    frm.add_custom_button("Create / Refresh Draft Salary Slips", () => {
      frappe.call({
        method: "rootedops_payroll.api.payroll_entry_actions.create_or_refresh_draft_salary_slips",
        args: { payroll_entry_name: frm.doc.name },
        freeze: true,
        freeze_message: "Creating or refreshing salary slips..."
      }).then((r) => {
        const data = r.message || {};
        const slips = data.salary_slip_names || [];

        frappe.msgprint({
          title: "Draft Salary Slips Created",
          wide: true,
          message: `
            <p><b>Employees:</b> ${data.employee_count || 0}</p>
            <p><b>Salary Slips:</b> ${slips.length}</p>
            <p>${salarySlipLinks(slips) || "None"}</p>
          `
        });
      });
    }, "RootedOps Payroll");

    frm.add_custom_button("Create Consolidated Draft JE", () => {
      frappe.call({
        method: "rootedops_payroll.api.payroll_entry_actions.create_consolidated_draft_journal_entry",
        args: { payroll_entry_name: frm.doc.name },
        freeze: true,
        freeze_message: "Creating consolidated Journal Entry draft..."
      }).then((r) => {
        const data = r.message || {};
        if (data.journal_entry_skipped) {
          frappe.msgprint({
            title: "Payroll Completed — No JE Required",
            indicator: "green",
            message: `
              <p>${frappe.utils.escape_html(data.skip_reason || "No accounting entry was required for this payroll period.")}</p>
              <p><b>Salary Slips:</b> ${(data.salary_slip_names || []).length}</p>
            `
          });
        } else {
          frappe.msgprint({
            title: "Consolidated JE Draft Created",
            message: `
              <p><b>Journal Entry:</b> ${journalEntryLink(data.journal_entry)}</p>
            `
          });
        }
        frm.reload_doc();
      });
    }, "RootedOps Payroll");

    frm.add_custom_button("Create Employee Payment Draft JE", () => {
      frappe.call({
        method: "rootedops_payroll.api.payroll_entry_actions.create_employee_payment_draft_journal_entry",
        args: { payroll_entry_name: frm.doc.name },
        freeze: true,
        freeze_message: "Creating employee payment Journal Entry draft..."
      }).then((r) => {
        const data = r.message || {};
        const liability = data.liability_summary || {};
        const banks = data.recommended_bank_accounts || {};
        frappe.msgprint({
          title: "Employee Payment JE Draft Created",
          message: `
            <p><b>Journal Entry:</b> ${journalEntryLink(data.journal_entry)}</p>
            <p><b>Checking Bank:</b> ${frappe.utils.escape_html(banks.checking_bank_account || "Not resolved")}</p>
            <p><b>Net Pay:</b> ${formatMoney(liability.net_pay)}</p>
          `
        });
        frm.reload_doc();
      });
    }, "RootedOps Payroll");

    frm.add_custom_button("Create Tax Reserve Transfer Draft JE", () => {
      frappe.call({
        method: "rootedops_payroll.api.payroll_entry_actions.create_tax_reserve_transfer_draft_journal_entry",
        args: { payroll_entry_name: frm.doc.name },
        freeze: true,
        freeze_message: "Creating tax reserve transfer Journal Entry draft..."
      }).then((r) => {
        const data = r.message || {};
        const liability = data.liability_summary || {};
        const banks = data.recommended_bank_accounts || {};
        frappe.msgprint({
          title: "Tax Reserve Transfer JE Draft Created",
          message: `
            <p><b>Journal Entry:</b> ${journalEntryLink(data.journal_entry)}</p>
            <p><b>Checking Bank:</b> ${frappe.utils.escape_html(banks.checking_bank_account || "Not resolved")}</p>
            <p><b>Withholding Bank:</b> ${frappe.utils.escape_html(banks.withholding_bank_account || "Not resolved")}</p>
            <p><b>Total Tax Reserve:</b> ${formatMoney(liability.total_liability_before_cash)}</p>
          `
        });
        frm.reload_doc();
      });
    }, "RootedOps Payroll");
  }
});
