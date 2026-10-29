# RootedOps v1.1.0

Release date: 2026-08-13

## Summary

This release establishes the shared infrastructure, ERPNext payroll, and QR-routing baseline for the concurrent Rooted software release. It precedes the planned change that will make ERPNext authoritative for vendor purchasing and purchased inventory and will route SignatureGate and MushroomProcess integrations through RootedOps-managed services.

## Highlights

- Added quarterly payroll-tax reporting and liability reconciliation.
- Added Colorado FAMLI, withholding, and unemployment-insurance breakdowns, including employer UI accrual.
- Added treasury projections, links to existing tax-payment entries, and filing confirmation tracking.
- Corrected zero-dollar payroll completion so unnecessary journal entries are not created.
- Added Listmonk services and environment configuration.
- Added stable MushroomProcess QR resolver exposure and Product destination configuration.
- Added Minecraft backup/restore coverage and repaired remote backup-retention pruning while keeping business documentation primary.
- Improved Appsmith reverse-proxy performance settings.

## Architecture boundary

ERPNext payroll and shared runtime services are operational at this baseline. ERPNext authority for vendor purchasing/purchased inventory and the new SignatureGate/MushroomProcess integration endpoints remain planned work.

## Coordinated baseline

- MushroomProcess `v1.2.0`
- SignatureGate `v1.1.0`
- RootedOps `v1.1.0`
- BookWorks `bookworks-v3.3.0`
