frappe.query_reports["Payroll Event Cost Report"] = {
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
      fieldname: "employee",
      label: __("Employee"),
      fieldtype: "Link",
      options: "Employee",
      reqd: 1,
      get_query: () => {
        const company = frappe.query_report.get_filter_value("company");
        return company ? { filters: { company } } : {};
      },
    },
    {
      fieldname: "window_start",
      label: __("Event Start"),
      fieldtype: "Datetime",
      reqd: 1,
    },
    {
      fieldname: "window_end",
      label: __("Event End"),
      fieldtype: "Datetime",
      reqd: 1,
    },
  ],
};
