import base64
import gzip
import json
import logging
import re

import requests
from erpbrasil.assinatura.assinatura import Assinatura
from erpbrasil.assinatura.certificado import ArquivoCertificado
from erpbrasil.base import misc
from lxml import etree

from odoo import _, fields, models
from odoo.exceptions import UserError

from ..constants.nfse import NFSE_NACIONAL_AMBIENTES

_logger = logging.getLogger(__name__)

NFSE_NS = "http://www.sped.fazenda.gov.br/nfse"
DSIG_NS = "http://www.w3.org/2000/09/xmldsig#"


class NfseNacional(models.AbstractModel):
    _name = "l10n_br_nfse.nfse_nacional"
    _description = "NFSe Nacional API Client"

    def _get_environment_urls(self, company):
        env = company.nfse_environment
        return NFSE_NACIONAL_AMBIENTES.get(env, NFSE_NACIONAL_AMBIENTES["2"])

    def _build_dps_id(self, company, document):
        cnpj = misc.punctuation_rm(company.partner_id.cnpj_cpf)
        tp_insc = "2" if company.partner_id.is_company else "1"
        if tp_insc == "1":
            cnpj = cnpj.zfill(14)
        serie = str(document.document_serie_id.code or "00001").zfill(5)[:5]
        n_dps = str(document.rps_number or "1").zfill(15)[:15]
        ibge = str(int(company.partner_id.city_id.ibge_code)).zfill(7)
        return "DPS" + ibge + tp_insc + cnpj + serie + n_dps

    def _build_dps_xml(self, document):
        company = document.company_id
        partner = document.partner_id
        prestador = company.partner_id
        line = document.fiscal_line_ids[0] if document.fiscal_line_ids else None

        dps_id = self._build_dps_id(company, document)

        NS = NFSE_NS
        nsmap = {None: NS}

        inf_dps = etree.SubElement(
            etree.Element("{%s}DPS" % NS, nsmap=nsmap, versao="1.01"),
            "{%s}infDPS" % NS,
            Id=dps_id,
        )

        def e(tag, text=None, parent=inf_dps):
            el = etree.SubElement(parent, "{%s}%s" % (NS, tag))
            if text is not None:
                el.text = str(text)
            return el

        e("tpAmb", "2" if company.nfse_environment == "2" else "1")

        dt = fields.Datetime.context_timestamp(
            document, fields.Datetime.from_string(document.document_date)
        )
        e("dhEmi", dt.strftime("%Y-%m-%dT%H:%M:%S-03:00"))
        e("verAplic", "l10n_br_nfse-16.0")
        e("serie", str(document.document_serie_id.code or "00001").zfill(5)[:5])
        e("nDPS", str(document.rps_number or "1").zfill(15)[:15])

        compet = document.date_in_out or document.document_date
        if compet:
            dt_comp = fields.Datetime.context_timestamp(document, compet)
            e("dCompet", dt_comp.strftime("%Y-%m-%d"))
        else:
            e("dCompet", dt.strftime("%Y-%m-%d"))

        e("tpEmit", "1")

        e("cLocEmi", str(int(prestador.city_id.ibge_code)).zfill(7))

        prest = etree.SubElement(inf_dps, "{%s}prest" % NS)

        cnpj_prest = misc.punctuation_rm(prestador.cnpj_cpf)
        etree.SubElement(prest, "{%s}CNPJ" % NS).text = cnpj_prest
        if prestador.l10n_br_im_code:
            etree.SubElement(prest, "{%s}IM" % NS).text = misc.punctuation_rm(
                prestador.l10n_br_im_code
            )
        etree.SubElement(prest, "{%s}xNome" % NS).text = (
            prestador.legal_name or prestador.name or ""
        )[:150]

        end_prest = etree.SubElement(prest, "{%s}end" % NS)
        end_nac = etree.SubElement(end_prest, "{%s}endNac" % NS)
        c_mun = str(int(prestador.city_id.ibge_code)).zfill(7)
        etree.SubElement(end_nac, "{%s}cMun" % NS).text = c_mun
        cep = misc.punctuation_rm(prestador.zip or "00000000").zfill(8)[:8]
        etree.SubElement(end_nac, "{%s}CEP" % NS).text = cep
        etree.SubElement(end_prest, "{%s}xLgr" % NS).text = (
            prestador.street_name or prestador.street or ""
        )[:255]
        etree.SubElement(end_prest, "{%s}nro" % NS).text = (
            prestador.street_number or "S/N"
        )[:60]
        if prestador.street2:
            etree.SubElement(end_prest, "{%s}xCpl" % NS).text = prestador.street2[:156]
        etree.SubElement(end_prest, "{%s}xBairro" % NS).text = (
            prestador.district or ""
        )[:60]
        if prestador.phone:
            etree.SubElement(prest, "{%s}fone" % NS).text = re.sub(
                r"[^0-9]", "", prestador.phone or ""
            )[:20]
        if prestador.email:
            etree.SubElement(prest, "{%s}email" % NS).text = prestador.email[:80]

        reg_trib = etree.SubElement(prest, "{%s}regTrib" % NS)
        tax_framework = company.tax_framework
        if tax_framework and tax_framework in ("3", "4", "5"):
            e = etree.SubElement(reg_trib, "{%s}opSimpNac" % NS)
            if tax_framework == "5":
                e.text = "2"
            else:
                e.text = "3"
        else:
            etree.SubElement(reg_trib, "{%s}opSimpNac" % NS).text = "1"
        etree.SubElement(reg_trib, "{%s}regEspTrib" % NS).text = (
            document.taxation_special_regime or "0"
        )

        toma = etree.SubElement(inf_dps, "{%s}toma" % NS)
        if partner.is_company:
            cnpj_tom = misc.punctuation_rm(partner.cnpj_cpf)
            if partner.country_id.id != company.country_id.id:
                cnpj_tom = "99999999999999"
            etree.SubElement(toma, "{%s}CNPJ" % NS).text = cnpj_tom
        else:
            cpf_tom = misc.punctuation_rm(partner.cnpj_cpf)
            if partner.country_id.id != company.country_id.id:
                cpf_tom = "99999999999"
            etree.SubElement(toma, "{%s}CPF" % NS).text = cpf_tom

        etree.SubElement(toma, "{%s}xNome" % NS).text = (
            partner.legal_name or partner.name or "TOMADOR"
        )[:150]

        end_toma = etree.SubElement(toma, "{%s}end" % NS)
        end_nac_t = etree.SubElement(end_toma, "{%s}endNac" % NS)
        if partner.city_id:
            etree.SubElement(end_nac_t, "{%s}cMun" % NS).text = str(
                int(partner.city_id.ibge_code)
            ).zfill(7)
        else:
            etree.SubElement(end_nac_t, "{%s}cMun" % NS).text = "9999999"
        cep_tom = misc.punctuation_rm(partner.zip or "00000000").zfill(8)[:8]
        etree.SubElement(end_nac_t, "{%s}CEP" % NS).text = cep_tom
        etree.SubElement(end_toma, "{%s}xLgr" % NS).text = (
            partner.street_name or partner.street or ""
        )[:255]
        etree.SubElement(end_toma, "{%s}nro" % NS).text = (
            partner.street_number or "S/N"
        )[:60]
        if partner.street2:
            etree.SubElement(end_toma, "{%s}xCpl" % NS).text = partner.street2[:156]
        etree.SubElement(end_toma, "{%s}xBairro" % NS).text = (
            partner.district or ""
        )[:60]
        if partner.email:
            etree.SubElement(toma, "{%s}email" % NS).text = partner.email[:80]

        serv = etree.SubElement(inf_dps, "{%s}serv" % NS)
        etree.SubElement(serv, "{%s}xDescServ" % NS).text = (
            line.name if line and line.name else ""
        )[:1000]
        if line and line.nbs_id:
            etree.SubElement(serv, "{%s}cNBS" % NS).text = misc.punctuation_rm(
                line.nbs_id.code
            )[:9]
        if line and line.national_taxation_code_id:
            etree.SubElement(serv, "{%s}cTribNac" % NS).text = (
                line.national_taxation_code_id.code or ""
            )[:6]
        if line and line.service_type_id:
            etree.SubElement(serv, "{%s}cServMun" % NS).text = line.service_type_id.code.replace(
                ".", ""
            )[:20]
        if line and line.cnae_id:
            etree.SubElement(serv, "{%s}cCNAE" % NS).text = misc.punctuation_rm(
                line.cnae_id.code
            )[:7]

        valores = etree.SubElement(inf_dps, "{%s}valores" % NS)
        etree.SubElement(valores, "{%s}vServ" % NS).text = "%.2f" % round(
            document.amount_price_gross, 2
        )
        etree.SubElement(valores, "{%s}vDescIncond" % NS).text = "%.2f" % round(
            line.discount_value if line else 0, 2
        )
        ded_val = line.fiscal_deductions_value if line else 0
        etree.SubElement(valores, "{%s}vDed" % NS).text = "%.2f" % round(ded_val, 2)

        return dps_id, inf_dps

    def _sign_dps(self, dps_element, dps_id, company):
        certificado = company._get_br_ecertificate()
        assinatura = Assinatura(certificado)
        signed = assinatura.assina_xml2(dps_element, dps_id, getchildren=False)
        return signed.encode("utf-8") if isinstance(signed, str) else signed

    def _compress_and_encode(self, xml_bytes):
        compressed = gzip.compress(xml_bytes)
        return base64.b64encode(compressed).decode("utf-8")

    def _decode_and_decompress(self, b64_data):
        compressed = base64.b64decode(b64_data)
        return gzip.decompress(compressed)

    def _parse_nfse_response(self, nfse_b64):
        xml_bytes = self._decode_and_decompress(nfse_b64)
        root = etree.fromstring(xml_bytes)
        NS = NFSE_NS
        def t(tag):
            return "{%s}%s" % (NS, tag)

        inf = root.find(t("infNFSe"))
        if inf is None:
            return {}
        result = {}
        n_nfse = inf.findtext(t("nNFSe"))
        if n_nfse:
            result["nNFSe"] = n_nfse
        cvc = inf.findtext(t("codigoVerificacao"))
        if cvc:
            result["codigoVerificacao"] = cvc
        for field in ("cStat", "dhProc", "nDFSe",
                      "xLocEmi", "xLocPrestacao", "xTribNac",
                      "xNBS"):
            val = inf.findtext(t(field))
            if val:
                result[field] = val
        emit = inf.find(t("emit"))
        if emit is not None:
            for field in ("CNPJ", "CPF", "IM", "xNome"):
                el = emit.find(t(field))
                if el is not None:
                    result["emit_" + field] = el.text
        chave = inf.get("Id", "")
        if chave:
            result["chaveAcesso"] = chave
        return result

    def _build_dps_envelope(self, dps_element):
        NS = NFSE_NS
        dps_part = dps_element if dps_element.tag == "{%s}DPS" % NS else dps_element.getparent()
        return etree.tostring(dps_part, xml_declaration=True, encoding="UTF-8")

    def send_dps(self, document):
        company = document.company_id
        certificado = company._get_br_ecertificate()
        urls = self._get_environment_urls(company)

        dps_id, inf_dps = self._build_dps_xml(document)
        signed_xml = self._sign_dps(inf_dps, dps_id, company)
        dps_b64 = self._compress_and_encode(signed_xml)

        payload = {"dps": dps_b64}
        _logger.debug("Enviando DPS NFSe Nacional: %s", payload["dps"][:100])

        with ArquivoCertificado(certificado, "w") as (key_path, cert_path):
            try:
                response = requests.post(
                    urls["adn"] + "/nfse",
                    json=payload,
                    cert=(key_path, cert_path),
                    timeout=60,
                )
                return self._handle_response(response, document)
            except requests.exceptions.RequestException as e:
                raise UserError(
                    _("Erro de conexão com a NFSe Nacional: %s") % str(e)
                )

    def consult_dps(self, document):
        company = document.company_id
        if not document.nfse_nacional_chave_acesso:
            return {"status": "sem_chave"}
        urls = self._get_environment_urls(company)
        certificado = company._get_br_ecertificate()

        with ArquivoCertificado(certificado, "w") as (key_path, cert_path):
            try:
                response = requests.get(
                    urls["adn"] + "/nfse/" + document.nfse_nacional_chave_acesso,
                    cert=(key_path, cert_path),
                    timeout=60,
                )
                return self._handle_response(response, document)
            except requests.exceptions.RequestException as e:
                raise UserError(
                    _("Erro de conexão com a NFSe Nacional: %s") % str(e)
                )

    def cancel_dps(self, document):
        company = document.company_id
        if not document.nfse_nacional_chave_acesso:
            raise UserError(_("Chave de acesso da NFS-e não encontrada para cancelamento."))
        urls = self._get_environment_urls(company)
        certificado = company._get_br_ecertificate()

        evento_xml = self._build_cancelamento_evento(document)
        evento_b64 = self._compress_and_encode(evento_xml.encode("utf-8"))
        payload = {"evento": evento_b64}

        with ArquivoCertificado(certificado, "w") as (key_path, cert_path):
            try:
                response = requests.post(
                    urls["adn"]
                    + "/nfse/"
                    + document.nfse_nacional_chave_acesso
                    + "/eventos",
                    json=payload,
                    cert=(key_path, cert_path),
                    timeout=60,
                )
                return self._handle_response(response, document)
            except requests.exceptions.RequestException as e:
                raise UserError(
                    _("Erro de conexão com a NFSe Nacional: %s") % str(e)
                )

    def _build_cancelamento_evento(self, document):
        NS = NFSE_NS
        nsmap = {None: NS}
        just = document.cancel_reason or "Cancelamento solicitado"
        chave = document.nfse_nacional_chave_acesso

        root = etree.Element("{%s}pedRegEvento" % NS, nsmap=nsmap, versao="1.01")
        inf_evento = etree.SubElement(root, "{%s}infEvento" % NS, Id="PRE" + chave + "01")
        etree.SubElement(inf_evento, "{%s}verAplic" % NS).text = "l10n_br_nfse-16.0"
        etree.SubElement(inf_evento, "{%s}ambGer" % NS).text = (
            "2" if document.company_id.nfse_environment == "2" else "1"
        )
        etree.SubElement(inf_evento, "{%s}nSeqEvento" % NS).text = "001"
        import datetime
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        etree.SubElement(inf_evento, "{%s}dhProc" % NS).text = now_utc.strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        etree.SubElement(inf_evento, "{%s}nDFSe" % NS).text = "0"
        det_evento = etree.SubElement(inf_evento, "{%s}detEvento" % NS)
        etree.SubElement(det_evento, "{%s}cEvento" % NS).text = "110110"
        etree.SubElement(det_evento, "{%s}xJust" % NS).text = just[:255]
        return etree.tostring(root, xml_declaration=True, encoding="UTF-8").decode("utf-8")

    def _handle_response(self, response, document):
        if response.status_code in (200, 201):
            data = response.json()
            _logger.debug("Resposta NFSe Nacional: %s", json.dumps(data, indent=2))

            result = {"protocolo": data.get("protocolo")}

            nfse_b64 = data.get("nfse")
            if nfse_b64:
                try:
                    nfse_data = self._parse_nfse_response(nfse_b64)
                    result.update(nfse_data)
                    result["status"] = "autorizado"
                    chave = nfse_data.get("chaveAcesso")
                    if chave:
                        urls = self._get_environment_urls(document.company_id)
                        result["urlDANFSe"] = urls["danfse"] + "/" + chave
                except Exception as e:
                    _logger.warning("Erro ao decodificar NFS-e: %s", e)
                    result["status"] = "processando"
            else:
                result["status"] = "processando"

            return result

        elif response.status_code in (400, 422):
            try:
                data = response.json()
                msg = data.get("mensagem", data.get("erro", str(response.text)))
            except (ValueError, TypeError):
                msg = response.text
            document.edoc_error_message = msg
            raise UserError(_("Erro NFSe Nacional: %s") % msg)

        elif response.status_code == 202:
            return {"status": "processando"}

        elif response.status_code == 401:
            raise UserError(
                _("Certificado digital não autorizado para NFSe Nacional.")
            )

        else:
            raise UserError(
                _("Erro inesperado NFSe Nacional (HTTP %s): %s")
                % (response.status_code, response.text)
            )
