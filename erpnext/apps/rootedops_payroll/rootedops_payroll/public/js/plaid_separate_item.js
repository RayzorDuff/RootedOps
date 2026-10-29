/* Separate Plaid Items, including multiple logins at one institution.
 * The existing ERPNext stock Link button remains unchanged. */
(() => {
  "use strict";
  let sdkPromise;
  function loadPlaid() {
    if (window.Plaid && window.Plaid.create) return Promise.resolve();
    if (sdkPromise) return sdkPromise;
    sdkPromise = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = "https://cdn.plaid.com/link/v2/stable/link-initialize.js";
      script.onload = () => window.Plaid ? resolve() : reject(new Error("Plaid SDK unavailable"));
      script.onerror = () => reject(new Error("Plaid SDK failed to load"));
      document.head.appendChild(script);
    });
    return sdkPromise;
  }

  frappe.ui.form.on("Plaid Settings", {
    refresh(frm) {
      frm.add_custom_button(__("Link Separate Plaid Item"), () => {
        const dialog = new frappe.ui.Dialog({
          title: __("Link Separate Plaid Item"),
          fields: [
            {fieldname:"profile_name", fieldtype:"Link", options:"RootedOps Plaid Connection Profile",
              label:__("Plaid Profile"), default:"legacy-current", reqd:1},
            {fieldname:"bank_name", fieldtype:"Link", options:"Bank",
              label:__("New / Unconnected Bank Record"), reqd:1,
              description:__("Use a distinct Bank record with no Plaid token. Existing Items will never be overwritten.")},
          ],
          primary_action_label: __("Authenticate New Connection"),
          primary_action: async (values) => {
            dialog.get_primary_btn().prop("disabled", true);
            try {
              await loadPlaid();
              const link = await frappe.call({
                method:"rootedops_payroll.api.plaid_link.create_profile_link_token",
                type:"POST",
                args:{profile_name:values.profile_name}
              });
              const token = link.message && link.message.link_token;
              if (!token) throw new Error("Plaid Link token was not returned");
              const handler = window.Plaid.create({
                token,
                onSuccess: async (public_token) => {
                  try {
                    const bound = await frappe.call({
                      method:"rootedops_payroll.api.plaid_link.bind_profile_item",
                      type:"POST",
                      args:{bank_name:values.bank_name, profile_name:values.profile_name, public_token}
                    });
                    const count = bound.message && bound.message.account_count;
                    frappe.msgprint(__("Plaid Item saved to Bank. {0} account(s) available for manual mapping. No Bank Accounts or transactions were imported.", [count]));
                    dialog.hide();
                    frm.reload_doc();
                  } catch(e) {
                    frappe.msgprint({title:__("Plaid Item not saved"), message: String(e.message || e), indicator:"red"});
                  } finally {
                    dialog.get_primary_btn().prop("disabled", false);
                  }
                },
                onExit: () => dialog.get_primary_btn().prop("disabled", false)
              });
              handler.open();
            } catch(e) {
              dialog.get_primary_btn().prop("disabled", false);
              frappe.msgprint({title:__("Plaid connection failed"), message:String(e.message || e), indicator:"red"});
            }
          }
        });
        dialog.show();
      }, __("Plaid"));
    }
  });
})();
