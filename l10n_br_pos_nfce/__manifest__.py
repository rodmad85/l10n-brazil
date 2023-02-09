# Copyright 2022 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "L10n Br Pos Nfce",
    "summary": """
        NFC-E no Ponto de Venda""",
    "version": "14.0.1.0.0",
    "license": "AGPL-3",
    "author": "KMEE,Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/l10n-brazil",
    "development_status": "Alpha",
    "maintainers": ["mileo", "sadamo", "gabrielcardoso21", "lfdivino"],
    "depends": [
        "l10n_br_pos",
        "l10n_br_account_nfe",
    ],
    "data": [
        "views/pos_payment_method.xml",
        "views/pos_template.xml",
        "views/pos_config_view.xml",
    ],
    "demo": [],
    "installable": True,
}
