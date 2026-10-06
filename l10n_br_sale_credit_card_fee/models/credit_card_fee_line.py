# Copyright (C) 2026 Madooit
# License AGPL-3 - See http://www.gnu.org/licenses/agpl-3.0.html

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import float_round


class CreditCardFeeLine(models.Model):
    _name = "credit.card.fee.line"
    _description = "Credit Card Fee Line"
    _order = "id"
    _check_company_auto = True

    order_id = fields.Many2one(
        comodel_name="sale.order",
        string="Sale Order",
        required=True,
        index=True,
        ondelete="cascade",
    )
    payment_method_id = fields.Many2one(
        comodel_name="sale.payment.method",
        string="Payment Method",
        ondelete="restrict",
        help="Payment method which originated this fee.",
    )
    admin_id = fields.Many2one(
        comodel_name="credit.card.admin",
        string="Card Administrator",
        ondelete="restrict",
        help="Card administrator which originated this fee.",
    )
    installments_from = fields.Integer(readonly=True)
    installments_to = fields.Integer(readonly=True)
    fee_percent = fields.Float(
        string="Fee (%)",
        help="Fee percentage applied by this line.",
    )
    amount = fields.Monetary(
        currency_field="currency_id",
        help="Base amount of the fee. It is filled with the order total "
        "including taxes when the payment method is selected.",
    )
    fee_amount = fields.Monetary(
        currency_field="currency_id",
        compute="_compute_fee_amount",
        store=True,
    )
    currency_id = fields.Many2one(
        related="order_id.currency_id",
        store=True,
    )
    company_id = fields.Many2one(
        related="order_id.company_id",
        store=True,
    )

    @api.model
    def _format_fee_percents(self, percents):
        """Return the fee percentages as a single comma separated string."""
        return ", ".join(
            f"{percent:.2f}".rstrip("0").rstrip(".") for percent in percents if percent
        )

    @api.model
    def _fee_amount_for(self, amount, percent, currency):
        """Return the fee of an amount and a percentage, as applied on a line.

        The value is rounded to the precision of the currency, so that fee
        previews (the *Create Invoice Plan* wizard) match the sum of the fee
        lines of the sale order.
        """
        return float_round(
            amount * percent / 100.0,
            precision_digits=currency.decimal_places,
        )

    @api.depends("amount", "fee_percent")
    def _compute_fee_amount(self):
        for line in self:
            line.fee_amount = line._fee_amount_for(
                line.amount, line.fee_percent, line.order_id.currency_id
            )

    @api.constrains("amount", "fee_percent")
    def _check_fee_values(self):
        for line in self:
            if line.amount < 0.0:
                raise ValidationError(_("The fee amount base cannot be negative."))
            if line.fee_percent < 0.0:
                raise ValidationError(_("The fee percentage cannot be negative."))
