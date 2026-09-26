## [1.4.6] - 2026-09-26

### Added

- Issue #7 Plaid Connection Profile foundation for generic profile identity, Plaid environment, protected credential references, server-side credential resolution, safe status inspection, and validation.

### Changed

- `rootedops_payroll` version advanced to `0.3.6`.
- Removed the obsolete legacy Payroll Entry employee-payment draft-JE client action; the maintained plural RootedOps action remains authoritative.

### Notes

- This is an Issue #7 development phase, so it uses a patch version and is not tagged.
- Existing Plaid Items, access tokens, transaction cursors, Bank Accounts, Bank Transactions, and synchronization behavior are unchanged in this phase.

---

## [1.4.5] - 2026-09-25

### Added

- Issue #6 Phase E validated NACHA payroll export with audit metadata, synthetic-data tests, and Payroll Entry download workflow.
- NACHA export records capture non-sensitive payroll/export metadata and SHA-256 file identity without retaining raw bank-account data.

### Notes

- Phase E supports only confirmed **Unbalanced** profiles; balanced/offset exports remain intentionally unsupported until bank requirements are confirmed.
- The generated file is a test/production-mode artifact determined by the profile certification status; no bank transmission is performed.

# Changelog

All notable changes to this project will be documented in this file.

---

## [1.4.4] - 2026-09-25

### Added

- Issue #6 Phase D read-only payroll-to-NACHA pre-export planning and validation.
- Submitted Payroll Entry/Salary Slip resolution, ACH/non-ACH separation, cent-accurate ACH reconciliation, secure ACH credential use, masked review data, and Phase C formatter integration.
- Payroll Entry UI action for reviewing an ACH export plan without generating, downloading, or persisting a NACHA file.
- Synthetic regression coverage for mixed payment methods, duplicate employees, formatter reconciliation, sensitive-data exclusion, and deferred balanced-file support.

### Changed

- RootedOps version advanced to 1.4.4.
- `rootedops_payroll` version advanced to `0.3.4`.

### Notes

- This is an Issue #6 development phase and is not a production ACH export release.
- Bank certification, production file generation/download, audit persistence, balanced/offset handling, and bank-specific effective-date rules remain deferred.

---

## [1.4.3] - 2026-09-25

### Added

- Issue #6 ACH Phase C pure NACHA PPD formatter and structural validator using synthetic/export-ready data.
- Fixed-width 94-character NACHA records, ten-record blocking, payroll PPD entries, checking/savings transaction codes, Entry Hash, batch/file controls, trace numbers, and deterministic validation.
- Synthetic regression coverage for checking, savings, routing validation, duplicate traces, record width, blocking, hashes, and payroll totals.

### Changed

- `rootedops_payroll` version advanced to `0.3.3`.

### Notes

- This is an Issue #6 development phase, so it uses a patch version and is not tagged.
- Payroll Entry integration, production export workflow, bank certification, and bank-specific balanced/offset funding remain outside this phase.

---

## [1.4.2] - 2026-09-25

### Added

- Issue #6 ACH Phase B `RootedOps NACHA Profile` for bank/origination values not already owned by ERPNext.
- Derived NACHA identity from ERPNext Company: uppercase company name, 16-character Batch Header projection, and High Plains Company ID `1 + Company.tax_id` EIN digits.
- Profile readiness validation for funding Bank Account, Immediate Destination/Origin, destination/origin names, ODFI Identification, and confirmed balanced/unbalanced behavior.
- Explicit configuration/certification states so incomplete High Plains parameters can be recorded without inventing values or enabling production use.
- Regression coverage for EIN normalization, company-name projection, Company ID derivation, and profile readiness.

### Changed

- `rootedops_payroll` version advanced to `0.3.2`.

### Notes

- This is an Issue #6 development phase, so it uses a patch version and is not tagged.
- No NACHA file generation or payroll accounting change is included in this phase.

---

## [1.4.1] - 2026-09-24

### Added

- Issue #6 ACH Phase A employee direct-deposit configuration using Frappe `Password` fields for routing/account numbers.
- Checking/savings selection, bank/account-holder metadata, ACH authorization status/effective date, masking helpers, ABA routing validation, and NACHA account-number validation.
- Server-side internal ACH credential retrieval for later NACHA export while ordinary configuration reads remain masked.
- Issue #6 documentation recording ERPNext Company `tax_id` as the EIN source of truth and High Plains Bank's `DANK MUSHROOMS LLC` / `1 + EIN` requirements.

### Changed

- `rootedops_payroll` version advanced to `0.3.1`.

### Notes

- This is an Issue #6 development phase, so it uses a patch version and is not tagged.
- Payroll accounting and Issue #8 settlement behavior are unchanged. No NACHA file is generated yet.

---

## [1.4.0] - 2026-09-24

### Completed

- Resolved Issue #8: employee net-pay settlement is now represented by one employee-specific Journal Entry per submitted positive-net-pay Salary Slip instead of a consolidated employee-payment Journal Entry.
- Finalized payment-method configuration, structured Employee/Salary Slip/Payroll Entry traceability, lifecycle/idempotency, cancelled-attempt regeneration, conflict detection, and employee-level reconciliation visibility.
- Documented the final accounting boundary and operational workflow in `doc/ISSUE_8_EMPLOYEE_PAYMENT_SETTLEMENT.md`.

### Added

- Explicit regression coverage for single-employee payroll behavior and zero-net-pay Salary Slips, in addition to the existing multi-employee/mixed-method, lifecycle, and accounting consistency coverage.
- Issue #6 handoff guidance that uses ERPNext Company `tax_id` as the authoritative EIN source rather than duplicating EIN configuration in RootedOps.

### Changed

- `rootedops_payroll` version advanced to `0.3.0` for the completed Issue #8 milestone.

### Notes

- This is a minor, tagged milestone because Issue #8 is complete.
- ACH/NACHA file generation remains Issue #6 and will build on the employee-specific payment model without changing its accounting boundary.

---

## [1.3.1] - 2026-09-24

### Added

- Live employee-payment settlement table directly on Payroll Entry, including payment method, Salary Slip, current/last JE, lifecycle state, attempt count, and accounting verification.
- Batch settlement summary showing expected net pay, draft/submitted payment totals, and outstanding net pay.
- Accounting-consistency validation that checks employee-specific payment JEs against Salary Slip net pay, Employee-party Payroll Payable debit, checking-account credit, company, Salary Slip, and Payroll Entry linkage.
- Regression coverage for correct payment accounting, amount mismatches, wrong employee-party attribution, and payroll-level settlement totals.

### Changed

- Newly created employee-payment JEs are verified against their actual accounting rows before the request can commit.
- Payment-status review now surfaces accounting mismatches and active-JE conflicts instead of treating every linked JE as valid settlement accounting.
- `rootedops_payroll` version advanced to `0.2.1`.

### Notes

- This remains Issue #8 development work, so it uses a patch version and is not tagged. A minor/tagged release should be created only after Issue #8 is verified and closed.
- Payment execution and ACH/NACHA generation remain outside Issue #8.

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
