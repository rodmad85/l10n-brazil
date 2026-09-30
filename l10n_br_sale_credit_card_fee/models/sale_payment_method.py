from odoo import fields, models


class SalePaymentMethod(models.Model):
    _inherit = "sale.payment.method"

    credit_card_admin_id = fields.Many2one(
        comodel_name="credit.card.admin",
        string="Card Administrator",
    )
