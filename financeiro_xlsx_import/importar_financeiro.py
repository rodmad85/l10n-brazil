#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de Importação Financeiro XLSX → Odoo via XML-RPC
Uso: python3 importar_financeiro.py [--arquivo CAMINHO] [--senha SENHA] [--url URL] [--banco BANCO] [--usuario USUARIO] [--senha-odoo SENHA]

Exemplo:
  python3 importar_financeiro.py
  python3 importar_financeiro.py --arquivo "FINANCEIRO 2026 - MADUREIRA.xlsb" --url https://app.madureira.ind.br --banco mad2 --usuario admin --senha-odoo admin
"""

import argparse
import xmlrpc.client
import ssl
import sys
import os
import io
import json
from datetime import datetime, timedelta

try:
    import pandas as pd
    import msoffcrypto
except ImportError:
    print("ERRO: Dependências não instaladas.")
    print("Execute: pip install pandas openpyxl pyxlsb msoffcrypto-tool")
    sys.exit(1)

# ============================================================
# CONFIGURAÇÕES PADRÃO
# ============================================================
URL_ODOO = "https://app.madureira.ind.br"
DB_NAME = "mad2"
USUARIO = "rodrigo@madureira.ind.br"
SENHA_ODOO = ""  # Preencher ou usar --senha-odoo
ARQUIVO_PADRAO = "FINANCEIRO 2026 - MADUREIRA.xlsb"
SENHA_XLSX = "A123d"
ODOO_EPOCH = datetime(1899, 12, 30)

CLASSIFICACAO_MAP = {
    'DESPESAS BANCARIAS': {'code': '5.1.01', 'tipo': 'expense'},
    'COMPRAS PRODUTIVAS': {'code': '1.2.01', 'tipo': 'asset'},
    'DESPESAS FIXAS': {'code': '5.2.01', 'tipo': 'expense'},
    'EMPRESTIMOS': {'code': '2.1.01', 'tipo': 'liability'},
    'FUNCIONARIOS': {'code': '5.3.01', 'tipo': 'expense'},
    'INVESTIMENTO': {'code': '1.3.01', 'tipo': 'asset'},
    'TRANSFERENCIAS': {'code': '9.1.01', 'tipo': 'equity'},
    'PAGAMENTO FATURA CARTAO CREDITO': {'code': '2.2.01', 'tipo': 'liability'},
    'PARTICULAR': {'code': '5.4.01', 'tipo': 'expense'},
    'IMPOSTOS': {'code': '5.5.01', 'tipo': 'expense'},
    'ATIVO': {'code': '1.1.01', 'tipo': 'asset'},
    'DESPESAS VARIAVEIS': {'code': '5.6.01', 'tipo': 'expense'},
    'SALDO INICIAL': {'code': '9.2.01', 'tipo': 'equity'},
    'RECEITAS': {'code': '4.1.01', 'tipo': 'income'},
}

BANCO_JOURNAL = {
    'ITAU': {'name': 'Banco Itaú', 'code': 'ITAU'},
    'SICREDI': {'name': 'Banco Sicredi', 'code': 'SICR'},
    'CAIXA': {'name': 'Caixa Econômica', 'code': 'CAIX'},
    'DINHEIRO': {'name': 'Dinheiro', 'code': 'CASH'},
    'DAYCOVAL': {'name': 'Daycoval', 'code': 'DAYC'},
    'NU BANK': {'name': 'Nubank', 'code': 'NUBK'},
}

TIPO_USER_MAP = {
    'expense': 'account.data_account_type_expenses',
    'income': 'account.data_account_type_revenue',
    'asset': 'account.data_account_type_asset',
    'liability': 'account.data_account_type_liability',
    'equity': 'account.data_account_type_equity',
}


class OdooXMLRPC:
    def __init__(self, url, db, user, password):
        self.url = url
        self.db = db
        self.user = user
        self.password = password
        self.uid = None

        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

        self.common = xmlrpc.client.ServerProxy(
            f'{url}/xmlrpc/2/common', context=context
        )
        self.models = xmlrpc.client.ServerProxy(
            f'{url}/xmlrpc/2/object', context=context
        )

    def authenticate(self):
        self.uid = self.common.authenticate(self.db, self.user, self.password, {})
        if not self.uid:
            raise Exception(f"Falha na autenticação. Verifique usuário/senha para {self.db}")
        print(f"Autenticado com sucesso! UID: {self.uid}")
        return self.uid

    def exec_kw(self, model, method, args=None, kwargs=None):
        args = args or []
        kwargs = kwargs or {}
        return self.models.execute_kw(
            self.db, self.uid, self.password,
            model, method, args, kwargs
        )

    def search(self, model, domain, limit=None):
        kwargs = {'domain': domain}
        if limit:
            kwargs['limit'] = limit
        return self.exec_kw(model, 'search', **kwargs)

    def read(self, model, ids, fields=None):
        kwargs = {'ids': ids}
        if fields:
            kwargs['fields'] = fields
        return self.exec_kw(model, 'read', **kwargs)

    def create(self, model, vals):
        return self.exec_kw(model, 'create', [vals])

    def write(self, model, ids, vals):
        return self.exec_kw(model, 'write', [ids, vals])


def decrypt_xlsx(filepath, password):
    print(f"Descriptografando {filepath}...")
    with open(filepath, 'rb') as f:
        ms_file = msoffcrypto.OfficeFile(f)
        ms_file.load_key(password=password)
        decrypted = io.BytesIO()
        ms_file.decrypt(decrypted)
        decrypted.seek(0)
    print("Arquivo descriptografado com sucesso!")
    return decrypted


def excel_serial_to_date(serial):
    if pd.isna(serial) or serial == 0:
        return None
    try:
        return ODOO_EPOCH + timedelta(days=int(serial))
    except (ValueError, TypeError):
        return None


def importar_plano_contas(odoo, decrypted, log):
    log.append("=== IMPORTAÇÃO PLANO DE CONTAS ===")
    df = pd.read_excel(decrypted, sheet_name='Classificacao', engine='pyxlsb')

    user_type_refs = {}
    for tipo, ref_path in TIPO_USER_MAP.items():
        try:
            ref_id = odoo.exec_kw('ir.model.data', 'xmlid_to_res_id', [ref_path])
            user_type_refs[tipo] = ref_id
        except Exception:
            user_type_refs[tipo] = False

    account_type_ref = odoo.exec_kw('ir.model.data', 'xmlid_to_res_id', ['account.data_account_type_other'])

    created = 0
    updated = 0

    for _, row in df.iterrows():
        classif = str(row.get('CLASSIFICAÇÃO', '')).strip()
        sub1 = str(row.get('Sub Classificação 1', '')).strip()
        sub2 = str(row.get('Sub Classificação 2', '')).strip()
        sub3 = str(row.get('Sub Classificação 3', '')).strip()

        if not classif or classif == 'nan':
            continue

        base = CLASSIFICACAO_MAP.get(classif)
        if not base:
            log.append(f"  AVISO: '{classif}' sem mapeamento")
            continue

        code = base['code']
        name_parts = [classif]
        if sub1 and sub1 != 'nan':
            name_parts.append(sub1)
        if sub2 and sub2 != 'nan':
            name_parts.append(sub2)
        if sub3 and sub3 != 'nan':
            name_parts.append(sub3)

        account_name = ' / '.join(name_parts)

        if sub1 and sub1 != 'nan':
            suffix = sub1[:3].upper().replace(' ', '').replace('/', '')
            full_code = f'{code}.{suffix}'
        else:
            full_code = code
        full_code = full_code[:20]

        existing = odoo.search('account.account', [
            ('financeiro_classificacao', '=', classif),
            ('financeiro_sub1', '=', sub1 if sub1 != 'nan' else False),
            ('financeiro_sub2', '=', sub2 if sub2 != 'nan' else False),
        ], limit=1)

        vals = {
            'code': full_code,
            'name': account_name,
            'financeiro_classificacao': classif,
            'financeiro_sub1': sub1 if sub1 != 'nan' else '',
            'financeiro_sub2': sub2 if sub2 != 'nan' else '',
            'financeiro_sub3': sub3 if sub3 != 'nan' else '',
        }

        ut = user_type_refs.get(base['tipo'])
        if ut:
            vals['user_type_id'] = ut

        if existing:
            odoo.write('account.account', existing, vals)
            updated += 1
        else:
            odoo.create('account.account', vals)
            created += 1

    log.append(f"  Plano de Contas: {created} criados, {updated} atualizados")
    return created, updated


def importar_lancamentos(odoo, df, origem, journal_type, log):
    log.append(f"=== IMPORTAÇÃO {origem.upper()} ===")
    log.append(f"  Total de linhas: {len(df)}")

    journals = {}
    accounts_cache = {}
    partners_cache = {}

    journal_refs = odoo.search('account.journal', [('type', '=', journal_type)])
    default_journal = journal_refs[0] if journal_refs else False

    created = 0
    skipped = 0

    for idx, row in df.iterrows():
        try:
            data_val = row.get('DATA')
            classif = str(row.get('CLASSIFICAÇÃO', '')).strip()
            historico = str(row.get('HISTÓRICOS ', row.get('HISTÓRICOS', ''))).strip()
            valor = row.get('Valor', 0)
            status = str(row.get('Status', '')).strip()
            banco = str(row.get('Banco', '')).strip()
            lancamento = row.get('Numero do Lançamento', 0)
            doc = str(row.get('DOCTO.', '')).strip()
            os_num = str(row.get('OS', '')).strip()
            sub1 = str(row.get('Sub Classificação 1', '')).strip()
            sub2 = str(row.get('Sub Classificação 2', '')).strip()
            parcela = row.get('Parcela', 0)
            total_parcelas = row.get('Total de Parcelas', 0)
            observacao = str(row.get('Observação', '')).strip()

            data_date = excel_serial_to_date(data_val)
            if not data_date:
                skipped += 1
                continue

            if pd.isna(valor) or valor == 0:
                skipped += 1
                continue

            lancamento_int = int(lancamento) if not pd.isna(lancamento) else 0

            existing = odoo.search('account.move', [
                ('financeiro_lancamento', '=', lancamento_int),
                ('financeiro_origem', '=', origem),
            ], limit=1)
            if existing:
                skipped += 1
                continue

            base = CLASSIFICACAO_MAP.get(classif, {'code': '9.9.99', 'tipo': 'expense'})

            if origem == 'pagar':
                acc_type_ref = 'account.data_account_type_expenses'
                contra_ref = 'account.data_account_type_payable'
            else:
                acc_type_ref = 'account.data_account_type_revenue'
                contra_ref = 'account.data_account_type_receivable'

            acc_type_id = odoo.exec_kw('ir.model.data', 'xmlid_to_res_id', [acc_type_ref])
            contra_type_id = odoo.exec_kw('ir.model.data', 'xmlid_to_res_id', [contra_ref])

            if classif not in accounts_cache:
                accs = odoo.search('account.account', [
                    ('financeiro_classificacao', '=', classif),
                ], limit=1)
                if not accs:
                    accs = odoo.search('account.account', [
                        ('user_type_id', '=', acc_type_id),
                        ('code', 'like', base['code'][:5]),
                    ], limit=1)
                accounts_cache[classif] = accs[0] if accs else False

            main_account = accounts_cache.get(classif)
            if not main_account:
                all_accs = odoo.search('account.account', [('user_type_id', '=', acc_type_id)], limit=1)
                main_account = all_accs[0] if all_accs else False

            contra_accounts = odoo.search('account.account', [('user_type_id', '=', contra_type_id)], limit=1)
            contra_account = contra_accounts[0] if contra_accounts else main_account

            partner_name = historico if historico and historico != 'nan' else classif
            if partner_name not in partners_cache:
                pranks = 1 if origem == 'pagar' else 0
                cranks = 1 if origem == 'receber' else 0
                p = odoo.search('res.partner', [('name', '=', partner_name)], limit=1)
                if not p:
                    p = odoo.create('res.partner', {
                        'name': partner_name,
                        'supplier_rank': pranks,
                        'customer_rank': cranks,
                    })
                partners_cache[partner_name] = p
            partner_id = partners_cache[partner_name]

            if banco and banco != 'nan' and banco in BANCO_JOURNAL:
                bj = BANCO_JOURNAL[banco]
                if banco not in journals:
                    j = odoo.search('account.journal', [('code', '=', bj['code'])], limit=1)
                    if not j:
                        j = odoo.create('account.journal', {
                            'name': bj['name'],
                            'code': bj['code'],
                            'type': 'bank',
                        })
                    journals[banco] = j[0] if isinstance(j, list) else j
                journal_id = journals[banco]
            else:
                journal_id = default_journal

            ref_parts = []
            if doc and doc != 'nan':
                ref_parts.append(doc)
            if parcela and parcela > 0:
                try:
                    ref_parts.append(f'{int(parcela)}/{int(total_parcelas)}')
                except (ValueError, TypeError):
                    pass
            ref = ' - '.join(ref_parts) if ref_parts else (historico[:50] if historico and historico != 'nan' else classif)

            narration = f"Classificação: {classif}"
            if sub1 and sub1 != 'nan':
                narration += f" / {sub1}"
            if sub2 and sub2 != 'nan':
                narration += f" / {sub2}"
            if os_num and os_num != 'nan':
                narration += f"\nOS: {os_num}"
            if observacao and observacao != 'nan':
                narration += f"\nObs: {observacao}"

            hist_name = (historico[:120] if historico and historico != 'nan' else classif)

            if origem == 'pagar':
                debit_main = abs(valor) if valor < 0 else 0
                credit_main = abs(valor) if valor > 0 else 0
                debit_contra = abs(valor) if valor > 0 else 0
                credit_contra = abs(valor) if valor < 0 else 0
            else:
                debit_main = abs(valor) if valor > 0 else 0
                credit_main = abs(valor) if valor < 0 else 0
                debit_contra = abs(valor) if valor < 0 else 0
                credit_contra = abs(valor) if valor > 0 else 0

            if contra_account == main_account:
                credit_contra = 0
                debit_contra = 0

            line1 = {
                'name': hist_name,
                'account_id': contra_account if origem == 'pagar' else main_account,
                'partner_id': partner_id,
                'debit': debit_contra if origem == 'pagar' else debit_main,
                'credit': credit_contra if origem == 'pagar' else credit_main,
            }
            line2 = {
                'name': hist_name,
                'account_id': main_account,
                'partner_id': partner_id,
                'debit': debit_main if origem == 'pagar' else 0,
                'credit': credit_main if origem == 'pagar' else 0,
            }

            if origem == 'receber':
                line1 = {
                    'name': hist_name,
                    'account_id': contra_account,
                    'partner_id': partner_id,
                    'debit': 0,
                    'credit': abs(valor) if valor > 0 else 0,
                }
                line2 = {
                    'name': hist_name,
                    'account_id': main_account,
                    'partner_id': partner_id,
                    'debit': abs(valor) if valor > 0 else 0,
                    'credit': 0,
                }
                if valor < 0:
                    line1['debit'] = abs(valor)
                    line1['credit'] = 0
                    line2['debit'] = 0
                    line2['credit'] = abs(valor)

            move_vals = {
                'move_type': 'entry',
                'date': data_date.strftime('%Y-%m-%d'),
                'ref': ref[:100] if ref else classif,
                'journal_id': journal_id,
                'narration': narration,
                'line_ids': [(0, 0, line1), (0, 0, line2)],
                'financeiro_lancamento': lancamento_int,
                'financeiro_classificacao': classif,
                'financeiro_status_planilha': status if status != 'nan' else '',
                'financeiro_banco_planilha': banco if banco != 'nan' else '',
                'financeiro_os': os_num if os_num != 'nan' else '',
                'financeiro_origem': origem,
            }

            move_id = odoo.create('account.move', move_vals)

            if status == 'Pago' and move_id:
                try:
                    odoo.exec_kw('account.move', 'action_post', [move_id])
                except Exception:
                    pass

            created += 1

        except Exception as e:
            skipped += 1
            if skipped <= 5:
                log.append(f"  ERRO linha {idx}: {e}")
            continue

        if (created + skipped) % 100 == 0:
            print(f"  Processado: {created + skipped}/{len(df)} (criados: {created}, pulados: {skipped})")

    log.append(f"  {origem}: {created} lançamentos criados, {skipped} pulados/erros")
    return created, skipped


def main():
    parser = argparse.ArgumentParser(description='Importar Financeiro XLSX para Odoo')
    parser.add_argument('--arquivo', default=ARQUIVO_PADRAO, help='Caminho do arquivo XLSX/XLSB')
    parser.add_argument('--senha', default=SENHA_XLSX, help='Senha do arquivo')
    parser.add_argument('--url', default=URL_ODOO, help='URL do Odoo')
    parser.add_argument('--banco', default=DB_NAME, help='Nome do banco de dados')
    parser.add_argument('--usuario', default=USUARIO, help='Usuário do Odoo')
    parser.add_argument('--senha-odoo', default=SENHA_ODOO, help='Senha do Odoo')
    parser.add_argument('--apenas-pagar', action='store_true', help='Importar apenas contas a pagar')
    parser.add_argument('--apenas-receber', action='store_true', help='Importar apenas contas a receber')
    parser.add_argument('--apenas-plano', action='store_true', help='Importar apenas plano de contas')
    parser.add_argument('--pagos-e-abertos', action='store_true', help='Importar apenas pagos e em aberto (excluir previsões)')

    args = parser.parse_args()

    if not args.senha_odoo:
        import getpass
        args.senha_odoo = getpass.getpass("Senha do Odoo: ")

    print(f"\n{'='*60}")
    print(f"IMPORTAÇÃO FINANCEIRO → ODOO")
    print(f"{'='*60}")
    print(f"URL: {args.url}")
    print(f"Banco: {args.banco}")
    print(f"Usuário: {args.usuario}")
    print(f"Arquivo: {args.arquivo}")
    print(f"{'='*60}\n")

    odoo = OdooXMLRPC(args.url, args.banco, args.usuario, args.senha_odoo)
    odoo.authenticate()

    decrypted = decrypt_xlsx(args.arquivo, args.senha)

    log = []

    if args.apenas_plano or not (args.apenas_pagar or args.apenas_receber):
        decrypted.seek(0)
        importar_plano_contas(odoo, decrypted, log)

    if not args.apenas_plano and not args.apenas_receber:
        decrypted.seek(0)
        df_pagar = pd.read_excel(decrypted, sheet_name='Pagar', engine='pyxlsb')
        if args.pagos_e_abertos:
            df_pagar = df_pagar[df_pagar['Status'].isin(['Pago', 'Em Aberto'])]
        importar_lancamentos(odoo, df_pagar, 'pagar', 'purchase', log)

    if not args.apenas_plano and not args.apenas_pagar:
        decrypted.seek(0)
        df_receber = pd.read_excel(decrypted, sheet_name='Receber', engine='pyxlsb')
        if args.pagos_e_abertos:
            df_receber = df_receber[df_receber['Status'].isin(['Pago', 'Em Aberto'])]
        importar_lancamentos(odoo, df_receber, 'receber', 'sale', log)

    print(f"\n{'='*60}")
    print("LOG DE IMPORTAÇÃO:")
    print('='*60)
    for line in log:
        print(line)

    report_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'import_log.txt')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(log))
    print(f"\nLog salvo em: {report_path}")
    print("Concluído!")


if __name__ == '__main__':
    main()
