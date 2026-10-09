# Copyright 2026 - TODAY Akretion (<https://akretion.com>)
# License AGPL-3 - See http://www.gnu.org/licenses/agpl-3.0.html.

from openupgradelib import openupgrade

TABLE = "sale_order_line"
MODEL = "sale.order.line"
OLD_FIELD = "discount_fixed"
NEW_FIELD = "use_discount_value"


def _column_type(cr, table, column):
    """Return the PostgreSQL type name of ``column``, or None if not found."""
    cr.execute(
        """
        SELECT atttypid::regtype::text
          FROM pg_attribute att
          JOIN pg_class cls ON cls.oid = att.attrelid
         WHERE cls.relname = %s
           AND att.attname = %s
           AND att.attnum > 0
           AND NOT att.attisdropped
        """,
        (table, column),
    )
    row = cr.fetchone()
    return row[0] if row else None


@openupgrade.migrate()
def migrate(env, version):
    """Rename sale.order.line.discount_fixed to use_discount_value.

    "discount_fixed" was a boolean flag telling whether the line discount is
    entered as a fixed amount ("discount_value") instead of a percentage. That
    name is also used by the OCA module "sale_fixed_discount", which defines
    it as a fixed discount *amount* (Float -> numeric column). Both modules
    therefore shared the same database column, and installing/updating one of
    them made Odoo cast it (numeric <-> boolean), which fails as soon as the
    column holds a value that is not 0 or 1.

    The column is only renamed when it is a boolean, i.e. when it really is the
    column created by this module. If it is numeric, it belongs to
    "sale_fixed_discount" and must be left untouched: "use_discount_value" is
    then simply created as a new column.
    """
    cr = env.cr
    if not openupgrade.column_exists(cr, TABLE, OLD_FIELD):
        return
    if _column_type(cr, TABLE, OLD_FIELD) != "boolean":
        return
    openupgrade.rename_fields(env, [(MODEL, TABLE, OLD_FIELD, NEW_FIELD)])
