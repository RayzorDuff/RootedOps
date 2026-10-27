"""Private Colorado FAMLI single-filer CSV, per official v1.18 35-column schema.

Run ONLY within trusted Frappe bench. Real output contains SSNs and addresses.
Values from ERPNext Company/Address/Employee/Salary Slip. Fail closed when
ambiguous: premiums and employee withholding use the existing RootedOps
payroll engine. No private IDs in source code.
"""
from __future__ import annotations

import csv
import os
import re
import tempfile
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import frappe
from rootedops_payroll.services.co_ui_wage_export import _get_ssn
from rootedops_payroll.services.payroll_engine import calculate_colorado_famli_premium, ytd_gross_before_period

HEADERS = (
    'DocumentCount AmendedReturn FAMLIPremiumStartDate FAMLIPremiumEndDate '
    'PreparerLegalName PreparerFEIN SettlementDate ReturnTotalContributionsDue '
    'EmployerFEIN EmployerFAMLIId EmployerLegalName EmployerTaxPayerId '
    'IndividualName FName MName LName BusAdrStreet1 BusAdrStreet2 '
    'BusAdrStreet3 BusAdrCity BusAdrStateCode BusAdrPostalCode BusAdrCountry '
    'TotalWagesThisPeriod TotalContributionsDue PaymentAmountTotal IsFinalReturn '
    'EmployeeSSN EmployeeFirstName EmployeeMiddleName EmployeeLastName '
    'YearToDateWages GrossWagesThisQtr SubjectWagesThisQtr '
    'FAMLIContributionThisQtr'
).split()
QUARTER_MONTHS = {1:(1,3), 2:(4,6), 3:(7,9), 4:(10,12)}
CENT=Decimal('0.01')

def money(v):
    return Decimal(str(v or '0')).quantize(CENT, rounding=ROUND_HALF_UP)

def _address(company):
    names=frappe.get_all('Dynamic Link', filters={'parenttype':'Address','link_doctype':'Company','link_name':company}, pluck='parent')
    if not names:
        frappe.throw('No Address linked to selected Company; configure a company address in ERPNext')
    addresses=frappe.get_all('Address',filters={'name':['in',names]},fields=['name','address_line1','address_line2','city','state','pincode','country','is_primary_address'])
    addresses.sort(key=lambda a:(-int(a.is_primary_address or 0), a.name))
    return addresses[0]

def _ssn(ssn):
    if not re.fullmatch(r'[0-9]{9}',ssn) or ssn[:3] in ('000','666') or ssn[0]=='9' or ssn[3:5]=='00' or ssn[5:]=='0000':
        frappe.throw('Employee SSN fails FAMLI format validation; correct Employee record before export')
    return ssn

