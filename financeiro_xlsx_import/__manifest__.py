# Copyright 2026 Madureira Ind. e Com.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    'name': 'Importação Financeiro XLSX',
    'description': """
        Importação do planilha FINANCEIRO 2026 para Odoo.
        Importa Contas a Pagar, Contas a Receber e Plano de Contas.""",
    'version': '16.0.1.0.0',
    'license': 'AGPL-3',
    'author': 'Madureira Ind. e Com.',
    'website': 'www.madureira.ind.br',
    'depends': [
        'account',
        'base',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/account_account_data.xml',
        'wizard/financeiro_import_wizard_view.xml',
        'views/menu.xml',
    ],
    'demo': [],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
