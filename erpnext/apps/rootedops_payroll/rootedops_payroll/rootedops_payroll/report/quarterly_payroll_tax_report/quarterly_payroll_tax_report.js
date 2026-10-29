frappe.query_reports["Quarterly Payroll Tax Report"] = {
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
    {
      fieldname: "salary_slip_status",
      label: __("Salary Slip Status"),
      fieldtype: "Select",
      options: ["Submitted", "Draft", "Draft and Submitted"],
      reqd: 1,
      default: "Submitted",
    },
  ],
};
