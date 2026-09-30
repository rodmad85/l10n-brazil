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
    credit_card_fee_percent = fields.Float(
        string="Fee (%)",
        compute="_compute_credit_card_fee",
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

    @api.depends(
        "sale_id",
        "sale_id.amount_untaxed",
        "sale_id.amount_total",
        "credit_card_admin_id",
        "num_installment",
    )
    def _compute_credit_card_fee(self):
        for rec in self:
            rec.credit_card_fee_percent = 0.0
            rec.credit_card_fee_amount = 0.0
            if rec.sale_id:
                rec.amount_plus_fee = rec.sale_id.amount_total
            if not (
                rec.sale_id
                and rec.credit_card_admin_id
                and rec.num_installment
            ):
                continue
            fee = rec.env["credit.card.fee.range"].search(
                [
                    ("admin_id", "=", rec.credit_card_admin_id.id),
                    ("installments_from", "<=", rec.num_installment),
                    ("installments_to", ">=", rec.num_installment),
                ],
                limit=1,
            )
            percent = fee.fee_percent if fee else 0.0
            rec.credit_card_fee_percent = percent
            rec.credit_card_fee_amount = rec.sale_id.amount_untaxed * percent / 100.0
            rec.amount_plus_fee = rec.sale_id.amount_total + rec.credit_card_fee_amount

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