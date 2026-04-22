# Changelog

All notable changes to this project will be documented in this file.

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
