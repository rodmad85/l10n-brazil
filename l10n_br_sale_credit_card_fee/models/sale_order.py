from odoo import api, fields, models


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
    credit_card_fee_percent = fields.Float(
        string="Fee (%)",
        compute="_compute_credit_card_fee",
        store=True,
        readonly=True,
        copy=False,
    )
    credit_card_fee_amount = fields.Monetary(
        compute="_compute_amounts",
        store=True,
    )
    credit_card_amount_plus_fee = fields.Monetary(
        string="Amount + Fee",
        compute="_compute_amounts",
        store=True,
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

    @api.onchange("payment_method_ids")
    def _onchange_payment_method_ids(self):
        admin = self.payment_method_ids.filtered(
            "credit_card_admin_id"
        ).mapped("credit_card_admin_id")[:1]
        if admin:
            self.credit_card_admin_id = admin

    @api.depends(
        "credit_card_admin_id",
        "invoice_plan_ids",
        "invoice_plan_ids.installment",
    )
    def _compute_credit_card_fee(self):
        for order in self:
            if not order.credit_card_admin_id:
                order.credit_card_fee_percent = 0.0
                continue
            installments = order.invoice_plan_ids.filtered(
                lambda p: p.invoice_type == "installment"
            )
            num_installments = len(installments)
            if not num_installments:
                order.credit_card_fee_percent = 0.0
                continue
            fee = self.env["credit.card.fee.range"].search(
                [
                    ("admin_id", "=", order.credit_card_admin_id.id),
                    ("installments_from", "<=", num_installments),
                    ("installments_to", ">=", num_installments),
                ],
                limit=1,
            )
            order.credit_card_fee_percent = fee.fee_percent if fee else 0.0

    @api.depends(
        "order_line.price_subtotal",
        "currency_id",
        "company_id",
        "payment_term_id",
        "credit_card_sum_fee",
        "credit_card_fee_percent",
    )
    def _compute_amounts(self):
        res = super()._compute_amounts()
        for order in self:
            if (
                order.credit_card_admin_id
                and order.credit_card_sum_fee
                and order.credit_card_fee_percent
            ):
                fee = order.amount_untaxed * order.credit_card_fee_percent / 100.0
                order.credit_card_fee_amount = fee
                order.amount_total += fee
            else:
                order.credit_card_fee_amount = 0.0
            order.credit_card_amount_plus_fee = order.amount_total
        return res

    def _create_invoices(self, grouped=False, final=False, date=None):
        moves = super()._create_invoices(grouped=grouped, final=final, date=date)
        plan = self.env["sale.invoice.plan"].browse(
            self.env.context.get("invoice_plan_id") or 0
        )
        if not plan.exists():
            return moves
        order = plan.sale_id
        if (
            not order.credit_card_admin_id
            or not order.credit_card_sum_fee
            or not plan.credit_card_fee_amount
        ):
            return moves
        product = self.env.ref("l10n_br_sale_credit_card_fee.product_credit_card_fee")
        name = self.env._("Credit Card Fee (%s%%)") % order.credit_card_fee_percent
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