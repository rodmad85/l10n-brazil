from odoo.exceptions import ValidationError
from odoo.tests import Form
from odoo.tools import float_round

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


class TestCreditCardFee(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # The credit card configuration is restricted to the fee manager group,
        # so it is created as the administrator.
        fee_range_model = cls.env["credit.card.fee.range"].sudo()
        payment_method_model = cls.env["sale.payment.method"].sudo()
        cls.admin = (
            cls.env["credit.card.admin"]
            .sudo()
            .create(
                {
                    "name": "Test Administrator",
                }
            )
        )
        fee_range_model.create(
            {
                "admin_id": cls.admin.id,
                "installments_from": 1,
                "installments_to": 3,
                "fee_percent": 2.5,
            }
        )
        fee_range_model.create(
            {
                "admin_id": cls.admin.id,
                "installments_from": 4,
                "installments_to": 6,
                "fee_percent": 3.5,
            }
        )
        cls.other_admin = (
            cls.env["credit.card.admin"]
            .sudo()
            .create(
                {
                    "name": "Other Administrator",
                }
            )
        )
        fee_range_model.create(
            {
                "admin_id": cls.other_admin.id,
                "installments_from": 1,
                "installments_to": 3,
                "fee_percent": 1.5,
            }
        )
        fee_range_model.create(
            {
                "admin_id": cls.other_admin.id,
                "installments_from": 4,
                "installments_to": 6,
                "fee_percent": 4.0,
            }
        )
        cls.payment_method = payment_method_model.create(
            {
                "name": "Credit Card",
                "credit_card_admin_id": cls.admin.id,
            }
        )
        cls.other_payment_method = payment_method_model.create(
            {
                "name": "Other Credit Card",
                "credit_card_admin_id": cls.other_admin.id,
            }
        )
        cls.payment_method_no_admin = payment_method_model.create(
            {
                "name": "No Administrator",
            }
        )
        cls.product = cls.env["product.product"].create(
            {
                "name": "Test Product",
                "list_price": 100.0,
                "invoice_policy": "order",
            }
        )
        cls.partner = cls.env["res.partner"].create(
            {
                "name": "Test Partner",
            }
        )

    def _sale_order_form(self, *payment_methods):
        order_form = Form(self.env["sale.order"])
        order_form.partner_id = self.partner
        with order_form.order_line.new() as line:
            line.product_id = self.product
            line.product_uom_qty = 1
        for payment_method in payment_methods:
            order_form.payment_method_ids.add(payment_method)
        return order_form

    def _create_sale_order(self, *payment_methods):
        return self._sale_order_form(*payment_methods).save()

    def test_fee_percent_by_installments(self):
        order = self._create_sale_order(self.payment_method)
        order.create_invoice_plan(3, "2025-01-01", 1, "month", False)
        line = order.credit_card_fee_line_ids
        self.assertEqual(len(line), 1)
        self.assertEqual(order.credit_card_fee_percent, "2.5")
        self.assertAlmostEqual(line.fee_amount, line.amount * 0.025, places=2)
        self.assertAlmostEqual(
            order.credit_card_fee_amount,
            line.fee_amount,
        )

    def test_no_fee_without_admin(self):
        order = self._create_sale_order(self.payment_method_no_admin)
        order.create_invoice_plan(3, "2025-01-01", 1, "month", False)
        self.assertFalse(order.credit_card_fee_line_ids)
        self.assertEqual(order.credit_card_fee_percent, "")
        self.assertEqual(order.credit_card_fee_amount, 0.0)

    def test_fee_amount_included_in_total(self):
        order = self._create_sale_order(self.payment_method)
        total_before = order.amount_total
        order.create_invoice_plan(3, "2025-01-01", 1, "month", False)
        expected_total = total_before + order.credit_card_fee_amount
        self.assertEqual(order.amount_total, expected_total)

    def test_fee_amount_not_included_without_sum_fee(self):
        order = self._create_sale_order(self.payment_method)
        total_before = order.amount_total
        order.credit_card_sum_fee = False
        order.create_invoice_plan(3, "2025-01-01", 1, "month", False)
        self.assertTrue(order.credit_card_fee_amount)
        self.assertEqual(order.amount_total, total_before)

    def test_different_installment_range(self):
        order = self._create_sale_order(self.payment_method)
        order.create_invoice_plan(5, "2025-01-01", 1, "month", False)
        self.assertEqual(order.credit_card_fee_percent, "3.5")

    def test_no_fee_after_removing_admin(self):
        order = self._create_sale_order(self.payment_method)
        order.create_invoice_plan(3, "2025-01-01", 1, "month", False)
        self.assertTrue(order.credit_card_fee_percent)
        order.payment_method_ids = [(5, 0, 0)]
        order.credit_card_admin_id = False
        order._sync_credit_card_fee_lines()
        self.assertFalse(order.credit_card_fee_line_ids)
        self.assertEqual(order.credit_card_fee_percent, "")

    def test_fee_amount_base_is_amount_with_taxes(self):
        order = self._create_sale_order()
        order.fiscal_position_id = False
        tax = self.env["account.tax"].create(
            {
                "name": "Fee Test Tax",
                "amount_type": "percent",
                "amount": 10.0,
                "type_tax_use": "sale",
            }
        )
        order.order_line.tax_id = [(5, 0, 0), (4, tax.id)]
        order.payment_method_ids = [(4, self.payment_method.id)]
        order._sync_credit_card_fee_lines()
        line = order.credit_card_fee_line_ids
        self.assertEqual(len(line), 1)
        self.assertAlmostEqual(line.amount, order.amount_untaxed + order.amount_tax)
        self.assertAlmostEqual(line.amount, 110.0)

    def test_multiple_payment_methods(self):
        order = self._create_sale_order(self.payment_method, self.other_payment_method)
        order.create_invoice_plan(3, "2025-01-01", 1, "month", False)
        lines = order.credit_card_fee_line_ids
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines.mapped("admin_id"), self.admin + self.other_admin)
        self.assertEqual(order.credit_card_fee_percent, "2.5, 1.5")
        base_amount = lines[0].amount
        self.assertAlmostEqual(
            order.credit_card_fee_amount,
            sum(lines.mapped("fee_amount")),
        )
        self.assertAlmostEqual(
            order.amount_total,
            order.amount_untaxed + order.amount_tax + order.credit_card_fee_amount,
        )
        self.assertAlmostEqual(base_amount, order.amount_untaxed + order.amount_tax)

    def test_fee_line_amount_is_editable(self):
        order = self._create_sale_order(self.payment_method)
        order.create_invoice_plan(3, "2025-01-01", 1, "month", False)
        line = order.credit_card_fee_line_ids
        line.amount = 200.0
        self.assertAlmostEqual(line.fee_amount, 5.0)
        self.assertAlmostEqual(order.credit_card_fee_amount, 5.0)
        self.assertAlmostEqual(
            order.amount_total, order.amount_untaxed + order.amount_tax + 5.0
        )

    def test_negative_fee_amount_base_not_allowed(self):
        order = self._create_sale_order(self.payment_method)
        with self.assertRaises(ValidationError):
            with self.env.cr.savepoint():
                order.credit_card_fee_line_ids.amount = -10.0

    def test_onchange_payment_method_sets_admin_and_lines(self):
        order_form = self._sale_order_form(self.payment_method)
        self.assertEqual(order_form.credit_card_admin_id, self.admin)
        lines = order_form.credit_card_fee_line_ids
        self.assertEqual(len(lines), 1)
        with lines.edit(0) as line:
            self.assertEqual(line.admin_id, self.admin)
            self.assertEqual(line.payment_method_id, self.payment_method)
            base_amount = line.amount
        order = order_form.save()
        self.assertAlmostEqual(base_amount, order.amount_untaxed + order.amount_tax)

    def test_payment_method_removed_syncs_fee_lines(self):
        order = self._create_sale_order(self.payment_method, self.other_payment_method)
        self.assertEqual(len(order.credit_card_fee_line_ids), 2)
        order.payment_method_ids = [(3, self.other_payment_method.id)]
        order._sync_credit_card_fee_lines()
        self.assertEqual(len(order.credit_card_fee_line_ids), 1)
        self.assertEqual(order.credit_card_fee_line_ids.admin_id, self.admin)

    def test_sync_keeps_manual_line_without_admin(self):
        order = self._create_sale_order(self.payment_method)
        order.create_invoice_plan(3, "2025-01-01", 1, "month", False)
        manual_line = self.env["credit.card.fee.line"].create(
            {
                "order_id": order.id,
                "fee_percent": 1.0,
                "amount": 100.0,
            }
        )
        order._sync_credit_card_fee_lines()
        self.assertIn(manual_line, order.credit_card_fee_line_ids)
        self.assertEqual(len(order.credit_card_fee_line_ids), 2)
        self.assertEqual(order.credit_card_fee_percent, "2.5, 1")

    def test_fee_ranges_from_admin(self):
        order = self._create_sale_order()
        order.credit_card_admin_id = self.admin
        self.assertEqual(len(order.credit_card_fee_range_ids), 2)
        self.assertEqual(
            order.credit_card_fee_range_ids.mapped("fee_percent"),
            [2.5, 3.5],
        )

    def test_admin_without_payment_method_applies_fee(self):
        order = self._create_sale_order()
        order.write({"credit_card_admin_id": self.admin.id})
        order._sync_credit_card_fee_lines()
        order.create_invoice_plan(3, "2025-01-01", 1, "month", False)
        self.assertEqual(order.credit_card_fee_percent, "2.5")

    def test_create_order_syncs_fee_lines(self):
        order = self.env["sale.order"].create(
            {
                "partner_id": self.partner.id,
                "order_line": [
                    (0, 0, {"product_id": self.product.id, "product_uom_qty": 1}),
                ],
                "payment_method_ids": [(4, self.payment_method.id)],
                "credit_card_admin_id": self.admin.id,
            }
        )
        self.assertEqual(len(order.credit_card_fee_line_ids), 1)
        self.assertAlmostEqual(
            order.credit_card_fee_line_ids.amount,
            order.amount_untaxed + order.amount_tax,
        )

    def _create_wizard(self, order, num_installment=3, sum_fee=True):
        wizard_form = Form(
            self.env["sale.create.invoice.plan"].with_context(
                active_id=order.id,
                active_model="sale.order",
            )
        )
        wizard_form.num_installment = num_installment
        wizard_form.credit_card_admin_id = self.admin
        wizard_form.sum_fee = sum_fee
        return wizard_form.save()

    def test_wizard_sets_admin_and_adds_fee(self):
        order = self._create_sale_order()
        total_before = order.amount_total
        base_amount = order.amount_untaxed + order.amount_tax
        wizard = self._create_wizard(order)
        self.assertEqual(wizard.credit_card_fee_percent, "2.5")
        self.assertAlmostEqual(
            wizard.credit_card_fee_amount, base_amount * 0.025, places=2
        )
        expected_total = total_before + wizard.credit_card_fee_amount
        self.assertAlmostEqual(wizard.amount_plus_fee, expected_total)
        wizard.sale_create_invoice_plan()
        self.assertEqual(order.credit_card_admin_id, self.admin)
        self.assertTrue(order.credit_card_sum_fee)
        self.assertEqual(order.credit_card_fee_percent, "2.5")
        self.assertEqual(order.amount_total, expected_total)
        self.assertAlmostEqual(order.credit_card_amount_plus_fee, expected_total)

    def test_wizard_previews_all_payment_methods(self):
        order = self._create_sale_order(self.payment_method, self.other_payment_method)
        base_amount = order.amount_untaxed + order.amount_tax
        wizard = self._create_wizard(order)
        self.assertEqual(wizard.credit_card_fee_percent, "2.5, 1.5")
        # Each administrator fee is rounded to the currency precision
        expected_fee = sum(
            float_round(base_amount * percent / 100.0, 2) for percent in (2.5, 1.5)
        )
        self.assertAlmostEqual(wizard.credit_card_fee_amount, expected_fee, places=2)

    def test_wizard_without_sum_fee_keeps_total(self):
        order = self._create_sale_order()
        total_before = order.amount_total
        wizard = self._create_wizard(order, sum_fee=False)
        wizard.sale_create_invoice_plan()
        self.assertEqual(order.credit_card_admin_id, self.admin)
        self.assertFalse(order.credit_card_sum_fee)
        self.assertEqual(order.credit_card_fee_percent, "2.5")
        self.assertEqual(order.amount_total, total_before)
        self.assertAlmostEqual(order.credit_card_amount_plus_fee, total_before)

    def test_installment_invoice_includes_fee(self):
        order = self._create_sale_order()
        wizard = self._create_wizard(order)
        wizard.sale_create_invoice_plan()
        order.action_confirm()
        plans = order.invoice_plan_ids.filtered(
            lambda p: p.invoice_type == "installment"
        ).sorted("installment")
        move = order.with_context(invoice_plan_id=plans[0].id)._create_invoices()
        product = self.env.ref("l10n_br_sale_credit_card_fee.product_credit_card_fee")
        fee_lines = move.invoice_line_ids.filtered(
            lambda line: line.product_id == product
        )
        self.assertEqual(len(fee_lines), 1)
        self.assertIn("2.5", fee_lines.name)
        expected_fee = plans[0].credit_card_fee_amount
        self.assertAlmostEqual(
            fee_lines.price_unit * fee_lines.quantity,
            expected_fee,
        )
        self.assertAlmostEqual(
            move.amount_total - move.amount_tax,
            plans[0].amount + expected_fee,
        )

    def test_installment_invoice_without_sum_fee_has_no_fee_line(self):
        order = self._create_sale_order()
        wizard = self._create_wizard(order, sum_fee=False)
        wizard.sale_create_invoice_plan()
        order.action_confirm()
        plans = order.invoice_plan_ids.filtered(
            lambda p: p.invoice_type == "installment"
        ).sorted("installment")
        move = order.with_context(invoice_plan_id=plans[0].id)._create_invoices()
        product = self.env.ref("l10n_br_sale_credit_card_fee.product_credit_card_fee")
        self.assertFalse(
            move.invoice_line_ids.filtered(lambda line: line.product_id == product)
        )

    def test_payment_method_links_to_credit_card_admin(self):
        self.assertEqual(
            self.payment_method.credit_card_admin_id,
            self.admin,
        )
