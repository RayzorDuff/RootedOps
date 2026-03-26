frappe.ui.form.on("Payroll Entry", {
  refresh(frm) {
    if (frm.is_new()) return;

    frm.add_custom_button("Preview Attendance Payroll", () => {
      frappe.call({
        method: "rootedops_payroll.api.payroll_entry_actions.preview_attendance_payroll",
        args: {
          payroll_entry_name: frm.doc.name
        },
        freeze: true,
        freeze_message: "Previewing attendance payroll..."
      }).then((r) => {
        const data = r.message || {};
        const summary = data.summary || {};
        const liability = summary.consolidated_liability_summary || {};
        const je_preview = summary.consolidated_journal_entry_preview || {};

        frappe.msgprint({
          title: "Attendance Payroll Preview",
          message: `
            <p><b>Employees:</b> ${summary.employee_count || 0}</p>
            <p><b>Gross Wages:</b> ${liability.gross_wages || 0}</p>
            <p><b>Net Pay:</b> ${liability.net_pay || 0}</p>
            <p><b>Employee Taxes:</b> ${liability.employee_tax_total || 0}</p>
            <p><b>Employer Taxes:</b> ${liability.employer_tax_total || 0}</p>
            <p><b>Total Payroll Expense:</b> ${liability.total_payroll_expense || 0}</p>
            <p><b>JE Balanced:</b> ${je_preview.is_balanced ? "Yes" : "No"}</p>
          `
        });

        console.log("Payroll preview", data);
      });
    }, "RootedOps Payroll");

    frm.add_custom_button("Create / Refresh Draft Salary Slips", () => {
      frappe.call({
        method: "rootedops_payroll.api.payroll_entry_actions.create_or_refresh_draft_salary_slips",
        args: {
          payroll_entry_name: frm.doc.name
        },
        freeze: true,
        freeze_message: "Creating or refreshing salary slips..."
      }).then((r) => {
        const data = r.message || {};
        const slips = data.salary_slip_names || [];

        frappe.msgprint({
          title: "Draft Salary Slips Created",
          message: `
            <p><b>Employees:</b> ${data.employee_count || 0}</p>
            <p><b>Salary Slips:</b> ${slips.length}</p>
            <p>${slips.join("<br>")}</p>
          `
        });

        console.log("Salary slips result", data);
      });
    }, "RootedOps Payroll");

    frm.add_custom_button("Create Consolidated Draft JE", () => {
      frappe.call({
        method: "rootedops_payroll.api.payroll_entry_actions.create_consolidated_draft_journal_entry",
        args: {
          payroll_entry_name: frm.doc.name
        },
        freeze: true,
        freeze_message: "Creating consolidated Journal Entry draft..."
      }).then((r) => {
        const data = r.message || {};

        frappe.msgprint({
          title: "Consolidated JE Draft Created",
          message: `
            <p><b>Journal Entry:</b> ${data.journal_entry || "None"}</p>
          `
        });

        console.log("JE draft result", data);
      });
    }, "RootedOps Payroll");
  }
});
