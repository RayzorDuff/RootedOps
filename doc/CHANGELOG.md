# Changelog

All notable changes to this project will be documented in this file.

---

## [1.3.0] - 2026-09-24

### Added

- Derived employee payroll-payment lifecycle states for each Salary Slip: Not Recorded, Draft, Submitted, Cancelled, and conflict detection for multiple active JEs.
- Stable logical Salary Slip payment identity plus sequential, unique payment-attempt keys so cancelled JEs remain auditable while replacements can be generated safely.
- Payroll Entry **Review Employee Payment Status** action showing current/last payment JE and attempt count.
- Migration backfill for Phase-2 employee-payment JEs to populate logical-key and attempt metadata without changing accounting entries.

### Changed

- Employee-payment generation now allows regeneration only when prior payment attempts are cancelled (or absent); draft/submitted JEs continue to block duplicates.
- Cancelled legacy consolidated employee-payment JEs no longer block prospective employee-specific settlement, while active legacy payment JEs still do.
- `rootedops_payroll` version advanced to `0.2.0`.

### Notes

- Payroll accrual, withholding-reserve transfers, and tax-remittance behavior are unchanged.
- Phase 3 does not execute payments or generate NACHA files.

---

## [1.2.1] - 2026-09-24

### Fixed

- Made the shared `erpnext_apps` volume available read-only to `erpnext-frontend` so nginx can serve custom RootedOps app public files from the same deployed source used by the backend.
- Made `erpnext-configurator` create the `sites/assets/rootedops_payroll` symlink on every configuration run, eliminating container-local frontend copies and avoiding an unnecessary `bench build` requirement for `doctype_js` changes.

### Deployment

- Custom `rootedops_payroll` Python/public-file updates should be copied into the shared apps volume, followed by `bench migrate`, `clear-cache`, and service restart/recreation as appropriate.
- `bench build --app rootedops_payroll` is not required for the current raw `doctype_js` asset and the runtime backend image does not include the Node build toolchain.

---

## [1.2.0] - 2026-09-24

### Added

- Employee payroll-payment method configuration and structured payment linkage metadata for RootedOps payroll.
- Employee-specific payroll payment draft Journal Entries tied to Employee, Salary Slip, Payroll Entry, payment method, and a stable full-net-pay payment key.
- Batch preflight validation for submitted Salary Slips, effective employee payment configuration, account resolution, and duplicate-payment prevention.

### Changed

- Payroll Entry employee-payment settlement now creates one draft Bank Entry Journal Entry per employee/Salary Slip instead of one consolidated employee-payment Journal Entry.
- RootedOps payroll app version advanced to `0.1.0` for the Issue #8 phased implementation.

### Notes

- Payroll accrual, withholding-reserve transfer, and tax-remittance accounting remain unchanged and consolidated where appropriate.
- Existing historical consolidated employee-payment Journal Entries are not migrated or rewritten.
- Payment execution, cancellation/amendment lifecycle handling, and ACH/NACHA generation remain later phases.

---

## [1.1.0] - 2026-08-13

### Added

- ERPNext quarterly payroll-tax reporting and liability reconciliation.
- Colorado FAMLI, wage-withholding, and unemployment-insurance breakdowns, including employer UI accrual.
- Payroll treasury projections, links to existing tax-payment journal entries, and tax-filing confirmation tracking.
- Listmonk service configuration for newsletters and member communications.
- Stable MushroomProcess QR resolver exposure and Product destination configuration.
- Minecraft-aware backup/restore support and corrected Google Drive retention pruning.
- Canonical release metadata, versioned release notes, and repeatable preparation/validation commands.

### Changed

- Improved Appsmith reverse-proxy performance configuration.
- Kept Minecraft operational detail in `README_MINECRAFT.md` so the primary README remains focused on business infrastructure.
- Established this release as the pre-integration baseline before ERPNext becomes authoritative for vendor purchases and purchased inventory.

### Fixed

- Completed zero-dollar payroll without creating unnecessary journal entries.
- Corrected payroll UI placement for Colorado tax fields.

