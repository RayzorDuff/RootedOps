from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock

from rootedops_payroll.services.tax_compliance import (
    release_tax_payment_key_on_cancel,
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
