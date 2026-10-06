# Copyright (C) 2026 Madooit
# License AGPL-3 - See http://www.gnu.org/licenses/agpl-3.0.html

from openupgradelib import openupgrade


@openupgrade.migrate()
def migrate(env, version):
    """Recreate the credit card fee lines of the existing sale orders.

    The applied fees are now stored in "credit.card.fee.line", one line per
    card administrator, with the amount and the fee amount. Orders created
    with the previous version have no such line, so their fees would not be
    summed anymore. The lines are synchronized with the payment methods (or
    with the card administrator of the order) and the current invoice plan.
    """
    orders = env["sale.order"].search([("credit_card_admin_id", "!=", False)])
    for order in orders:
        order._sync_credit_card_fee_lines()
