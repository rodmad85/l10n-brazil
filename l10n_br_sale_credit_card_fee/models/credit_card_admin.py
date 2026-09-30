from odoo import api, fields, models


class CreditCardAdmin(models.Model):
    _name = "credit.card.admin"
    _description = "Credit Card Administrator"
    _order = "name"

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
    )
    fee_line_ids = fields.One2many(
        comodel_name="credit.card.fee.range",
        inverse_name="admin_id",
        string="Fee Ranges",
    )


class CreditCardFeeRange(models.Model):
    _name = "credit.card.fee.range"
    _description = "Credit Card Fee Range by Installments"
    _order = "installments_from"

    admin_id = fields.Many2one(
        comodel_name="credit.card.admin",
        string="Card Administrator",
        required=True,
        ondelete="cascade",
    )
    installments_from = fields.Integer(required=True, default=1)
    installments_to = fields.Integer(required=True, default=1)
    fee_percent = fields.Float(
        string="Fee (%)",
        required=True,
        help="Credit card fee percentage for this installment range",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        related="admin_id.company_id",
        store=True,
    )

    @api.constrains("installments_from", "installments_to")
    def _check_installments_range(self):
        for rec in self:
            if rec.installments_from < 1:
                rec.installments_from = 1
            if rec.installments_to < rec.installments_from:
                rec.installments_to = rec.installments_from