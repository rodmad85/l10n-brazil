import base64
import io
import logging
from datetime import datetime, timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

try:
    import pandas as pd
except ImportError:
    _logger.error('pandas not installed. Please install: pip install pandas openpyxl pyxlsb')
    pd = None

ODOO_EPOCH = datetime(1899, 12, 30)

CLASSIFICACAO_ACCOUNT_MAP = {
    'DESPESAS BANCARIAS': {'code': '5.1.01', 'user_type': 'expense', 'name': 'Despesas Bancárias'},
    'COMPRAS PRODUTIVAS': {'code': '1.2.01', 'user_type': 'asset', 'name': 'Compras Produtivas'},
    'DESPESAS FIXAS': {'code': '5.2.01', 'user_type': 'expense', 'name': 'Despesas Fixas'},
    'EMPRESTIMOS': {'code': '2.1.01', 'user_type': 'liability', 'name': 'Empréstimos'},
    'FUNCIONARIOS': {'code': '5.3.01', 'user_type': 'expense', 'name': 'Despesas com Pessoal'},
    'INVESTIMENTO': {'code': '1.3.01', 'user_type': 'asset', 'name': 'Investimentos'},
    'TRANSFERENCIAS': {'code': '9.1.01', 'user_type': 'equity', 'name': 'Transferências'},
    'PAGAMENTO FATURA CARTAO CREDITO': {'code': '2.2.01', 'user_type': 'liability', 'name': 'Pagamento Fatura Cartão'},
    'PARTICULAR': {'code': '5.4.01', 'user_type': 'expense', 'name': 'Despesas Particulares'},
    'IMPOSTOS': {'code': '5.5.01', 'user_type': 'expense', 'name': 'Impostos e Taxas'},
    'ATIVO': {'code': '1.1.01', 'user_type': 'asset', 'name': 'Ativo'},
    'DESPESAS VARIAVEIS': {'code': '5.6.01', 'user_type': 'expense', 'name': 'Despesas Variáveis'},
    'SALDO INICIAL': {'code': '9.2.01', 'user_type': 'equity', 'name': 'Saldos Iniciais'},
    'RECEITAS': {'code': '4.1.01', 'user_type': 'income', 'name': 'Receitas Operacionais'},
}

BANCO_JOURNAL_MAP = {
    'ITAU': {'name': 'Banco Itaú', 'code': 'ITAU', 'type': 'bank'},
    'SICREDI': {'name': 'Banco Sicredi', 'code': 'SICR', 'type': 'bank'},
    'CAIXA': {'name': 'Caixa Econômica', 'code': 'CAIX', 'type': 'bank'},
    'DINHEIRO': {'name': 'Dinheiro', 'code': 'CASH', 'type': 'cash'},
    'DAYCOVAL': {'name': 'Daycoval', 'code': 'DAYC', 'type': 'bank'},
    'NU BANK': {'name': 'Nubank', 'code': 'NUBK', 'type': 'bank'},
}

STATUS_MAP = {
    'Pago': 'posted',
    'Em Aberto': 'draft',
    'Previsão': 'draft',
}


