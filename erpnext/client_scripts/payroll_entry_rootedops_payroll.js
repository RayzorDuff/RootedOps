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

        frappe.msgprint({
          title: "Attendance Payroll Preview",
          message: `
            <p><b>Employees:</b> ${summary.employee_count || 0}</p>
            <p><b>Gross Wages:</b> ${formatMoney(liability.gross_wages)}</p>
            <p><b>Net Pay:</b> ${formatMoney(liability.net_pay)}</p>
            <p><b>Employee Taxes:</b> ${formatMoney(liability.employee_tax_total)}</p>
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
            <p><b>Employer Taxes:</b> ${formatMoney(liability.employer_tax_total)}</p>
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

        frm.reload_doc();
      });
    }, "RootedOps Payroll");

    frm.add_custom_button("Submit Draft Salary Slips", () => {
      frappe.call({
        method: "rootedops_payroll.api.payroll_entry_actions.submit_draft_salary_slips",
        args: { payroll_entry_name: frm.doc.name },
        freeze: true,
        freeze_message: "Submitting salary slips..."
      }).then((r) => {
        const data = r.message || {};
        const submitted = data.submitted_salary_slip_names || [];
        const alreadySubmitted = data.already_submitted_salary_slip_names || [];

        frappe.msgprint({
          title: "Salary Slips Submitted",
          wide: true,
          message: `
            <p><b>Employees:</b> ${data.employee_count || 0}</p>
            <p><b>Submitted Now:</b> ${submitted.length}</p>
            <p>${salarySlipLinks(submitted) || "None"}</p>
            <hr>
            <p><b>Already Submitted:</b> ${alreadySubmitted.length}</p>
            <p>${salarySlipLinks(alreadySubmitted) || "None"}</p>
        `
         });

        frm.reload_doc();
      });
    }, "RootedOps Payroll");

    frm.add_custom_button("Finalize Payroll (Safe)", async () => {
      const steps = [
        {
          label: "Submit Draft Salary Slips",
          method: "rootedops_payroll.api.payroll_entry_actions.submit_draft_salary_slips",
          freeze_message: "Submitting salary slips..."
        },
        {
          label: "Create Consolidated Draft JE",
          method: "rootedops_payroll.api.payroll_entry_actions.create_consolidated_draft_journal_entry",
          freeze_message: "Creating consolidated Journal Entry draft..."
        },
        {
          label: "Create Employee Payment Draft JE",
          method: "rootedops_payroll.api.payroll_entry_actions.create_employee_payment_draft_journal_entry",
          freeze_message: "Creating employee payment Journal Entry draft..."
        },
        {
          label: "Create Tax Reserve Transfer Draft JE",
          method: "rootedops_payroll.api.payroll_entry_actions.create_tax_reserve_transfer_draft_journal_entry",
          freeze_message: "Creating tax reserve transfer Journal Entry draft..."
        }
      ];

      const results = [];

      try {
        for (const step of steps) {
          const r = await frappe.call({
            method: step.method,
            args: { payroll_entry_name: frm.doc.name },
            freeze: true,
            freeze_message: step.freeze_message
          });

          results.push({
            label: step.label,
            data: r.message || {}
          });
        }

        const submitData = results.find(r => r.label === "Submit Draft Salary Slips")?.data || {};
        const consolidatedData = results.find(r => r.label === "Create Consolidated Draft JE")?.data || {};
        const paymentData = results.find(r => r.label === "Create Employee Payment Draft JE")?.data || {};
        const reserveData = results.find(r => r.label === "Create Tax Reserve Transfer Draft JE")?.data || {};

        const submitted = submitData.submitted_salary_slip_names || [];
        const alreadySubmitted = submitData.already_submitted_salary_slip_names || [];

        frappe.msgprint({
          title: "Payroll Finalized",
          wide: true,
          message: `
            <p><b>Employees:</b> ${submitData.employee_count || 0}</p>

            <hr>
            <p><b>Salary Slips Submitted Now:</b> ${submitted.length}</p>
            <p>${salarySlipLinks(submitted) || "None"}</p>

            <p><b>Salary Slips Already Submitted:</b> ${alreadySubmitted.length}</p>
            <p>${salarySlipLinks(alreadySubmitted) || "None"}</p>

            <hr>
            <p><b>Consolidated JE:</b> ${journalEntryLink(consolidatedData.journal_entry)}</p>
            <p><b>Employee Payment JE:</b> ${journalEntryLink(paymentData.journal_entry)}</p>
            <p><b>Tax Reserve Transfer JE:</b> ${journalEntryLink(reserveData.journal_entry)}</p>
          `
        });

        frm.reload_doc();
      } catch (e) {
        frappe.msgprint({
          title: "Finalize Payroll Stopped",
          indicator: "red",
          message: `
            <p>The payroll flow stopped before completion.</p>
            <p>Review the server error above, correct it, and rerun the remaining steps.</p>
          `
        });
        throw e;
      }
    }, "RootedOps Payroll");

    frm.add_custom_button("Create Consolidated Draft JE", () => {
      frappe.call({
        method: "rootedops_payroll.api.payroll_entry_actions.create_consolidated_draft_journal_entry",
        args: { payroll_entry_name: frm.doc.name },
        freeze: true,
        freeze_message: "Creating consolidated Journal Entry draft..."
      }).then((r) => {
        const data = r.message || {};
        frappe.msgprint({
          title: "Consolidated JE Draft Created",
          message: `
            <p><b>Journal Entry:</b> ${journalEntryLink(data.journal_entry)}</p>
          `
        });
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
