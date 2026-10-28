from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock

from rootedops_payroll.services.tax_compliance import (
    release_tax_payment_key_on_cancel,
    JOURNAL_ENTRY_TAX_PAYMENT_CUSTOM_FIELDS,
)


class TestTaxPaymentCancellation(TestCase):
    def test_cancelled_tax_payment_releases_unique_key(self):
        doc = SimpleNamespace(
            docstatus=2,
            rootedops_tax_payment_key=(
                "Dank Mushrooms, LLC|2026|Q2|Colorado FAMLI"
            ),
            db_set=Mock(),
        )

        release_tax_payment_key_on_cancel(doc)

        doc.db_set.assert_called_once_with(
            "rootedops_tax_payment_key",
            None,
            update_modified=False,
        )

    def test_ordinary_journal_entry_is_unchanged(self):
        doc = SimpleNamespace(
            docstatus=2,
            rootedops_tax_payment_key=None,
            db_set=Mock(),
        )

        release_tax_payment_key_on_cancel(doc)

        doc.db_set.assert_not_called()

    def test_non_cancelled_tax_payment_is_unchanged(self):
        doc = SimpleNamespace(
            docstatus=1,
            rootedops_tax_payment_key=(
                "Dank Mushrooms, LLC|2026|Q2|Colorado FAMLI"
            ),
            db_set=Mock(),
        )

        release_tax_payment_key_on_cancel(doc)

        doc.db_set.assert_not_called()


class TestTaxPaymentAmendmentSchema(TestCase):
    def test_unique_key_not_copied_to_amended_journal_entry(self):
        fields = {
            field["fieldname"]: field
            for field in JOURNAL_ENTRY_TAX_PAYMENT_CUSTOM_FIELDS["Journal Entry"]
        }
        key = fields["rootedops_tax_payment_key"]
        self.assertEqual(key["unique"], 1)
        self.assertEqual(key["no_copy"], 1)

    def test_cancellation_only_clears_unique_key(self):
        doc = SimpleNamespace(
            docstatus=2,
            rootedops_tax_payment_key="company|2026|Q2|Colorado FAMLI",
            rootedops_tax_type="Colorado FAMLI",
            rootedops_tax_year=2026,
            rootedops_tax_quarter="Q2",
            rootedops_confirmation_number="confirmed",
            db_set=Mock(),
        )
        release_tax_payment_key_on_cancel(doc)
        doc.db_set.assert_called_once_with(
            "rootedops_tax_payment_key", None, update_modified=False
        )
        self.assertEqual(doc.rootedops_tax_type, "Colorado FAMLI")
        self.assertEqual(doc.rootedops_tax_quarter, "Q2")
        self.assertEqual(doc.rootedops_confirmation_number, "confirmed")