class FinanceiroImportWizard(models.TransientModel):
    _name = 'financeiro.import.wizard'
    _description = 'Wizard de Importação Financeiro XLSX'

    file = fields.Binary(string='Arquivo Financeiro', required=True)
    filename = fields.Char(string='Nome do Arquivo')
    password = fields.Char(string='Senha do Arquivo', default='A123d')
    import_pagar = fields.Boolean(string='Importar Contas a Pagar', default=True)
    import_receber = fields.Boolean(string='Importar Contas a Receber', default=True)
    import_plano = fields.Boolean(string='Importar/Atualizar Plano de Contas', default=True)
    importar_todos = fields.Boolean(
        string='Importar Todos os Status',
        default=True,
        help='Se marcado, importa Pago, Em Aberto e Previsão. Se desmarcado, apenas Pago e Em Aberto.',
    )
    log = fields.Text(string='Log de Importação', readonly=True)
    state = fields.Selection([
        ('draft', 'Rascunho'),
        ('done', 'Concluído'),
        ('error', 'Erro'),
    ], default='draft')

    def action_decrypt(self):
        if not pd:
            raise UserError(_('pandas não está instalado. Instale com: pip install pandas openpyxl pyxlsb msoffcrypto-tool'))

        try:
            import msoffcrypto
            file_data = base64.b64decode(self.file)
            ms_file = msoffcrypto.OfficeFile(io.BytesIO(file_data))
            ms_file.load_key(password=self.password)
            decrypted = io.BytesIO()
            ms_file.decrypt(decrypted)
            decrypted.seek(0)
            return decrypted
        except Exception as e:
            raise UserError(_('Erro ao descriptografar arquivo: %s') % str(e))

    def _excel_serial_to_date(self, serial):
        if pd.isna(serial) or serial == 0:
            return False
        try:
            return ODOO_EPOCH + timedelta(days=int(serial))
        except (ValueError, TypeError):
            return False

    def action_import(self):
        self.ensure_one()
        decrypted = self._decrypt_file()
        log_lines = []

        try:
            if self.import_plano:
                self._import_plano_contas(decrypted, log_lines)
                decrypted.seek(0)

            if self.import_pagar:
                self._import_pagar(decrypted, log_lines)
                decrypted.seek(0)

            if self.import_receber:
                self._import_receber(decrypted, log_lines)

            self.write({
                'log': '\n'.join(log_lines),
                'state': 'done',
            })
        except Exception as e:
            _logger.exception('Erro na importação')
            self.write({
                'log': '\n'.join(log_lines) + f'\n\nERRO: {str(e)}',
                'state': 'error',
            })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'financeiro.import.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def _decrypt_file(self):
        try:
            import msoffcrypto
            file_data = base64.b64decode(self.file)
            ms_file = msoffcrypto.OfficeFile(io.BytesIO(file_data))
            ms_file.load_key(password=self.password)
            decrypted = io.BytesIO()
            ms_file.decrypt(decrypted)
            decrypted.seek(0)
            return decrypted
        except Exception as e:
            raise UserError(_('Erro ao descriptografar: %s') % str(e))

    def _import_plano_contas(self, decrypted, log_lines):
        log_lines.append('=== IMPORTAÇÃO PLANO DE CONTAS ===')
        df_class = pd.read_excel(decrypted, sheet_name='Classificacao', engine='pyxlsb')

        account_obj = self.env['account.account']
        created = 0
        updated = 0

        for _, row in df_class.iterrows():
            classif = str(row.get('CLASSIFICAÇÃO', '')).strip()
            sub1 = str(row.get('Sub Classificação 1', '')).strip()
            sub2 = str(row.get('Sub Classificação 2', '')).strip()
            sub3 = str(row.get('Sub Classificação 3', '')).strip()

            if not classif or classif == 'nan':
                continue

            base_info = CLASSIFICACAO_ACCOUNT_MAP.get(classif, None)
            if not base_info:
                log_lines.append(f'  AVISO: Classificação "{classif}" sem mapeamento. Pulando.')
                continue

            code = base_info['code']
            name_parts = [classif]
            if sub1 and sub1 != 'nan':
                name_parts.append(sub1)
            if sub2 and sub2 != 'nan':
                name_parts.append(sub2)
            if sub3 and sub3 != 'nan':
                name_parts.append(sub3)

            account_name = ' / '.join(name_parts)

            if sub1 and sub1 != 'nan':
                code_suffix = sub1[:3].upper().replace(' ', '').replace('/', '')
                full_code = f'{code}.{code_suffix}'
            else:
                full_code = code

            full_code = full_code[:20]

            existing = account_obj.search([
                ('financeiro_classificacao', '=', classif),
                ('financeiro_sub1', '=', sub1 if sub1 != 'nan' else False),
                ('financeiro_sub2', '=', sub2 if sub2 != 'nan' else False),
            ], limit=1)

            if not existing:
                existing = account_obj.search([
                    ('code', '=', full_code),
                ], limit=1)

            vals = {
                'code': full_code,
                'name': account_name,
                'financeiro_classificacao': classif,
                'financeiro_sub1': sub1 if sub1 != 'nan' else False,
                'financeiro_sub2': sub2 if sub2 != 'nan' else False,
                'financeiro_sub3': sub3 if sub3 != 'nan' else False,
            }

            user_type_map = {
                'expense': self.env.ref('account.data_account_type_expenses').id,
                'income': self.env.ref('account.data_account_type_revenue').id,
                'asset': self.env.ref('account.data_account_type_asset').id,
                'liability': self.env.ref('account.data_account_type_liability').id,
                'equity': self.env.ref('account.data_account_type_equity').id,
            }
            vals['user_type_id'] = user_type_map.get(base_info['user_type'],
                                                       self.env.ref('account.data_account_type_other').id)

            if existing:
                existing.write(vals)
                updated += 1
            else:
                account_obj.create(vals)
                created += 1

        log_lines.append(f'  Plano de Contas: {created} criados, {updated} atualizados')

    def _import_pagar(self, decrypted, log_lines):
        log_lines.append('\n=== IMPORTAÇÃO CONTAS A PAGAR ===')
        df = pd.read_excel(decrypted, sheet_name='Pagar', engine='pyxlsb')

        if not self.importar_todos:
            df = df[df['Status'].isin(['Pago', 'Em Aberto'])]

        journal_pagar = self.env['account.journal'].search([
            ('type', '=', 'purchase'),
        ], limit=1)
        if not journal_pagar:
            journal_pagar = self.env['account.journal'].search([
                ('type', 'in', ['general', 'purchase']),
            ], limit=1)

        move_obj = self.env['account.move']
        partner_obj = self.env['res.partner']
        account_obj = self.env['account.account']

        created = 0
        skipped = 0
        log_lines.append(f'  Total de linhas a processar: {len(df)}')

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
                dt_pgto = row.get('DtPgto', 0)
                observacao = str(row.get('Observação', '')).strip()

                data_date = self._excel_serial_to_date(data_val)
                if not data_date:
                    skipped += 1
                    continue

                if pd.isna(valor) or valor == 0:
                    skipped += 1
                    continue

                lancamento_int = int(lancamento) if not pd.isna(lancamento) else 0
                existing = move_obj.search([
                    ('financeiro_lancamento', '=', lancamento_int),
                    ('financeiro_origem', '=', 'pagar'),
                ], limit=1)
                if existing:
                    skipped += 1
                    continue

                base_info = CLASSIFICACAO_ACCOUNT_MAP.get(classif, {'code': '5.9.99', 'name': classif})

                expense_account = account_obj.search([
                    ('financeiro_classificacao', '=', classif),
                ], limit=1)
                if not expense_account:
                    expense_account = account_obj.search([
                        ('code', 'like', base_info['code'][:5]),
                        ('user_type_id', '=', self.env.ref('account.data_account_type_expenses').id),
                    ], limit=1)
                if not expense_account:
                    expense_account = self.env.ref('account.data_account_type_expenses').id
                    expense_account = account_obj.search([
                        ('user_type_id', '=', expense_account),
                    ], limit=1)

                payable_account = self.env.ref('account.data_account_type_payable').id
                payable_account = account_obj.search([
                    ('user_type_id', '=', payable_account),
                ], limit=1)

                partner_name = historico if historico and historico != 'nan' else classif
                partner = partner_obj.search([
                    ('name', '=', partner_name),
                ], limit=1)
                if not partner:
                    partner = partner_obj.create({
                        'name': partner_name,
                        'supplier_rank': 1,
                    })

                if banco and banco != 'nan' and banco in BANCO_JOURNAL_MAP:
                    bank_info = BANCO_JOURNAL_MAP[banco]
                    journal = self.env['account.journal'].search([
                        ('code', '=', bank_info['code']),
                    ], limit=1)
                    if not journal:
                        journal = self.env['account.journal'].create({
                            'name': bank_info['name'],
                            'code': bank_info['code'],
                            'type': bank_info['type'],
                        })
                else:
                    journal = journal_pagar

                ref_parts = []
                if doc and doc != 'nan':
                    ref_parts.append(doc)
                if parcela and parcela > 0:
                    ref_parts.append(f'{int(parcela)}/{int(total_parcelas)}')
                ref = ' - '.join(ref_parts) if ref_parts else historico[:50]

                narration = f"Classificação: {classif}"
                if sub1 and sub1 != 'nan':
                    narration += f" / {sub1}"
                if sub2 and sub2 != 'nan':
                    narration += f" / {sub2}"
                if os_num and os_num != 'nan':
                    narration += f"\nOS: {os_num}"
                if observacao and observacao != 'nan':
                    narration += f"\nObs: {observacao}"

                line_vals = [
                    (0, 0, {
                        'name': historico[:120] if historico and historico != 'nan' else classif,
                        'account_id': payable_account.id if payable_account else expense_account.id,
                        'partner_id': partner.id,
                        'debit': abs(valor) if valor > 0 else 0,
                        'credit': abs(valor) if valor < 0 else 0,
                    }),
                    (0, 0, {
                        'name': historico[:120] if historico and historico != 'nan' else classif,
                        'account_id': expense_account.id,
                        'partner_id': partner.id,
                        'debit': abs(valor) if valor < 0 else 0,
                        'credit': abs(valor) if valor > 0 else 0,
                    }),
                ]

                move_vals = {
                    'move_type': 'entry',
                    'date': data_date.strftime('%Y-%m-%d'),
                    'ref': ref[:100] if ref else classif,
                    'journal_id': journal.id if journal else journal_pagar.id,
                    'narration': narration,
                    'line_ids': line_vals,
                    'financeiro_lancamento': lancamento_int,
                    'financeiro_classificacao': classif,
                    'financeiro_status_planilha': status if status != 'nan' else '',
                    'financeiro_banco_planilha': banco if banco != 'nan' else '',
                    'financeiro_os': os_num if os_num != 'nan' else '',
                    'financeiro_origem': 'pagar',
                }

                if status == 'Pago':
                    move_vals['auto_post'] = 'never'

                move = move_obj.create(move_vals)
                created += 1

                if status == 'Pago':
                    try:
                        move.action_post()
                    except Exception:
                        pass

            except Exception as e:
                _logger.warning(f'Erro ao processar linha Pagar {idx}: {e}')
                skipped += 1
                continue

        log_lines.append(f'  Pagar: {created} lançamentos criados, {skipped} pulados/erros')

    def _import_receber(self, decrypted, log_lines):
        log_lines.append('\n=== IMPORTAÇÃO CONTAS A RECEBER ===')
        df = pd.read_excel(decrypted, sheet_name='Receber', engine='pyxlsb')

        if not self.importar_todos:
            df = df[df['Status'].isin(['Pago', 'Em Aberto'])]

        journal_receber = self.env['account.journal'].search([
            ('type', '=', 'sale'),
        ], limit=1)
        if not journal_receber:
            journal_receber = self.env['account.journal'].search([
                ('type', 'in', ['general', 'sale']),
            ], limit=1)

        move_obj = self.env['account.move']
        partner_obj = self.env['res.partner']
        account_obj = self.env['account.account']

        created = 0
        skipped = 0
        log_lines.append(f'  Total de linhas a processar: {len(df)}')

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
                observacao = str(row.get('Observação', '')).strip()

                data_date = self._excel_serial_to_date(data_val)
                if not data_date:
                    skipped += 1
                    continue

                if pd.isna(valor) or valor == 0:
                    skipped += 1
                    continue

                lancamento_int = int(lancamento) if not pd.isna(lancamento) else 0
                existing = move_obj.search([
                    ('financeiro_lancamento', '=', lancamento_int),
                    ('financeiro_origem', '=', 'receber'),
                ], limit=1)
                if existing:
                    skipped += 1
                    continue

                base_info = CLASSIFICACAO_ACCOUNT_MAP.get(classif, {'code': '4.9.99', 'name': classif})

                income_account = account_obj.search([
                    ('financeiro_classificacao', '=', classif),
                ], limit=1)
                if not income_account:
                    income_account = account_obj.search([
                        ('code', 'like', base_info['code'][:5]),
                        ('user_type_id', '=', self.env.ref('account.data_account_type_revenue').id),
                    ], limit=1)
                if not income_account:
                    income_account = self.env.ref('account.data_account_type_revenue').id
                    income_account = account_obj.search([
                        ('user_type_id', '=', income_account),
                    ], limit=1)

                receivable_type = self.env.ref('account.data_account_type_receivable').id
                receivable_account = account_obj.search([
                    ('user_type_id', '=', receivable_type),
                ], limit=1)

                partner_name = historico if historico and historico != 'nan' else classif
                partner = partner_obj.search([
                    ('name', '=', partner_name),
                ], limit=1)
                if not partner:
                    partner = partner_obj.create({
                        'name': partner_name,
                        'customer_rank': 1,
                    })

                if banco and banco != 'nan' and banco in BANCO_JOURNAL_MAP:
                    bank_info = BANCO_JOURNAL_MAP[banco]
                    journal = self.env['account.journal'].search([
                        ('code', '=', bank_info['code']),
                    ], limit=1)
                    if not journal:
                        journal = self.env['account.journal'].create({
                            'name': bank_info['name'],
                            'code': bank_info['code'],
                            'type': bank_info['type'],
                        })
                else:
                    journal = journal_receber

                ref = doc if doc and doc != 'nan' else historico[:50]

                narration = f"Classificação: {classif}"
                if sub1 and sub1 != 'nan':
                    narration += f" / {sub1}"
                if os_num and os_num != 'nan':
                    narration += f"\nOS: {os_num}"
                if observacao and observacao != 'nan':
                    narration += f"\nObs: {observacao}"

                line_vals = [
                    (0, 0, {
                        'name': historico[:120] if historico and historico != 'nan' else classif,
                        'account_id': receivable_account.id if receivable_account else income_account.id,
                        'partner_id': partner.id,
                        'debit': abs(valor) if valor < 0 else 0,
                        'credit': abs(valor) if valor > 0 else 0,
                    }),
                    (0, 0, {
                        'name': historico[:120] if historico and historico != 'nan' else classif,
                        'account_id': income_account.id,
                        'partner_id': partner.id,
                        'debit': abs(valor) if valor > 0 else 0,
                        'credit': abs(valor) if valor < 0 else 0,
                    }),
                ]

                move_vals = {
                    'move_type': 'entry',
                    'date': data_date.strftime('%Y-%m-%d'),
                    'ref': ref[:100] if ref else classif,
                    'journal_id': journal.id if journal else journal_receber.id,
                    'narration': narration,
                    'line_ids': line_vals,
                    'financeiro_lancamento': lancamento_int,
                    'financeiro_classificacao': classif,
                    'financeiro_status_planilha': status if status != 'nan' else '',
                    'financeiro_banco_planilha': banco if banco != 'nan' else '',
                    'financeiro_os': os_num if os_num != 'nan' else '',
                    'financeiro_origem': 'receber',
                }

                move = move_obj.create(move_vals)
                created += 1

                if status == 'Pago':
                    try:
                        move.action_post()
                    except Exception:
                        pass

            except Exception as e:
                _logger.warning(f'Erro ao processar linha Receber {idx}: {e}')
                skipped += 1
                continue

        log_lines.append(f'  Receber: {created} lançamentos criados, {skipped} pulados/erros')