### Notes

- ERPNext purchasing/inventory authority and the new SignatureGate/MushroomProcess integration endpoints remain future work.
- Coordinated with MushroomProcess `v1.2.0`, SignatureGate `v1.1.0`, and BookWorks `bookworks-v3.3.0`.

---

## [1.0.0] - 2026-04-22

### 🎉 Initial Release

This is the first stable release of RootedOps, establishing a unified operational platform integrating:

- PostgreSQL-based data layer
- NocoDB for data access and API abstraction
- Appsmith for operational interfaces
- n8n for workflow automation
- Supporting services (print daemon, document management, etc.)

This release aligns with:
- MushroomProcess v1.0.8-beta
- SignatureGate v1.0.2

---

### 🧱 Core Architecture

- Established Docker-based multi-service environment
- Integrated services:
  - PostgreSQL database
  - NocoDB API layer
  - Appsmith UI platform
  - n8n automation engine
  - Supporting microservices (print daemon, document handling)
- Centralized `.env` configuration pattern
- Volume mapping and persistent storage structure defined

---

### 🗄️ Database & Schema

- Implemented PostgreSQL schema replacing Airtable backend
- Migrated core entities:
  - Items
  - Lots
  - Recipes
  - Events
  - Products
  - Personnel-related structures
- Introduced category-based item system (e.g., grain, substrate, LC, agar, plate)
- Added support for:
  - Agar plates and agar flasks
  - Volume-based vs weight-based product handling
- Established schema under `nocodb_schema/pgsql`

---

### 🔄 Airtable Migration (In Progress)

- Exported Airtable schema and data for migration
- Created mapping structures between Airtable and PostgreSQL
- Began transition away from Airtable automations
- Identified remaining dependencies:
  - Airtable automations
  - Airtable views for print workflows

---

### 🧩 Appsmith Interfaces

- Implemented initial operational UI:
  - Lot-centric workflows
  - Production tracking interfaces
  - Personnel and review pages
  - Fulfillment interface (early version)
- Defined direction:
  - Transition from Airtable-style views → purpose-built operational UI
  - Shift toward station-based and workflow-based interfaces

---

### ⚙️ Automation (n8n)

- Implemented workflows for:
  - Bank transaction ingestion
  - ERPNext integration
  - Event-driven processing
- Added duplicate detection and transaction validation logic
- Introduced preview/debug outputs for workflow visibility

---

### 🖨️ Print System

- Implemented print daemon architecture
- Designed for:
  - Multiple instances per environment
  - Printer-specific routing
  - Airtable (temporary) and future NocoDB integration
- Added groundwork for:
  - Label printing (Zebra GK420t)
  - Sterilization sheets
- Planned improvements:
  - Locking
  - Logging levels
  - Queue filtering

---

### 🧪 Production System Enhancements

- Added agar workflow support:
  - Plate creation and tracking
  - Master vs working plates
  - Integration into inoculation workflows
- Improved product generation logic:
  - Volume-based items (LC, agar) handled separately from weight-based
  - Corrected unit conversions

---

### 📦 Fulfillment & Inventory

- Introduced fulfillment workflows via Appsmith
- Enabled product creation from lots
- Linked production outputs to inventory system
- Began testing with imported Airtable datasets

---

### 📚 Documentation

- Added and updated:
  - README files across services
  - Schema documentation
  - Migration notes
- Defined project structure:
  - `nocodb_schema/`
  - `nocodb_interfaces/`
  - `n8n/workflows/`
  - `airtable_schema/`
  - `screenshots/`

---

### 🚧 Known Gaps / Work in Progress

- Airtable still partially in use for:
  - Automations
  - Print queue sourcing
- Appsmith interfaces incomplete in some workflows
- Full production migration not yet finalized
- Some schema refinements ongoing
- Logging and observability improvements pending

---

### 🔜 Next Steps

- Complete Airtable decommissioning
- Finalize Appsmith operational interfaces
- Migrate print daemon fully to NocoDB
- Expand automation coverage in n8n
- Harden deployment and monitoring
