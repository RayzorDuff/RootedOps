-- Dedicated integration DB schema. No operational or accounting mutations.
BEGIN;
CREATE TABLE IF NOT EXISTS commerce_inbox (
  provider text NOT NULL, site_key text NOT NULL, event_id text NOT NULL,
  external_order_id text NOT NULL, revision bigint NOT NULL,
  payload jsonb NOT NULL, raw_body bytea NOT NULL, received_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(provider,site_key,event_id)
);
CREATE TABLE IF NOT EXISTS commerce_delivery (
  provider text NOT NULL, site_key text NOT NULL, event_id text NOT NULL,
  state text NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','leased','done','dead')),
  attempts integer NOT NULL DEFAULT 0, next_attempt_at timestamptz NOT NULL DEFAULT now(),
  lease_token text, lease_until timestamptz, last_error text,
  mp_receipt jsonb, erp_receipt jsonb,
  PRIMARY KEY(provider,site_key,event_id),
  FOREIGN KEY(provider,site_key,event_id) REFERENCES commerce_inbox(provider,site_key,event_id)
);
CREATE INDEX IF NOT EXISTS commerce_delivery_ready ON commerce_delivery(state,next_attempt_at);
COMMIT;
