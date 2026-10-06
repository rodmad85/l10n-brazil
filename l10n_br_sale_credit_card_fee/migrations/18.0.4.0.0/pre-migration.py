# Copyright (C) 2026 Madooit
# License AGPL-3 - See http://www.gnu.org/licenses/agpl-3.0.html

from openupgradelib import openupgrade
from psycopg2 import sql

COLUMNS = [
    ("sale_order", "credit_card_fee_percent"),
    ("sale_create_invoice_plan", "credit_card_fee_percent"),
]


@openupgrade.migrate()
def migrate(env, version):
    """Convert the fee percentage columns from Float to Char.

    sale.order.credit_card_fee_percent and the transient wizard field became
    Char fields, since the fees of every payment method of the order are
    displayed as a comma separated list (e.g. "2.5, 3.5").
    """
    cr = env.cr
    for table, column in COLUMNS:
        if not openupgrade.column_exists(cr, table, column):
            continue
        cr.execute(
            sql.SQL(
                "ALTER TABLE {} ALTER COLUMN {} TYPE varchar USING {}::varchar"
            ).format(
                sql.Identifier(table),
                sql.Identifier(column),
                sql.Identifier(column),
            )
        )
