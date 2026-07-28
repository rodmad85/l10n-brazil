from odoo import fields, models, api


class AccountMoveExt(models.Model):
    _inherit = 'account.move'

    financeiro_lancamento = fields.Integer(
        string='Nº Lançamento Financeiro',
        help='Número do lançamento original da planilha',
    )
    financeiro_classificacao = fields.Char(
        string='Classificação Financeiro',
    )
    financeiro_status_planilha = fields.Char(
        string='Status Planilha',
        help='Status original na planilha: Pago, Em Aberto, Previsão',
    )
    financeiro_banco_planilha = fields.Char(
        string='Banco Planilha',
        help='Banco original na planilha',
    )
    financeiro_os = fields.Char(
        string='OS',
        help='Número da Ordem de Serviço',
    )
    financeiro_origem = fields.Selection([
        ('pagar', 'Contas a Pagar'),
        ('receber', 'Contas a Receber'),
    ], string='Origem Financeiro')
