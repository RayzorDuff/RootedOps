-- Snapshot 24 accepted operational availability rows, read-only.
-- psql -X -v ON_ERROR_STOP=1 -At -F ',' -f is NOT safe CSV quoting; use \copy.
-- Outputs CSV only to stdout (no BEGIN/ROLLBACK banners); SELECT is read only.
\set ON_ERROR_STOP on
\copy (SELECT c.ecommerce_id, c.erp_item_code, c.external_sku, c.external_product_id, c.external_variation_id, c.provider, c.site_key, c.desired_quantity AS physical_quantity, n.available_quantity AS projected_quantity FROM public.mp_ecommerce_catalog_inventory() c JOIN public.mp_commerce_inventory() n USING(ecommerce_id) ORDER BY c.ecommerce_id) TO STDOUT WITH (FORMAT csv, HEADER true)
