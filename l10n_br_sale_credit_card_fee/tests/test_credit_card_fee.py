from odoo.tests import Form
from odoo.addons.account.tests.common import AccountTestInvoicingCommon


class TestCreditCardFee(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin = cls.env["credit.card.admin"].create(
            {
                "name": "Test Administrator",
            }
        )
        cls.env["credit.card.fee.range"].create(
            {
                "admin_id": cls.admin.id,
                "installments_from": 1,
                "installments_to": 3,
                "fee_percent": 2.5,
            }
        )
        cls.env["credit.card.fee.range"].create(
            {
                "admin_id": cls.admin.id,
                "installments_from": 4,
                "installments_to": 6,
                "fee_percent": 3.5,
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

    def _create_sale_order(self):
        order_form = Form(self.env["sale.order"])
        order_form.partner_id = self.partner
        with order_form.order_line.new() as line:
            line.product_id = self.product
            line.product_uom_qty = 1
        return order_form.save()

    def test_fee_percent_by_installments(self):
        order = self._create_sale_order()
        order.credit_card_admin_id = self.admin
        order.create_invoice_plan(3, "2025-01-01", 1, "month", False)
        self.assertEqual(order.credit_card_fee_percent, 2.5)
        self.assertEqual(
            order.credit_card_fee_amount,
            order.amount_untaxed * 0.025,
        )

    def test_no_fee_without_admin(self):
        order = self._create_sale_order()
        order.create_invoice_plan(3, "2025-01-01", 1, "month", False)
        self.assertEqual(order.credit_card_fee_percent, 0.0)

    def test_fee_amount_included_in_total(self):
        order = self._create_sale_order()
        total_before = order.amount_total
        order.credit_card_admin_id = self.admin
        order.create_invoice_plan(3, "2025-01-01", 1, "month", False)
        expected_total = total_before + order.amount_untaxed * 0.025
        self.assertEqual(order.amount_total, expected_total)

    def test_different_installment_range(self):
        order = self._create_sale_order()
        order.credit_card_admin_id = self.admin
        order.create_invoice_plan(5, "2025-01-01", 1, "month", False)
        self.assertEqual(order.credit_card_fee_percent, 3.5)

    def test_no_fee_after_removing_admin(self):
        order = self._create_sale_order()
        order.credit_card_admin_id = self.admin
        order.create_invoice_plan(3, "2025-01-01", 1, "month", False)
        self.assertTrue(order.credit_card_fee_percent > 0)
        order.credit_card_admin_id = False
        self.assertEqual(order.credit_card_fee_percent, 0.0)

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
        wizard = self._create_wizard(order)
        self.assertEqual(wizard.credit_card_fee_percent, 2.5)
        self.assertAlmostEqual(
            wizard.credit_card_fee_amount,
            order.amount_untaxed * 0.025,
        )
        expected_total = total_before + wizard.credit_card_fee_amount
        self.assertAlmostEqual(wizard.amount_plus_fee, expected_total)
        wizard.sale_create_invoice_plan()
        self.assertEqual(order.credit_card_admin_id, self.admin)
        self.assertTrue(order.credit_card_sum_fee)
        self.assertEqual(order.credit_card_fee_percent, 2.5)
        self.assertEqual(order.amount_total, expected_total)
        self.assertAlmostEqual(order.credit_card_amount_plus_fee, expected_total)

    def test_wizard_without_sum_fee_keeps_total(self):
        order = self._create_sale_order()
        total_before = order.amount_total
        wizard = self._create_wizard(order, sum_fee=False)
        wizard.sale_create_invoice_plan()
        self.assertEqual(order.credit_card_admin_id, self.admin)
        self.assertFalse(order.credit_card_sum_fee)
        self.assertEqual(order.credit_card_fee_percent, 2.5)
        self.assertEqual(order.credit_card_fee_amount, 0.0)
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
        product = self.env.ref(
            "l10n_br_sale_credit_card_fee.product_credit_card_fee"
        )
        fee_lines = move.invoice_line_ids.filtered(
            lambda line: line.product_id == product
        )
        self.assertEqual(len(fee_lines), 1)
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
        product = self.env.ref(
            "l10n_br_sale_credit_card_fee.product_credit_card_fee"
        )
        self.assertFalse(
            move.invoice_line_ids.filtered(lambda line: line.product_id == product)
        )

    def test_payment_method_links_to_credit_card_admin(self):
        payment_method = self.env["sale.payment.method"].create(
            {
                "name": "Cartao de Credito",
                "credit_card_admin_id": self.admin.id,
            }
        )
        self.assertTrue(payment_method.credit_card_admin_id)

    def test_onchange_payment_method_sets_admin(self):
        payment_method = self.env["sale.payment.method"].create(
            {
                "name": "Cartao de Credito",
                "credit_card_admin_id": self.admin.id,
            }
        )
        order_form = Form(self.env["sale.order"])
        order_form.partner_id = self.partner
        with order_form.order_line.new() as line:
            line.product_id = self.product
            line.product_uom_qty = 1
        order_form.payment_method_ids.add(payment_method)
        self.assertEqual(order_form.credit_card_admin_id, self.admin)

    def test_fee_ranges_from_admin(self):
        order = self._create_sale_order()
        order.credit_card_admin_id = self.admin
        self.assertEqual(len(order.credit_card_fee_range_ids), 2)
        self.assertEqual(
            order.credit_card_fee_range_ids.mapped("fee_percent"),
            [2.5, 3.5],
        )