def export(company, year, quarter, output_path, payment_amount_total='0', settlement_date=None):
    """Generate protected 35-column single-employer FAMLI CSV.

    Uses the SAME company FAMLI engine as the Quarterly Payroll Tax Report,
    including its employer-paid employee-share setting and statutory employer
    rate. payment_amount_total defaults to zero for wage-report-only uploads;
    report/premium payment remains separate until portal confirms otherwise.
    Returns only nonsensitive aggregate results.
    """
    year,quarter=int(year),int(quarter)
    if quarter not in QUARTER_MONTHS or not 2000<=year<=2100:
        frappe.throw('Invalid year or quarter')
    if not frappe.db.exists('Company',company): frappe.throw('Unknown Company')
    payment=money(payment_amount_total)
    if payment<0: frappe.throw('Invalid payment amount')
    start_m,end_m=QUARTER_MONTHS[quarter]
    start=date(year,start_m,1)
    last=date(year+int(end_m==12),end_m%12+1,1).toordinal()-1
    end=date.fromordinal(last)
    # Most existing payroll reports aggregate by posting_date. Confirm payroll
    # date basis for FAMLI, especially where payday differs from work dates.
    slips=frappe.get_all('Salary Slip',filters={'company':company,'docstatus':1,'posting_date':['between',[date(year,1,1),end]]}, fields=['name','employee','posting_date','start_date','gross_pay'],order_by='employee asc, posting_date asc')
    current=[s for s in slips if start<=s.posting_date<=end]
    if not current: frappe.throw('No submitted slips in selected quarter')
    # Share the exact premium engine and YTD basis of the existing quarter report;
    # when the employer pays the employee share, the employee's withheld
    # contribution is zero while employer expense contains that share.
    premium_by_slip={}
    for slip in slips:
        prior=ytd_gross_before_period(slip.employee, slip.start_date, exclude_slip_name=slip.name)
        premium_by_slip[slip.name]=calculate_colorado_famli_premium(
            company, slip.gross_pay, prior, slip.posting_date)
    grouped=defaultdict(list)
    for s in slips: grouped[s.employee].append(s)
    employees=[]
    for employee, all_slips in sorted(grouped.items()):
        qslips=[s for s in all_slips if start<=s.posting_date<=end]
        if not qslips: continue
        rec=frappe.db.get_value('Employee',employee,['first_name','middle_name','last_name'],as_dict=True)
        if not rec or not rec.first_name or not rec.last_name: frappe.throw('Employee first and last name required')
        qgross=sum((money(s.gross_pay) for s in qslips),Decimal('0'))
        subject=sum((money(premium_by_slip[s.name]['taxable_wages']) for s in qslips),Decimal('0'))
        subject_ytd=sum((money(premium_by_slip[s.name]['taxable_wages']) for s in all_slips),Decimal('0'))
        contribution=sum((money(premium_by_slip[s.name]['employee_withholding']) for s in qslips),Decimal('0'))
        statutory_employer=sum((money(premium_by_slip[s.name]['employer_expense']) for s in qslips),Decimal('0'))
        if qgross<0 or subject<0 or contribution<0: frappe.throw('Invalid wages or contributions')
        employees.append({'ssn':_ssn(_get_ssn(employee)),'first':rec.first_name,'middle':rec.middle_name or '',
                          'last':rec.last_name,'gross':qgross,'subject':subject,'subject_ytd':subject_ytd,'contribution':contribution,'employer_premium':statutory_employer})
    total_subject=sum((e['subject'] for e in employees),Decimal('0'))
    total_contributions=sum((e['contribution'] for e in employees),Decimal('0'))
    total_employer=sum((e['employer_premium'] for e in employees),Decimal('0'))
    assessed=total_contributions+total_employer
    if payment not in (Decimal('0.00'), assessed):
        frappe.throw('For a separate wage-only report use payment_amount_total=0; for full payment supply the exact calculated amount')
    a=_address(company)
    ein=re.sub(r'[^0-9]','',str(frappe.db.get_value('Company',company,'tax_id') or ''))
    if len(ein)!=9: frappe.throw('Company tax_id must contain a nine-digit FEIN')
    required_address_fields = ('address_line1', 'city', 'state', 'pincode', 'country')
    missing_address_fields = [field for field in required_address_fields if not a.get(field)]
    if missing_address_fields:
        frappe.throw('Company Address is missing required fields: ' + ', '.join(missing_address_fields))
    timestamp=settlement_date or datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    if not re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:Z|[+-]\d\d:\d\d)',timestamp):
        frappe.throw('Invalid settlement timestamp')
    common=dict(DocumentCount=str(len(employees)),AmendedReturn='false', FAMLIPremiumStartDate=start.isoformat(),
        FAMLIPremiumEndDate=end.isoformat(), PreparerLegalName='', PreparerFEIN='',SettlementDate=timestamp,
        ReturnTotalContributionsDue=f'{assessed:.2f}',EmployerFEIN=ein,EmployerFAMLIId='',
        EmployerLegalName=company, EmployerTaxPayerId='',IndividualName='',FName='',MName='',LName='',
        BusAdrStreet1=a.address_line1, BusAdrStreet2=a.address_line2 or '',BusAdrStreet3='',
        BusAdrCity=a.city,BusAdrStateCode='CO',BusAdrPostalCode=a.pincode,BusAdrCountry='United States',
        TotalWagesThisPeriod=f'{total_subject:.2f}',TotalContributionsDue=f'{assessed:.2f}',
        PaymentAmountTotal=f'{payment:.2f}',IsFinalReturn='false')
    output=Path(output_path)
    if not output.is_absolute() or output.suffix.lower()!='.csv':frappe.throw('Use an absolute .csv output path')
    if output.exists():frappe.throw('Refusing to overwrite output')
    output.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='.famli-',dir=output.parent)
    try:
        os.fchmod(fd,0o600)
        with os.fdopen(fd,'w',newline='',encoding='utf-8') as f:
            writer=csv.DictWriter(f,fieldnames=HEADERS,lineterminator='\r\n')
            writer.writeheader()
            for e in employees:
                writer.writerow({**common,'EmployeeSSN':e['ssn'],'EmployeeFirstName':e['first'],
                    'EmployeeMiddleName':e['middle'],'EmployeeLastName':e['last'],
                    'YearToDateWages':f"{e['subject_ytd']:.2f}", 'GrossWagesThisQtr':f"{e['gross']:.2f}",
                    'SubjectWagesThisQtr':f"{e['subject']:.2f}",
                    'FAMLIContributionThisQtr':f"{e['contribution']:.2f}"})
        os.replace(tmp,output)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
    return {'path':str(output),'employee_count':len(employees),
            'quarter_subject_wages':f'{total_subject:.2f}',
            'employee_contributions':f'{total_contributions:.2f}',
            'employer_contributions':f'{total_employer:.2f}',
            'remittance_due':f'{assessed:.2f}',
            'payment_total':f'{payment:.2f}',
            'warning':'Review wage basis, SS cap, business registration and portal import results before filing; sensitive file.'}
