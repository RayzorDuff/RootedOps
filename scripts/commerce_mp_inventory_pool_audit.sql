-- Read-only inventory pool/alias audit for the accepted 24 MP<->ERP mappings.
-- Physical and available quantity totals across ecommerce listings are NOT
-- necessarily unique stock; shared item_id/strain_id pools can double count.
-- No production writes, Woo projection, ERP stock moves or sync activation.
BEGIN READ ONLY;

-- Listing-level coverage, pool counts, and potential duplicate availability.
WITH listing AS (
  SELECT c.ecommerce_id, c.erp_item_code, c.item_id, c.strain_id,
         c.external_sku, c.provider, c.site_key,
         c.desired_quantity AS physical_quantity,
         a.available_quantity AS unreserved_quantity
  FROM public.mp_ecommerce_catalog_inventory() c
  JOIN public.mp_commerce_inventory() a USING(ecommerce_id)
),
pool AS (
  SELECT item_id, strain_id,
         count(*) AS listings,
         array_agg(ecommerce_id ORDER BY ecommerce_id) AS ecommerce_ids,
         array_agg(external_sku ORDER BY ecommerce_id) AS skus,
         sum(physical_quantity) AS summed_listing_physical,
         sum(unreserved_quantity) AS summed_listing_available,
         min(physical_quantity) AS min_listing_physical,
         max(physical_quantity) AS max_listing_physical
  FROM listing
  GROUP BY item_id, strain_id
)
SELECT count(*) AS physical_pools,
       sum(listings) AS mapped_listings,
       count(*) FILTER (WHERE listings>1) AS shared_pools,
       coalesce(sum(listings-1),0) AS extra_listing_aliases,
       sum(summed_listing_physical) AS listing_physical_total_not_distinct,
       sum(summed_listing_available) AS listing_available_total_not_distinct
FROM pool;

-- Any output here MUST be reviewed before Woo quantity publication.
WITH listing AS (
  SELECT c.ecommerce_id, c.erp_item_code, c.item_id, c.strain_id,
         c.external_sku, c.provider, c.site_key,
         c.desired_quantity AS physical_quantity,
         a.available_quantity AS unreserved_quantity
  FROM public.mp_ecommerce_catalog_inventory() c
  JOIN public.mp_commerce_inventory() a USING(ecommerce_id)
)
SELECT item_id, strain_id,
       count(*) AS listings_sharing_pool,
       array_agg(ecommerce_id ORDER BY ecommerce_id) AS ecommerce_ids,
       array_agg(external_sku ORDER BY ecommerce_id) AS skus,
       array_agg(physical_quantity ORDER BY ecommerce_id) AS physical_by_listing,
       array_agg(unreserved_quantity ORDER BY ecommerce_id) AS available_by_listing
FROM listing
GROUP BY item_id, strain_id
HAVING count(*)>1
ORDER BY listings_sharing_pool DESC, item_id, strain_id;

-- Sanity checks for each approved source listing, without exporting private lots.
WITH listing AS (
  SELECT c.ecommerce_id, c.erp_item_code, c.item_id, c.strain_id,
         c.provider, c.site_key, c.external_sku,
         c.desired_quantity AS physical_quantity,
         a.available_quantity AS unreserved_quantity
  FROM public.mp_ecommerce_catalog_inventory() c
  JOIN public.mp_commerce_inventory() a USING(ecommerce_id)
)
SELECT ecommerce_id, erp_item_code, external_sku, item_id, strain_id,
       physical_quantity, unreserved_quantity
FROM listing
WHERE erp_item_code IS NULL OR btrim(erp_item_code)=''
   OR provider<>'ecwid' OR site_key<>'dank_mushrooms'
   OR physical_quantity<0
   OR unreserved_quantity<0
   OR unreserved_quantity>physical_quantity
ORDER BY ecommerce_id;

ROLLBACK;
