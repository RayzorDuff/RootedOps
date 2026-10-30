app_name = "rootedops_commerce"
app_title = "RootedOps Commerce"
app_publisher = "Dank Mushrooms, LLC"
app_description = "Commercial catalog and external channel integration"
app_email = "sales@danks.net"
app_license = "gpl-3.0"
required_apps = ["erpnext"]

doc_events = {
    'Sales Order': {'before_submit': 'rootedops_commerce.order_service.protect_order_submission'},
    'Sales Invoice': {'before_submit': 'rootedops_commerce.order_service.protect_invoice_submission'},
}
