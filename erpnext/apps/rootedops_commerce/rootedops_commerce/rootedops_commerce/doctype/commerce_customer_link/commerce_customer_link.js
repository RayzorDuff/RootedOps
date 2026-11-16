frappe.ui.form.on("Commerce Customer Link", {
  refresh(frm) {
    if (frm.is_new() || frm.doc.customer ||
        frm.doc.account_status !== "review_erp_email_match" ||
        !frappe.user.has_role("System Manager")) return;

    frm.add_custom_button(__("Link to Existing Customer"), async () => {
      const name = frm.doc.name;
      const { message: account } = await frappe.call({
        method: "rootedops_commerce.customer_sync.get_signup_review",
        type: "GET",
        args: { name }
      });
      if (frm.doc.name !== name || !account) return;

      const dialog = new frappe.ui.Dialog({
        title: __("Link to Existing Customer"),
        fields: [
          { fieldtype: "HTML", fieldname: "woo_account" },
          { fieldtype: "Link", fieldname: "customer", label: __("ERP Customer"), options: "Customer", reqd: 1 },
          { fieldtype: "Link", fieldname: "contact", label: __("ERP Contact"), options: "Contact", reqd: 1 },
          { fieldtype: "Link", fieldname: "billing_address", label: __("ERP Billing Address"), options: "Address" },
          { fieldtype: "Link", fieldname: "shipping_address", label: __("ERP Shipping Address"), options: "Address" }
        ],
        primary_action_label: __("Approve Link"),
        async primary_action(values) {
          await frappe.call({
            method: "rootedops_commerce.customer_sync.approve_signup_review",
            args: { name, ...values },
            freeze: true,
            btn: dialog.get_primary_btn()
          });
          dialog.hide();
          if (frm.doc.name === name) await frm.reload_doc();
        }
      });
      const accountName = [account.first_name, account.last_name].filter(Boolean).join(" ");
      dialog.fields_dict.woo_account.$wrapper
        .empty()
        .append($("<p>").text([accountName, account.email].filter(Boolean).join(" — ")))
        .append($("<p>").text(__("Choose the Contact dedicated to this Customer. The Woo and ERP profiles must agree.")));
      dialog.show();
    });
  }
});
