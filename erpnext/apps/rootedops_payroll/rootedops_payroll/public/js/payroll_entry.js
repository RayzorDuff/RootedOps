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

function salarySlipLink(name) {
  if (!name) return "None";
  return `<a href="/app/salary-slip/${encodeURIComponent(name)}">${frappe.utils.escape_html(name)}</a>`;
}

function employeePaymentStatusHtml(data) {
  const summary = data.payment_summary || {};
  const statuses = data.payment_statuses || [];
  const rows = statuses.map((row) => {
    const accountingErrors = (row.accounting_errors || []).map((message) => (
      frappe.utils.escape_html(message)
    )).join(" ");
    const accountingDetail = accountingErrors
      ? `<br><small class="text-danger">${accountingErrors}</small>`
      : "";
    return `
      <tr>
        <td>${frappe.utils.escape_html(row.employee_name || row.employee || "")}</td>
        <td>${salarySlipLink(row.salary_slip)}</td>
        <td>${frappe.utils.escape_html(row.payment_method || "")}</td>
        <td>${formatMoney(row.net_pay)}</td>
        <td>${frappe.utils.escape_html(row.status || "")}</td>
        <td>${row.journal_entry ? journalEntryLink(row.journal_entry) : "None"}</td>
        <td>${row.attempt_count || 0}</td>
        <td>${frappe.utils.escape_html(row.accounting_status || "Not Recorded")}${accountingDetail}</td>
      </tr>
    `;
  }).join("");

  let alertClass = "alert-info";
  let alertText = "Employee payment accounting is not yet fully recorded.";
  if ((summary.conflict_count || 0) > 0 || (summary.accounting_mismatch_count || 0) > 0) {
    alertClass = "alert-danger";
    alertText = "Employee payment accounting needs review before further settlement activity.";
  } else if (summary.all_positive_net_pay_recorded && summary.all_accounting_consistent) {
    alertClass = "alert-success";
    alertText = "All positive-net-pay Salary Slips have an active employee payment JE and recorded accounting matches net pay.";
  }

  const legacy = data.legacy_employee_payment_journal_entry;
  const legacyWarning = legacy && Number(data.legacy_employee_payment_docstatus) !== 2
    ? `<div class="alert alert-warning">Legacy consolidated employee-payment JE ${journalEntryLink(legacy)} is still active and blocks employee-specific settlement.</div>`
    : "";

  return `
    <div class="alert ${alertClass}">${alertText}</div>
    ${legacyWarning}
    <div class="row">
      <div class="col-sm-3"><b>Expected Net Pay</b><br>${formatMoney(summary.expected_net_pay_total)}</div>
      <div class="col-sm-3"><b>Draft Payment JEs</b><br>${formatMoney(summary.draft_payment_total)}</div>
      <div class="col-sm-3"><b>Submitted Payment JEs</b><br>${formatMoney(summary.submitted_payment_total)}</div>
      <div class="col-sm-3"><b>Outstanding</b><br>${formatMoney(summary.outstanding_net_pay_total)}</div>
    </div>
    <br>
    <table class="table table-bordered table-condensed">
      <thead>
        <tr><th>Employee</th><th>Salary Slip</th><th>Method</th><th>Net Pay</th><th>Status</th><th>Current / Last JE</th><th>Attempts</th><th>Accounting</th></tr>
      </thead>
      <tbody>${rows || '<tr><td colspan="8">No submitted Salary Slips found.</td></tr>'}</tbody>
    </table>
  `;
}

function renderEmployeePaymentStatusPanel(frm, data) {
  const field = frm.fields_dict && frm.fields_dict.rootedops_employee_payment_status_html;
  if (!field || !field.$wrapper) return;
  field.$wrapper.html(employeePaymentStatusHtml(data || {}));
}

function refreshEmployeePaymentStatusPanel(frm) {
  const field = frm.fields_dict && frm.fields_dict.rootedops_employee_payment_status_html;
  if (!field || !field.$wrapper) return;

  field.$wrapper.html('<p class="text-muted">Loading employee payment status...</p>');
  frappe.call({
    method: "rootedops_payroll.api.payroll_entry_actions.get_employee_payment_statuses",
    args: { payroll_entry_name: frm.doc.name }
  }).then((r) => {
    renderEmployeePaymentStatusPanel(frm, r.message || {});
  }).catch(() => {
    field.$wrapper.html('<p class="text-muted">Employee payment status could not be loaded.</p>');
  });
}

