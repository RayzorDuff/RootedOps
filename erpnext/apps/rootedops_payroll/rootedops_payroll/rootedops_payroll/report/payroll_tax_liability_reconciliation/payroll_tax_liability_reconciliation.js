frappe.query_reports["Payroll Tax Liability Reconciliation"] = {
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
    });
  },
};
