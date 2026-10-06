# Copyright (C) 2026 Madooit
# License AGPL-3 - See http://www.gnu.org/licenses/agpl-3.0.html

from odoo import api, fields, models


class SaleInvoicePlan(models.Model):
    _inherit = "sale.invoice.plan"

    currency_id = fields.Many2one(
        related="sale_id.currency_id",
    )
    credit_card_fee_percent = fields.Char(
        string="Fee (%)",
        related="sale_id.credit_card_fee_percent",
    )
    credit_card_fee_amount = fields.Monetary(
        string="Fee Amount",
        currency_field="currency_id",
        compute="_compute_fee_amount",
    )

    @api.depends(
        "sale_id.credit_card_sum_fee",
        "sale_id.credit_card_fee_amount",
        "amount",
        "invoice_type",
    )
    def _compute_fee_amount(self):
        for rec in self:
            if (
                not rec.sale_id.credit_card_sum_fee
                or not rec.sale_id.credit_card_fee_amount
            ):
                rec.credit_card_fee_amount = 0.0
                continue
            if rec.invoice_type != "installment":
                rec.credit_card_fee_amount = 0.0
                continue
            total_installment_amount = sum(
                rec.sale_id.invoice_plan_ids.filtered(
                    lambda p: p.invoice_type == "installment"
                ).mapped("amount")
            )
            if total_installment_amount:
                ratio = rec.amount / total_installment_amount
                rec.credit_card_fee_amount = rec.sale_id.credit_card_fee_amount * ratio
            else:
                rec.credit_card_fee_amount = 0.0
