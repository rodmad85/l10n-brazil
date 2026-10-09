# Copyright (C) 2026  Rodrigo Macedo
# License AGPL-3 - See http://www.gnu.org/licenses/agpl-3.0.html

from odoo import models


class IrUiView(models.Model):
    _inherit = "ir.ui.view"

    def _postprocess_access_rights(self, tree):
        """Open the sale order lines in a popup for the fiscal detail group.

        In Odoo 18 the order lines of a sale order are an inline editable
        list (``editable="bottom"`` on the ``<list>`` sub view of the
        ``order_line`` field). The ``group_line_fiscal_detail`` group expects
        each line to be edited in a popup dialog with the full fiscal form
        instead.

        This used to be done by patching the arch in ``sale.order``
        ``_get_view``, but that is a cached entry point in Odoo 18: the arch
        is computed once (usually by the superuser) and group dependent
        modifications never reach the other users. ``_postprocess_access_rights``
        runs on every view load, after the cache, so it is the right place to
        apply a per-user arch tweak. ``editable=""`` makes the web client open
        the line form in a dialog (the falsy editable falls back to the
        record-in-dialog edition mode).
        """
        model = tree.get("model_access_rights")
        tree = super()._postprocess_access_rights(tree)
        # NOTE: the base implementation pops `model_access_rights` from the
        # root node, so capture the model before calling super().
        if model != "sale.order" or tree.tag != "form":
            return tree
        if self.env.company.country_id.code != "BR":
            return tree
        if not (
            self.env.user.has_group("l10n_br_sale.group_line_fiscal_detail")
            or self.env.context.get("force_line_fiscal_detail_edition")
        ):
            return tree
        for sub_list_node in tree.xpath("//field[@name='order_line']/list"):
            sub_list_node.set("editable", "")
        return tree