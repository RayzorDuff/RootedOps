# Issue #6 Phase D — Payroll-to-NACHA pre-export plan

Phase D connects submitted ERPNext Payroll Entries and Salary Slips to the Phase C NACHA formatter through a read-only pre-export planning workflow. It separates ACH from non-ACH employees, validates protected employee ACH configuration, reconciles ACH credits to Salary Slip net pay, and exercises the formatter/control-total validation without returning, downloading, or persisting a NACHA file.

The Phase D UI requires an explicit NACHA Profile and effective ACH date. The date is operator-supplied because bank-specific lead-time, cutoff, weekend, holiday, and settlement rules have not yet been certified. Balanced/offset files remain deferred until the bank specification confirms the required behavior.
