# Copyright (C) 2026 Madooit
# License AGPL-3 - See http://www.gnu.org/licenses/agpl-3.0.html

from odoo import Command, api, fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    credit_card_admin_id = fields.Many2one(
        comodel_name="credit.card.admin",
        string="Card Administrator",
        ondelete="restrict",
        copy=False,
    )
    credit_card_sum_fee = fields.Boolean(
        string="Add Fee",
        default=True,
        copy=False,
        help="Add the credit card fee to the order total.",
    )
    credit_card_fee_percent = fields.Char(
        string="Fee (%)",
        compute="_compute_credit_card_fee_percent",
        store=True,
        readonly=True,
        copy=False,
        help="Fee percentages applied on this order, separated by comma.",
    )
    credit_card_fee_amount = fields.Monetary(
        string="Fee Amount",
        compute="_compute_credit_card_fee_amount",
        store=True,
        currency_field="currency_id",
    )
    credit_card_amount_plus_fee = fields.Monetary(
        string="Amount + Fee",
        compute="_compute_amounts",
        store=True,
    )
    credit_card_fee_line_ids = fields.One2many(
        comodel_name="credit.card.fee.line",
        inverse_name="order_id",
        string="Credit Card Fees",
    )
    credit_card_fee_range_ids = fields.Many2many(
        comodel_name="credit.card.fee.range",
        compute="_compute_credit_card_fee_range_ids",
    )

    @api.depends("credit_card_admin_id")
    def _compute_credit_card_fee_range_ids(self):
        for order in self:
            order.credit_card_fee_range_ids = (
                order.credit_card_admin_id.fee_line_ids
                if order.credit_card_admin_id
                else self.env["credit.card.fee.range"]
            )

    @api.depends("credit_card_fee_line_ids.fee_percent")
    def _compute_credit_card_fee_percent(self):
        fee_line_model = self.env["credit.card.fee.line"]
        for order in self:
            order.credit_card_fee_percent = fee_line_model._format_fee_percents(
                order.credit_card_fee_line_ids.mapped("fee_percent")
            )

    @api.depends("credit_card_fee_line_ids.fee_amount")
    def _compute_credit_card_fee_amount(self):
        for order in self:
            order.credit_card_fee_amount = sum(
                order.credit_card_fee_line_ids.mapped("fee_amount")
            )

    @api.depends(
        "order_line.price_subtotal",
        "currency_id",
        "company_id",
        "payment_term_id",
        "credit_card_sum_fee",
        "credit_card_fee_amount",
    )
    def _compute_amounts(self):
        res = super()._compute_amounts()
        for order in self:
            if order.credit_card_sum_fee and order.credit_card_fee_amount:
                order.amount_total += order.credit_card_fee_amount
            order.credit_card_amount_plus_fee = order.amount_total
        return res

    @api.model_create_multi
    def create(self, vals_list):
        orders = super().create(vals_list)
        for order in orders:
            if order.credit_card_admin_id:
                order._sync_credit_card_fee_lines()
        return orders

    @api.onchange("payment_method_ids")
    def _onchange_payment_method_ids(self):
        if not self.payment_method_ids:
            return
        admins = self.payment_method_ids.filtered("credit_card_admin_id").mapped(
            "credit_card_admin_id"
        )
        if admins:
            self.credit_card_admin_id = admins[:1]
        self._sync_credit_card_fee_lines()

    @api.onchange("credit_card_admin_id")
    def _onchange_credit_card_admin_id(self):
        self._sync_credit_card_fee_lines()

    def _credit_card_admin_ids(self):
        """Return the administrators the fees must be applied for.

        The administrators of the selected payment methods are used. When none
        of them has an administrator, the one selected in the order is used.
        """
        self.ensure_one()
        admins = self.payment_method_ids.filtered("credit_card_admin_id").mapped(
            "credit_card_admin_id"
        )
        if not admins and self.credit_card_admin_id:
            admins = self.credit_card_admin_id
        return admins

    def _credit_card_installment_count(self):
        """Return the number of installments of the invoice plan."""
        self.ensure_one()
        return len(
            self.invoice_plan_ids.filtered(
                lambda plan: plan.invoice_type == "installment"
            )
        )

    def _credit_card_fee_base_amount(self):
        """Return the order total with taxes, without the credit card fee."""
        self.ensure_one()
        return self.amount_untaxed + self.amount_tax

    def _sync_credit_card_fee_lines(self, num_installments=None):
        """Sync the applied fee lines with the administrators of the order.

        One line per administrator is kept, with the fee percentage of the
        given number of installments (the current invoice plan by default).
        New lines are filled with the order total including taxes.
        """
        self.ensure_one()
        if num_installments is None:
            num_installments = self._credit_card_installment_count()
        admins = self._credit_card_admin_ids()
        stale_lines = self.credit_card_fee_line_ids.filtered(
            lambda line: line.admin_id and line.admin_id not in admins
        )
        if stale_lines:
            stale_lines.unlink()
        base_amount = self._credit_card_fee_base_amount()
        new_lines = []
        for admin in admins:
            fee = admin.fee_range_for_installments(num_installments)
            values = {
                "admin_id": admin.id,
                "payment_method_id": self.payment_method_ids.filtered(
                    lambda method, adm=admin: method.credit_card_admin_id == adm
                )[:1].id,
                "installments_from": fee.installments_from,
                "installments_to": fee.installments_to,
                "fee_percent": fee.fee_percent,
            }
            line = self.credit_card_fee_line_ids.filtered(
                lambda line, adm=admin: line.admin_id == adm
            )[:1]
            if line:
                line.write(values)
            else:
                new_lines.append(Command.create({**values, "amount": base_amount}))
        if new_lines:
            self.credit_card_fee_line_ids = new_lines

    def create_invoice_plan(
        self, num_installment, installment_date, interval, interval_type, advance
    ):
        res = super().create_invoice_plan(
            num_installment, installment_date, interval, interval_type, advance
        )
        self._sync_credit_card_fee_lines(num_installments=num_installment)
        return res

    def remove_invoice_plan(self):
        res = super().remove_invoice_plan()
        self._sync_credit_card_fee_lines()
        return res

    def _create_invoices(self, grouped=False, final=False, date=None):
        moves = super()._create_invoices(grouped=grouped, final=final, date=date)
        plan = self.env["sale.invoice.plan"].browse(
            self.env.context.get("invoice_plan_id") or 0
        )
        if not plan.exists():
            return moves
        order = plan.sale_id
        if not order.credit_card_sum_fee or not order.credit_card_fee_amount:
            return moves
        product = self.env.ref("l10n_br_sale_credit_card_fee.product_credit_card_fee")
        name = self.env._("Credit Card Fee (%s)") % order.credit_card_fee_percent
        for move in moves:
            if move.move_type != "out_invoice":
                continue
            if move.invoice_line_ids.filtered(lambda line: line.product_id == product):
                continue
            move.write(
                {
                    "invoice_line_ids": [
                        (
                            0,
                            0,
                            {
                                "product_id": product.id,
                                "name": name,
                                "quantity": 1,
                                "price_unit": plan.credit_card_fee_amount,
                                "tax_ids": [(5, 0, 0)],
                            },
                        )
                    ]
                }
            )
        return moves
