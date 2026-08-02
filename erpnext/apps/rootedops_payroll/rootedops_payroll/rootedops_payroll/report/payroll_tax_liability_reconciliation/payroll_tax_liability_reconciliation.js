frappe.query_reports["Payroll Tax Liability Reconciliation"] = {
  formatter(value, row, column, data, default_formatter) {
    if (["draft_entries", "submitted_entries"].includes(column.fieldname) && value) {
      return value.split(", ").map((name) => {
        const escaped = frappe.utils.escape_html(name);
        return `<a href="/app/journal-entry/${encodeURIComponent(name)}">${escaped}</a>`;
      }).join(", ");
    }
    if (column.fieldname === "confirmation_attachment" && value) {
      const escaped = frappe.utils.escape_html(value);
      return `<a href="${escaped}" target="_blank" rel="noopener">${__("Open")}</a>`;
    }

    const formatted = default_formatter(value, row, column, data);
    if (column.fieldname === "projected_outstanding" && Number(value) < 0) {
      return `<span class="text-danger">${formatted}</span>`;
    }
    return formatted;
  },

  filters: [
    {
      fieldname: "company",
      label: __("Company"),
      fieldtype: "Link",
      options: "Company",
      reqd: 1,
      default: frappe.defaults.get_user_default("Company"),
    },
    {
      fieldname: "year",
      label: __("Year"),
      fieldtype: "Int",
      reqd: 1,
      default: new Date().getFullYear(),
    },
    {
      fieldname: "quarter",
      label: __("Quarter"),
      fieldtype: "Select",
      options: ["Q1", "Q2", "Q3", "Q4"],
      reqd: 1,
      default: `Q${Math.floor(new Date().getMonth() / 3) + 1}`,
    },
  ],

  onload(report) {
    report.page.add_inner_button(__("Record Filing Confirmation"), () => {
      const filters = report.get_values();
      const dialog = new frappe.ui.Dialog({
        title: __("Record Tax Filing Confirmation"),
        fields: [
          {
            fieldname: "tax_type", label: __("Tax Type"), fieldtype: "Select",
            options: ["Federal Payroll Tax", "Colorado Withholding", "Colorado UI", "Colorado FAMLI"], reqd: 1,
          },
          {
            fieldname: "journal_entry", label: __("Linked Journal Entry"), fieldtype: "Link",
            options: "Journal Entry", reqd: 1,
            get_query: () => ({filters: {
              company: filters.company,
              rootedops_tax_year: filters.year,
              rootedops_tax_quarter: filters.quarter,
              docstatus: ["in", [0, 1]],
            }}),
          },
          {
            fieldname: "filing_status", label: __("Filing Status"), fieldtype: "Select",
            options: ["Not Filed", "Filed", "Accepted"], default: "Accepted", reqd: 1,
          },
          {fieldname: "filing_date", label: __("Filing Date"), fieldtype: "Date", default: frappe.datetime.get_today()},
          {fieldname: "confirmation_number", label: __("Confirmation Number"), fieldtype: "Data"},
          {fieldname: "confirmation_attachment", label: __("Confirmation Attachment"), fieldtype: "Attach"},
        ],
        primary_action_label: __("Save Confirmation"),
        primary_action(values) {
          frappe.call({
            method: "rootedops_payroll.services.tax_compliance.record_tax_filing_confirmation",
            args: {...filters, ...values},
            freeze: true,
            freeze_message: __("Saving filing confirmation..."),
            callback(response) {
              if (!response.message) return;
              dialog.hide();
              frappe.show_alert({
                message: __("Recorded {0} status for {1}", [response.message.filing_status, response.message.journal_entry]),
                indicator: "green",
              });
              report.refresh();
            },
          });
        },
      });
      dialog.show();
    }, __("Actions"));

    report.page.add_inner_button(__("Link Existing Payment"), () => {
      const filters = report.get_values();
      const dialog = new frappe.ui.Dialog({
        title: __("Link Existing Tax Payment"),
        fields: [
          {
            fieldname: "journal_entry",
            label: __("Journal Entry"),
            fieldtype: "Link",
            options: "Journal Entry",
            reqd: 1,
            get_query: () => ({filters: {company: filters.company, docstatus: ["in", [0, 1]]}}),
          },
          {
            fieldname: "tax_type",
            label: __("Tax Type"),
            fieldtype: "Select",
            options: ["Federal Payroll Tax", "Colorado Withholding", "Colorado UI", "Colorado FAMLI"],
            reqd: 1,
          },
        ],
        primary_action_label: __("Link Payment"),
        primary_action(values) {
          frappe.call({
            method: "rootedops_payroll.services.tax_compliance.link_existing_tax_payment",
            args: {...filters, ...values},
            freeze: true,
            freeze_message: __("Linking payment Journal Entry..."),
            callback(response) {
              if (!response.message) return;
              dialog.hide();
              frappe.show_alert({
                message: __("Linked {0} as a {1} tax payment", [
                  response.message.journal_entry,
                  response.message.status,
                ]),
                indicator: "green",
              });
              report.refresh();
            },
          });
        },
      });
      dialog.show();
    }, __("Actions"));

    report.page.add_inner_button(__("Create Tax Payment Draft"), () => {
      const filters = report.get_values();
      const dialog = new frappe.ui.Dialog({
        title: __("Create Tax Payment Draft"),
        fields: [
          {
            fieldname: "tax_type",
            label: __("Tax Type"),
            fieldtype: "Select",
            options: ["Federal Payroll Tax", "Colorado Withholding", "Colorado UI", "Colorado FAMLI"],
            reqd: 1,
          },
          {fieldname: "posting_date", label: __("Payment Date"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1},
          {fieldname: "reference_no", label: __("Payment Reference"), fieldtype: "Data", reqd: 1},
        ],
        primary_action_label: __("Create Draft"),
        primary_action(values) {
          frappe.call({
            method: "rootedops_payroll.services.tax_compliance.create_tax_payment_draft",
            args: {...filters, ...values},
            freeze: true,
            freeze_message: __("Creating payment Journal Entry..."),
            callback(response) {
              if (!response.message) return;
              dialog.hide();
              frappe.set_route("Form", "Journal Entry", response.message.journal_entry);
            },
          });
        },
      });
      dialog.show();
    }, __("Actions"));
  },
};
