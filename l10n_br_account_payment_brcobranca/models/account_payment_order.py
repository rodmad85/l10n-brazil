# Copyright 2020 Akretion
# @author Magno Costa <magno.costa@akretion.com.br>
# Copyright 2020 KMEE
# @author Luis Felipe Mileo <mileo@kmee.com.br>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import base64
import json
import logging
import tempfile

import requests
from erpbrasil.base import misc

from odoo import _, fields, models
from odoo.exceptions import ValidationError

from ..constants.br_cobranca import (
    DICT_BRCOBRANCA_CNAB_TYPE,
    TIMEOUT,
    get_brcobranca_api_url,
    get_brcobranca_bank,
)

_logger = logging.getLogger(__name__)


class PaymentOrder(models.Model):
    _inherit = "account.payment.order"

    def _prepare_remessa_banco_brasil(self, remessa_values, cnab_config):
        remessa_values.update(
            {
                "convenio": str(cnab_config.cnab_company_bank_code),
                "carteira": str(cnab_config.boleto_wallet).zfill(2),
            }
        )

        if cnab_config.payment_method_code == "240":
            remessa_values.update(
                {
                    "variacao": cnab_config.boleto_variation.zfill(3),
                    "agencia": str(self.journal_id.bank_account_id.bra_number),
                    "conta_corrente": str(
                        misc.punctuation_rm(self.journal_id.bank_account_id.acc_number)
                    ),
                }
            )

        if cnab_config.payment_method_code == "400":
            remessa_values.update(
                {
                    "variacao_carteira": cnab_config.boleto_variation.zfill(3),
                    "convenio_lider": cnab_config.convention_code.zfill(7),
                }
            )

    def _prepare_remessa_santander(self, remessa_values, cnab_config):
        remessa_values.update(
            {
                "codigo_carteira": cnab_config.wallet_code_id.code,
                "codigo_transmissao": cnab_config.cnab_company_bank_code,
                "conta_corrente": misc.punctuation_rm(
                    self.journal_id.bank_account_id.acc_number
                ),
            }
        )

    def _prepare_remessa_caixa(self, remessa_values, cnab_config):
        remessa_values.update(
            {
                "convenio": int(cnab_config.cnab_company_bank_code),
                "digito_agencia": self.journal_id.bank_account_id.bra_number_dig,
            }
        )

    def _prepare_remessa_ailos(self, remessa_values, cnab_config):
        remessa_values.update(
            {
                "convenio": int(cnab_config.cnab_company_bank_code),
                "digito_agencia": self.journal_id.bank_account_id.bra_number_dig,
            }
        )

    def _prepare_remessa_unicred(self, remessa_values, cnab_config):
        remessa_values["codigo_beneficiario"] = int(cnab_config.cnab_company_bank_code)

    def _prepare_remessa_sicredi(self, remessa_values, cnab_config):
        bank_account_id = self.journal_id.bank_account_id
        conta_corrente = misc.punctuation_rm(
            bank_account_id.acc_number
        )
        # Sicredi valida conta_corrente com max 5 dígitos
        if len(conta_corrente) > 5:
            conta_corrente = conta_corrente[-5:]
        remessa_values.update(
            {
                # Aparentemente a validação do BRCobranca nesse caso gera erro
                # quando é feito o int(misc.punctuation_rm(bank_account_id.acc_number))
                "conta_corrente": conta_corrente,
                "posto": cnab_config.boleto_post,
                "byte_idt": cnab_config.boleto_byte_idt,
            }
        )

    def _prepare_remessa_bradesco(self, remessa_values, cnab_config):
        remessa_values["codigo_empresa"] = int(cnab_config.cnab_company_bank_code)

    def _build_remessa_values(self, sequencial):
        cnab_config = self.payment_mode_id.cnab_config_id
        bank_account_id = self.journal_id.bank_account_id
        bank_brcobranca = get_brcobranca_bank(
            bank_account_id, cnab_config.payment_method_id.code
        )
        pagamentos = []
        for line in self.payment_line_ids:
            pagamentos.append(line.prepare_bank_payment_line(bank_brcobranca))
        remessa_values = {
            "carteira": str(cnab_config.boleto_wallet),
            "agencia": bank_account_id.bra_number,
            "conta_corrente": int(misc.punctuation_rm(bank_account_id.acc_number)),
            "digito_conta": bank_account_id.acc_number_dig[0],
            "empresa_mae": bank_account_id.partner_id.legal_name[:30],
            "documento_cedente": misc.punctuation_rm(
                bank_account_id.partner_id.cnpj_cpf
            ),
            "pagamentos": pagamentos,
            "sequencial_remessa": sequencial,
        }
        if hasattr(self, f"_prepare_remessa_{bank_brcobranca.name}"):
            bank_method = getattr(self, f"_prepare_remessa_{bank_brcobranca.name}")
            bank_method(remessa_values, cnab_config)
        return remessa_values, bank_brcobranca, cnab_config

    def generate_payment_file(self):
        """Returns (payment file as string, filename)"""
        self.ensure_one()
        cnab_config = self.payment_mode_id.cnab_config_id

        # see remessa fields here:
        # https://github.com/kivanio/brcobranca/blob/master/lib/brcobranca/remessa/base.rb
        # https://github.com/kivanio/brcobranca/tree/master/lib/brcobranca/remessa/cnab240
        # https://github.com/kivanio/brcobranca/tree/master/lib/brcobranca/remessa/cnab400
        # and a test here:
        # https://github.com/kivanio/brcobranca/blob/master/spec/
        # brcobranca/remessa/cnab400/itau_spec.rb

        cnab_type = cnab_config.payment_method_id.code

        # Se não for um caso CNAB deve chamar o super
        if (
            cnab_type not in ("240", "400", "500")
            or cnab_config.cnab_processor != "brcobranca"
        ):
            return super().generate_payment_file()

        # A sequencia sera consumida apenas na confirmacao de envio
        # (generated2uploaded) para evitar gaps e permitir que o usuario
        # edite o numero antes de confirmar. Aqui usamos 0 como placeholder.
        self.file_number = 0

        bank_account_id = self.journal_id.bank_account_id
        bank_brcobranca = get_brcobranca_bank(bank_account_id, cnab_type)

        # Verificar campos que não podem ser usados no CNAB, já é
        # feito ao criar um Modo de Pagamento, porém para evitar
        # erros devido alterações e re-validado aqui
        cnab_config._check_cnab_restriction()

        if cnab_type not in bank_brcobranca.remessa:
            raise ValidationError(
                _(
                    "The CNAB %(cnab_type)s for Bank %(bank_name)s are not implemented "
                    "in BRCobranca.",
                    cnab_type=cnab_type,
                    bank_name=bank_account_id.bank_id.name,
                )
            )

        remessa_values, bank_brcobranca, cnab_config = self._build_remessa_values(
            self.file_number
        )
        remessa = self._get_brcobranca_remessa(
            bank_brcobranca, remessa_values, cnab_type
        )

        return remessa, self.get_file_name(cnab_type)

    def _get_brcobranca_remessa(self, bank_brcobranca, remessa_values, cnab_type):
        content = json.dumps(remessa_values)
        f = open(tempfile.mktemp(), "w")
        f.write(content)
        f.close()
        files = {"data": open(f.name, "rb")}

        brcobranca_api_url = get_brcobranca_api_url(self.env)
        # EX.: "http://boleto_cnab_api:9292/api/remessa"
        brcobranca_service_url = brcobranca_api_url + "/api/remessa"
        _logger.info(
            "Connecting to %s to generate CNAB-REMESSA file for Payment Order %s",
            brcobranca_service_url,
            self.name,
        )
        res = requests.post(
            brcobranca_service_url,
            data={
                "type": DICT_BRCOBRANCA_CNAB_TYPE[cnab_type],
                "bank": bank_brcobranca.name,
            },
            files=files,
            timeout=TIMEOUT,
        )

        if cnab_type == "240" and "R01" in res.text[242:254]:
            #  Todos os header de lote cnab 240 tem conteúdo: R01,
            #  verificar observações G025 e G028 do manual cnab 240 febraban.
            remessa = res.content
        elif cnab_type == "400" and res.text[:3] in ("01R", "DCB"):
            # A remessa 400 não tem um layout padronizado,
            # entretanto a maiorias dos arquivos começa com 01REMESSA,
            # o banco de brasilia começa com DCB...
            # Dúvidas verificar exemplos:
            # https://github.com/kivanio/brcobranca/tree/master/spec/fixtures/remessa
            remessa = res.content
        else:
            raise ValidationError(res.text)

        return remessa

    @staticmethod
    def _patch_cnab_sequence(content, old_seq, new_seq, cnab_type):
        """Update sequencial_remessa in CNAB file content.

        For CNAB 240:
          - Header do Arquivo (linha 1): pos 158-163 (6 dígitos)
          - Header do Lote   (linha 2): pos 185-192 (8 dígitos)
        """
        if not content:
            return content

        def _replace_padded(data, start, length, new_val):
            old_part = data[start : start + length]
            new_part = str(new_val).zfill(length)[:length].encode()
            if old_part != new_part:
                return data[:start] + new_part + data[start + length :]
            return data

        if cnab_type == "240":
            lines = content.split(b"\n")
            if len(lines) >= 1 and len(lines[0]) >= 163:
                lines[0] = _replace_padded(lines[0], 157, 6, new_seq)
            if len(lines) >= 2 and len(lines[1]) >= 192:
                lines[1] = _replace_padded(lines[1], 184, 8, new_seq)
            content = b"\n".join(lines)
        elif cnab_type == "400":
            lines = content.split(b"\n")
            if len(lines) >= 1:
                lines[0] = _replace_padded(lines[0], 393, 6, new_seq)
            content = b"\n".join(lines)

        return content

    def _update_cnab_attachment(self, cnab_type):
        """Patch the CNAB attachment to reflect the current file_number."""
        attachment = self.env["ir.attachment"].search(
            [
                ("res_model", "=", "account.payment.order"),
                ("res_id", "=", self.id),
            ],
            order="create_date desc",
            limit=1,
        )
        if attachment and attachment.datas:
            raw = base64.b64decode(attachment.datas)
            patched = self._patch_cnab_sequence(raw, 0, self.file_number, cnab_type)
            new_filename = self.get_file_name(cnab_type)
            attachment.write(
                {
                    "datas": base64.b64encode(patched),
                    "name": new_filename,
                }
            )
            self.cnab_file = base64.b64encode(patched)
            self.cnab_filename = new_filename

    def write(self, vals):
        result = super().write(vals)
        if "file_number" in vals:
            for record in self:
                cnab_config = record.payment_mode_id.cnab_config_id
                if (
                    cnab_config
                    and cnab_config.cnab_processor == "brcobranca"
                    and record.state == "generated"
                ):
                    record._update_cnab_attachment(
                        cnab_config.payment_method_id.code
                    )
        return result

    def generated2uploaded(self):
        cnab_config = self.payment_mode_id.cnab_config_id
        if (
            cnab_config
            and cnab_config.cnab_processor == "brcobranca"
            and cnab_config.cnab_sequence_id
        ):
            if not self.file_number:
                self.file_number = cnab_config.cnab_sequence_id.next_by_id()

            self._update_cnab_attachment(cnab_config.payment_method_id.code)

        result = super().generated2uploaded()
        for payment_line in self.payment_line_ids:
            if payment_line.move_line_id:
                payment_line.move_line_id.cnab_state = "exported"
        return result

    def get_file_name(self, cnab_type):
        cnab_config = self.payment_mode_id.cnab_config_id
        if cnab_config and cnab_config.bank_id.code_bc == "748":
            month_code = {
                1: "1", 2: "2", 3: "3", 4: "4", 5: "5", 6: "6",
                7: "7", 8: "8", 9: "9", 10: "O", 11: "N", 12: "D",
            }
            context_today = fields.Date.context_today(self)
            month = month_code[context_today.month]
            day = context_today.strftime("%d")
            beneficiary = cnab_config.cnab_company_bank_code.zfill(5)[:5]
            extension = str(self.file_number).zfill(3)
            return f"{beneficiary}{month}{day}.{extension}"
        return super().get_file_name(cnab_type)
