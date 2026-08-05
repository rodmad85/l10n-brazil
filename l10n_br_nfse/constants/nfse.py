# Copyright 2019 KMEE
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

NFSE_ENVIRONMENTS = [("1", "Produção"), ("2", "Homologação")]


NFSE_ENVIRONMENT_DEFAULT = "2"


NFSE_VERSION = [
    ("municipal", "Municipal (SOAP)"),
    ("nacional", "Nacional (REST API)"),
]

NFSE_VERSION_DEFAULT = "municipal"


OPERATION_NATURE = [
    ("1", "Tributação no município"),
    ("2", "Tributação fora do município"),
    ("3", "Isenção"),
    ("4", "Imune"),
    ("5", "Exigibilidade suspensa por decisão judicial"),
    ("6", "Exigibilidade suspensa por procedimento administrativo"),
]


RPS_TYPE = [
    ("1", "Recibo provisório de Serviços"),
    ("2", "RPS Nota Fiscal Conjugada (Mista)"),
    ("3", "Cupom"),
]


TAXATION_SPECIAL_REGIME = [
    ("1", "Microempresa Municipal"),
    ("2", "Estimativa"),
    ("3", "Sociedade de Profissionais"),
    ("4", "Cooperativa"),
    ("5", "Microempresario Individual(MEI)"),
    ("6", "Microempresario e Empresa de Pequeno Porte(ME EPP)"),
]


ISSQN_TO_TRIBUTACAO_ISS = {
    "1": "1",  # Exigível → Operação tributável
    "2": "4",  # Não incidência → Não Incidência
    "3": "4",  # Isenção → Não Incidência
    "4": "3",  # Exportação → Exportação de serviço
    "5": "2",  # Imunidade → Imunidade
    "6": "1",  # Suspensa (Judicial) → Operação tributável
    "7": "1",  # Suspensa (Administrativo) → Operação tributável
}


NFSE_NACIONAL_AMBIENTES = {
    "1": {
        "nome": "Produção",
        "adn": "https://adn.nfse.gov.br",
        "cnc": "https://adn.nfse.gov.br/cnc",
        "sefin": "https://sefin.nfse.gov.br",
        "danfse": "https://adn.nfse.gov.br/danfse",
    },
    "2": {
        "nome": "Homologação",
        "adn": "https://adn.producaorestrita.nfse.gov.br",
        "cnc": "https://adn.producaorestrita.nfse.gov.br/cnc",
        "sefin": "https://sefin.producaorestrita.nfse.gov.br",
        "danfse": "https://adn.producaorestrita.nfse.gov.br/danfse",
    },
}

DPS_VERSAO = "1.01"

TIPO_EMISSAO_DPS = [
    ("1", "Aplicativo do contribuinte (Web Service)"),
    ("2", "Aplicativo disponibilizado pelo fisco (Web)"),
    ("3", "Aplicativo disponibilizado pelo fisco (App)"),
]

REGIME_TRIBUTACAO_DPS = [
    ("1", "Simples Nacional"),
    ("2", "Regime Normal"),
    ("3", "MEI"),
]

SITUACAO_DPS = [
    ("1", "Normal"),
    ("2", "Cancelada"),
]

INDICADOR_OPERACAO_DPS = [
    ("1", "Operação Interna"),
    ("2", "Operação Interestadual"),
    ("3", "Operação com Exterior"),
]
