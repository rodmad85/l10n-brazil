# Copyright (C) 2026 Madooit
# License AGPL-3 - See http://www.gnu.org/licenses/agpl-3.0.html

from odoo import api, fields, models


class SaleCreateInvoicePlan(models.TransientModel):
    _inherit = "sale.create.invoice.plan"

    sale_id = fields.Many2one(
        comodel_name="sale.order",
        default=lambda self: self.env.context.get("active_id"),
    )
    currency_id = fields.Many2one(related="sale_id.currency_id")
    credit_card_admin_id = fields.Many2one(
        comodel_name="credit.card.admin",
        string="Card Administrator",
        default=lambda self: self._default_credit_card_admin_id(),
    )
    sum_fee = fields.Boolean(
        string="Add Fee",
        default=True,
        help="Add the credit card fee to the order total.",
    )
    credit_card_fee_percent = fields.Char(
        string="Fee (%)",
        compute="_compute_credit_card_fee",
        help="Fee percentages which will be applied, separated by comma.",
    )
    credit_card_fee_amount = fields.Monetary(
        compute="_compute_credit_card_fee",
    )
    amount_plus_fee = fields.Monetary(
        string="Amount + Fee",
        compute="_compute_credit_card_fee",
        help="Order total including the credit card fee.",
    )

    @api.model
    def _default_credit_card_admin_id(self):
        sale = self.env["sale.order"].browse(self.env.context.get("active_id"))
        return sale.credit_card_admin_id

    def _credit_card_admin_ids(self):
        """Return the administrators the fees must be applied for.

        The administrators of the payment methods of the sale order are used.
        When none of them has an administrator, the one selected in the wizard
        is used.
        """
        self.ensure_one()
        admins = self.sale_id.payment_method_ids.filtered(
            "credit_card_admin_id"
        ).mapped("credit_card_admin_id")
        if not admins and self.credit_card_admin_id:
            admins = self.credit_card_admin_id
        return admins

    @api.depends(
        "sale_id",
        "sale_id.amount_untaxed",
        "sale_id.amount_tax",
        "sale_id.payment_method_ids",
        "credit_card_admin_id",
        "num_installment",
        "sum_fee",
    )
    def _compute_credit_card_fee(self):
        fee_line_model = self.env["credit.card.fee.line"]
        for rec in self:
            rec.credit_card_fee_percent = ""
            rec.credit_card_fee_amount = 0.0
            rec.amount_plus_fee = rec.sale_id.amount_total
            if not (rec.sale_id and rec.num_installment):
                continue
            admins = rec._credit_card_admin_ids()
            if not admins:
                continue
            base_amount = rec.sale_id.amount_untaxed + rec.sale_id.amount_tax
            percents = [
                admin.fee_percent_for_installments(rec.num_installment)
                for admin in admins
            ]
            rec.credit_card_fee_percent = fee_line_model._format_fee_percents(percents)
            rec.credit_card_fee_amount = sum(
                fee_line_model._fee_amount_for(base_amount, percent, rec.currency_id)
                for percent in percents
            )
            if rec.sum_fee:
                rec.amount_plus_fee = (
                    rec.sale_id.amount_total + rec.credit_card_fee_amount
                )

    def sale_create_invoice_plan(self):
        self.ensure_one()
        sale = self.env["sale.order"].browse(self.env.context.get("active_id"))
        if sale and self.credit_card_admin_id:
            sale.write(
                {
                    "credit_card_admin_id": self.credit_card_admin_id.id,
                    "credit_card_sum_fee": self.sum_fee,
                }
            )
        return super().sale_create_invoice_plan()
