import re

from odoo import models


class IrAttachment(models.Model):
    _inherit = "ir.attachment"

    @staticmethod
    def _parse_file_number(name, cnab_config):
        if cnab_config.bank_id.code_bc == "748":
            parts = name.rsplit(".", 1)
            if len(parts) == 2 and parts[1].isdigit():
                return int(parts[1])
            return None
        base = name.rsplit(".", 1)[0] if "." in name else name
        m = re.search(r"\d{4}(\d+)$", base)
        if m:
            return int(m.group(1))
        return None

    def write(self, vals):
        result = super().write(vals)
        if "name" in vals:
            for att in self:
                if att.res_model != "account.payment.order" or not att.res_id:
                    continue
                order = self.env["account.payment.order"].browse(att.res_id)
                if not order.exists() or order.state != "generated":
                    continue
                cnab_config = order.payment_mode_id.cnab_config_id
                if not cnab_config or cnab_config.cnab_processor != "brcobranca":
                    continue
                new_name = vals.get("name", att.name)
                file_number = self._parse_file_number(new_name, cnab_config)
                if file_number is not None and file_number != order.file_number:
                    order.write({"file_number": file_number})
        return result
