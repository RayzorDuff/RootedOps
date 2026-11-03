/* ERP Item form: canonical product content from Commercial Product Content.
 * This preview stores no duplicate Item fields and never publishes to Woo.
 */
frappe.ui.form.on("Item", {
  refresh(frm) {
    const wrapper = frm.fields_dict.rootedops_commerce_preview;
    if (frm.is_new() || !wrapper) return;
    const item = frm.doc.name;
    const esc = (value) => $("<div>").text(String(value == null ? "" : value)).html();
    wrapper.$wrapper.empty().text(__("Loading commerce content…"));
    frappe.call({
      method: "rootedops_commerce.item_editorial.get_item_editorial",
      args: { item: item },
      callback(response) {
        if (frm.doc.name !== item) return;
        const d = response.message;
        if (!d) {
          wrapper.$wrapper.text(__("Commerce content unavailable"));
          return;
        }
        const fields = d.fields;
        const sections = [
          [__("Public title"), fields.public_title],
          [__("Short description"), fields.short_description],
          [__("Full description"), fields.full_description],
          [__("SEO title"), fields.seo_title],
          [__("SEO description"), fields.seo_description]
        ];
        let html = '<div class="rootedops-commerce-content">';
        html += '<p><strong>' + esc(__("Publication status")) + ':</strong> '
              + esc(d.publication_status) + ' — ' + esc(__("Editing does not publish to WooCommerce")) + '</p>';
        sections.forEach(([label, value]) => {
          html += '<p><strong>' + esc(label) + '</strong></p>';
          html += '<div style="white-space:pre-wrap;margin-bottom:12px">' + esc(value) + '</div>';
        });
        html += '<p><strong>' + esc(__("Gallery / alt text")) + ' (' + d.gallery.length + ')</strong></p>';
        d.gallery.forEach((row) => {
          html += '<p>' + esc(row.image) + ' — ' + esc(row.alt_text) + '</p>';
        });
        html += '<p><strong>' + esc(__("Channel overrides")) + ' (' + d.channel_overrides.length + ')</strong></p>';
        d.channel_overrides.forEach((row) => {
          html += '<p>' + esc(row.provider) + ' / ' + esc(row.site_key) + ': ' +
                  esc(row.title) + '</p>';
        });
        html += '<p><strong>' + esc(__("Source key")) + ':</strong> ' + esc(d.source_key) + '</p>';
        html += '<p class="text-muted">' +
          esc(__("Use Open Full Commerce Record to edit galleries, per-channel overrides, and publication status. " +
                 "Storefront synchronization remains a separate reviewed operation.")) +
          '</p></div>';
        wrapper.$wrapper.html(html);
        frm.add_custom_button(__("Open Full Commerce Record"), () => {
          frappe.set_route("Form", "Commercial Product Content", item);
        }, __("Commerce"));

        if (d.can_write) {
          frm.add_custom_button(__("Edit Commerce Content"), () => {
            const dialog = new frappe.ui.Dialog({
              title: __("Edit authoritative product content"),
              fields: [
                { fieldname: "public_title", label: __("Public title"), fieldtype: "Data",
                  reqd: 1, default: fields.public_title },
                { fieldname: "short_description", label: __("Short description"),
                  fieldtype: "Small Text", default: fields.short_description },
                { fieldname: "full_description", label: __("Full description"),
                  fieldtype: "Text Editor", default: fields.full_description },
                { fieldname: "seo_title", label: __("SEO title"),
                  fieldtype: "Data", default: fields.seo_title },
                { fieldname: "seo_description", label: __("SEO description"),
                  fieldtype: "Small Text", default: fields.seo_description }
              ],
              primary_action_label: __("Save in ERPNext")
            });
            dialog.set_primary_action(__("Save in ERPNext"), async () => {
              const values = dialog.get_values();
              if (!values) return;
              dialog.get_primary_btn().prop("disabled", true);
              try {
                await frappe.call({
                  method: "rootedops_commerce.item_editorial.save_item_editorial",
                  args: { item: item, expected_modified: d.modified, values: values }
                });
                dialog.hide();
                await frm.reload_doc();
                frappe.show_alert({ message: __("ERPNext content saved. WooCommerce was not changed."),
                                    indicator: "green" });
              } finally {
                dialog.get_primary_btn().prop("disabled", false);
              }
            });
            dialog.show();
          }, __("Commerce"));
        }
      },
      error() {
        wrapper.$wrapper.text(__("Could not load commerce content. Check permissions or app migration."));
      }
    });
  }
});
