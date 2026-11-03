-- READ ONLY: source-authoritative MushroomProcess gross versus reservation-adjusted availability.
-- Run on production MushroomProcess PostgreSQL with psql -X -v ON_ERROR_STOP=1.
-- No ERP stock-ledger transactions, no Woo writes and no inventory sync activation.
BEGIN READ ONLY;
WITH snapshot AS (
  SELECT c.ecommerce_id, c.erp_item_code, c.provider, c.site_key,
         c.external_sku, c.external_product_id, c.external_variation_id,
         c.available_from_products, c.available_from_lots,
         c.desired_quantity AS physical_quantity,
         n.available_quantity AS unreserved_quantity,
         c.desired_quantity - n.available_quantity AS reserved_effect
  FROM public.mp_ecommerce_catalog_inventory() c
  JOIN public.mp_commerce_inventory() n USING (ecommerce_id)
)
SELECT count(*) AS listings,
       count(*) FILTER (WHERE nullif(btrim(coalesce(erp_item_code,'')),'') IS NOT NULL) AS erp_linked,
       count(*) FILTER (WHERE provider='ecwid' AND site_key='dank_mushrooms') AS expected_ecwid,
       count(*) FILTER (WHERE unreserved_quantity >= 0 AND unreserved_quantity <= physical_quantity) AS valid_availability,
       sum(physical_quantity) AS physical_total,
       sum(unreserved_quantity) AS unreserved_total
FROM snapshot;
WITH snapshot AS (
  SELECT c.ecommerce_id, c.erp_item_code, c.provider, c.site_key,
         c.external_sku, c.external_product_id, c.external_variation_id,
         c.available_from_products, c.available_from_lots,
         c.desired_quantity AS physical_quantity,
         n.available_quantity AS unreserved_quantity,
         c.desired_quantity - n.available_quantity AS reserved_effect
  FROM public.mp_ecommerce_catalog_inventory() c
  JOIN public.mp_commerce_inventory() n USING (ecommerce_id)
)
SELECT ecommerce_id, erp_item_code, provider, site_key, external_sku, external_product_id,
       external_variation_id, available_from_products, available_from_lots,
       physical_quantity, unreserved_quantity, reserved_effect
FROM snapshot ORDER BY ecommerce_id;
ROLLBACK;
