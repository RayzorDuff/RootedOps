# Issue #8 — Employee-specific payroll payment settlement

Issue #8 changes RootedOps payroll settlement from one consolidated employee-payment Journal Entry per payroll cycle to one full-net-pay settlement Journal Entry per submitted Salary Slip/employee. Payroll calculation and accrual remain batch-oriented; only the actual settlement of Payroll Payable is employee-specific.

## Final accounting boundary

RootedOps preserves three distinct layers:

1. **Payroll accrual/accounting** — native ERPNext/HRMS Payroll Entry and Salary Slip accounting remains authoritative. The existing employee-based payroll-accounting setting may add employee party detail without changing this RootedOps settlement workflow.
2. **Payroll tax reserve/remittance** — withholding reserve transfers and actual tax remittances remain consolidated where the real bank movement is consolidated.
3. **Employee net-pay settlement** — RootedOps creates one draft Bank Entry Journal Entry for each submitted, positive-net-pay Salary Slip selected by the Payroll Entry action.

For a $350 employee settlement the expected accounting is:

```text
Dr Payroll Payable                 350.00
   party_type = Employee
   party      = <Employee>
Cr configured payroll checking     350.00
```

The Journal Entry retains structured Employee, Salary Slip, Payroll Entry, payment method, logical payment identity, unique attempt identity, and attempt number metadata.

## Payroll Entry workflow

1. Calculate/submit payroll using the existing RootedOps/ERPNext workflow.
2. Create the consolidated payroll accrual Journal Entry where required.
3. Configure each Employee's RootedOps Payroll Payment section:
   - Payroll Payment Method
   - Payroll Payment Configuration Active
   - optional effective date
   - non-sensitive operational instructions
4. Use **Review Employee Payment Status** to inspect each submitted Salary Slip.
5. Use **Create Employee Payment Draft JEs** to create one draft settlement JE per eligible employee.
6. Review and submit/record each employee payment according to the actual payment method.
7. Reconcile each employee bank transaction against its individual payment JE.

The creation action is transactional: the full batch is preflighted before insertion, and the request transaction owns the commit. RootedOps does not intentionally leave a partial group of employee-payment JEs when validation or insertion fails.

## Lifecycle and idempotency

The stable logical identity is based on the Salary Slip full-net-pay obligation:

```text
salary-slip:<Salary Slip>:full-net-pay
```

Each settlement attempt receives its own unique key:

```text
salary-slip:<Salary Slip>:full-net-pay:attempt:1
salary-slip:<Salary Slip>:full-net-pay:attempt:2
```

Derived states are:

- **Not Recorded** — no employee-specific settlement attempt exists.
- **Payment JE Draft** — a current draft attempt exists; regeneration is blocked.
- **Payment JE Submitted** — a submitted attempt exists; regeneration is blocked.
- **Payment JE Cancelled** — only cancelled attempts remain; a replacement attempt may be created.
- **Payment JE Conflict** — more than one active attempt exists; generation is blocked until corrected.

Cancelled JEs remain audit history. They are not rewritten or deleted merely to permit regeneration.

## Accounting verification

The live Payroll Entry status panel and **Review Employee Payment Status** verify that an active/current employee-payment JE:

- belongs to the expected company;
- references the expected Employee;
- references the expected Salary Slip;
- references the expected Payroll Entry;
- debits the expected Payroll Payable account for the Salary Slip net pay;
- attributes the payable row to the correct Employee party;
- credits the configured/default payroll checking account for the same amount.

Accounting mismatches and multiple-active-attempt conflicts are surfaced instead of silently being counted as settled payroll.

## Historical behavior

Existing historical consolidated employee-payment Journal Entries are not automatically rewritten. An active legacy consolidated employee-payment JE linked to the Payroll Entry blocks prospective employee-specific settlement so Payroll Payable cannot be cleared twice. A cancelled legacy JE remains historical but no longer blocks a new employee-specific settlement.

## Payment execution boundary

Issue #8 records payment accounting and operator-visible payment method only. It does **not** execute Venmo, Apple Cash, paper checks, or ACH transmission.

ACH/NACHA generation belongs to Issue #6. That successor work will consume the employee-specific settlement model established here. For Dank Mushrooms, the company EIN already exists in ERPNext Company as `tax_id`; RootedOps should use that ERPNext field as the EIN source of truth rather than creating a duplicate EIN setting. High Plains Bank's NACHA Company ID can then be derived as `1` plus the normalized nine-digit EIN.

## Acceptance mapping

The completed implementation provides:

- one draft payment JE per submitted positive-net-pay Salary Slip/employee;
- Salary Slip net pay as the payment amount;
- Employee, Salary Slip, Payroll Entry, payment-method, and attempt traceability;
- mixed employee payment methods within one payroll cycle;
- duplicate prevention and cancellation-aware regeneration;
- independent employee-level bank reconciliation;
- preservation of consolidated payroll accrual, withholding-reserve transfer, and tax-remittance behavior;
- prospective-only behavior with no automatic historical rewrite;
- accounting consistency checks against actual JE rows;
- automated regression coverage for multi-employee/mixed-method generation, lifecycle/idempotency, and accounting reconciliation.

Issue #6 may extend the status model later with ACH-file/export/submission states without changing the Issue #8 accounting boundary.
