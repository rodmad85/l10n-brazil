from odoo import fields, models, api


class AccountAccountExt(models.Model):
    _inherit = 'account.account'

    financeiro_classificacao = fields.Char(
        string='Classificação Financeiro',
        help='Classificação original da planilha financeira',
    )
    financeiro_sub1 = fields.Char(
        string='Sub Classificação 1',
    )
    financeiro_sub2 = fields.Char(
        string='Sub Classificação 2',
    )
    financeiro_sub3 = fields.Char(
        string='Sub Classificação 3',
    )