frappe.ui.form.on("Payroll Entry", {
  refresh(frm) {
    if (frm.is_new()) return;

    refreshEmployeePaymentStatusPanel(frm);

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

    frm.add_custom_button("Review Employee Payment Status", () => {
      frappe.call({
        method: "rootedops_payroll.api.payroll_entry_actions.get_employee_payment_statuses",
        args: { payroll_entry_name: frm.doc.name },
        freeze: true,
        freeze_message: "Resolving employee payment status..."
      }).then((r) => {
        const data = r.message || {};
        renderEmployeePaymentStatusPanel(frm, data);

        frappe.msgprint({
          title: "Employee Payment Status",
          wide: true,
          message: employeePaymentStatusHtml(data)
        });
      });
    }, "RootedOps Payroll");

    frm.add_custom_button("Create Employee Payment Draft JEs", () => {
      frappe.call({
        method: "rootedops_payroll.api.payroll_entry_actions.create_employee_payment_draft_journal_entry",
        args: { payroll_entry_name: frm.doc.name },
        freeze: true,
        freeze_message: "Creating employee-specific payment Journal Entry drafts..."
      }).then((r) => {
        const data = r.message || {};
        const rows = (data.journal_entries || []).map((row) => `
          <tr>
            <td>${frappe.utils.escape_html(row.employee_name || row.employee || "")}</td>
            <td>${frappe.utils.escape_html(row.payment_method || "")}</td>
            <td>${formatMoney(row.net_pay)}</td>
            <td>${frappe.utils.escape_html(row.status || "Payment JE Draft")}</td>
            <td>${row.payment_attempt || 1}</td>
            <td>${journalEntryLink(row.journal_entry)}</td>
          </tr>
        `).join("");
        frappe.msgprint({
          title: "Employee Payment JE Drafts Created",
          message: `
            <p><b>Checking Bank:</b> ${frappe.utils.escape_html(data.checking_bank_account || "Not resolved")}</p>
            <p><b>Employees:</b> ${data.employee_count || 0}</p>
            <p><b>Total Net Pay:</b> ${formatMoney(data.total_net_pay)}</p>
            <table class="table table-bordered">
              <thead><tr><th>Employee</th><th>Method</th><th>Net Pay</th><th>Status</th><th>Attempt</th><th>Journal Entry</th></tr></thead>
              <tbody>${rows}</tbody>
            </table>
          `
        });
        frm.reload_doc();
      });
    }, "RootedOps Payroll");

    frm.add_custom_button("Preview NACHA Payroll", () => {
      const dialog = new frappe.ui.Dialog({
        title: "NACHA Payroll Pre-Export Review",
        fields: [
          {
            fieldname: "profile_name",
            label: "NACHA Profile",
            fieldtype: "Link",
            options: "RootedOps NACHA Profile",
            reqd: 1,
            get_query: () => ({ filters: { company: frm.doc.company } })
          },
          {
            fieldname: "effective_entry_date",
            label: "Effective ACH Date",
            fieldtype: "Date",
            default: frm.doc.end_date,
            reqd: 1,
            description: "Confirm this date against the bank's ACH cutoff and settlement rules."
          }
        ],
        primary_action_label: "Review Payroll",
        primary_action(values) {
          frappe.call({
            method: "rootedops_payroll.api.payroll_entry_actions.preview_nacha_payroll",
            args: {
              payroll_entry_name: frm.doc.name,
              profile_name: values.profile_name,
              effective_entry_date: values.effective_entry_date
            },
            freeze: true,
            freeze_message: "Validating payroll for NACHA export..."
          }).then((r) => {
            dialog.hide();
            const data = r.message || {};
            const employees = (data.employees || []).map((row) => `
              <tr>
                <td>${frappe.utils.escape_html(row.employee_name || row.employee || "")}</td>
                <td>${salarySlipLink(row.salary_slip)}</td>
                <td>${frappe.utils.escape_html(row.account_type || "")}</td>
                <td>${formatMoney(row.net_pay)}</td>
                <td>${frappe.utils.escape_html(row.routing_number_masked || "")}</td>
                <td>${frappe.utils.escape_html(row.account_number_masked || "")}</td>
              </tr>
            `).join("");
            const excluded = (data.excluded_employees || []).map((row) => `
              <tr>
                <td>${frappe.utils.escape_html(row.employee_name || row.employee || "")}</td>
                <td>${salarySlipLink(row.salary_slip)}</td>
                <td>${frappe.utils.escape_html(row.payment_method || "")}</td>
                <td>${formatMoney(row.net_pay)}</td>
                <td>${frappe.utils.escape_html(row.reason || "")}</td>
              </tr>
            `).join("");
            frappe.msgprint({
              title: "NACHA Payroll Pre-Export Review",
              wide: true,
              message: `
                <div class="alert alert-success">${frappe.utils.escape_html(data.validation_status || "Validation complete")}</div>
                <p><b>Payroll Entry:</b> ${frappe.utils.escape_html(data.payroll_entry || "")}</p>
                <p><b>Pay Period:</b> ${frappe.utils.escape_html(data.pay_period_start || "")} to ${frappe.utils.escape_html(data.pay_period_end || "")}</p>
                <p><b>Effective ACH Date:</b> ${frappe.utils.escape_html(data.effective_entry_date || "")}</p>
                <p><b>ACH Employees:</b> ${data.ach_employee_count || 0} &nbsp; <b>ACH Total:</b> ${formatMoney(data.ach_total)}</p>
                <p><b>All Payroll Net Pay:</b> ${formatMoney(data.total_payroll_net_pay)}</p>
                <p><b>Excluded:</b> ${data.excluded_count || 0}</p>
                <hr>
                <h5>Employees included in ACH</h5>
                <table class="table table-bordered table-condensed">
                  <thead><tr><th>Employee</th><th>Salary Slip</th><th>Account</th><th>Net Pay</th><th>Routing</th><th>Account</th></tr></thead>
                  <tbody>${employees || '<tr><td colspan="6">None</td></tr>'}</tbody>
                </table>
                <h5>Excluded from ACH</h5>
                <table class="table table-bordered table-condensed">
                  <thead><tr><th>Employee</th><th>Salary Slip</th><th>Method</th><th>Net Pay</th><th>Reason</th></tr></thead>
                  <tbody>${excluded || '<tr><td colspan="5">None</td></tr>'}</tbody>
                </table>
                <p class="text-muted"><b>Read-only:</b> no NACHA file was generated, downloaded, submitted, or persisted.</p>
              `
            });
          });
        }
      });
      dialog.show();
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
