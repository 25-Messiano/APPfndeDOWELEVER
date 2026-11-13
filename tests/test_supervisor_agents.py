"""Contraprovas offline da equipe: API simulada, sem downloads/escrita financeira."""
import copy
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from supervisao import supervisor as s, supervisor_auto as auto, supervisor_agents as team
from supervisao import supervisor_lineage as lineage


def report(source='BB', operation='download'):
    return {'id': 'operacao-1', 'fonte': source, 'operacao': operation,
            'identidade': {'municipio': 'Cardeal da Silva', 'ano': '2026'},
            'status': 'CONCLUIDO', 'resumo': {'ok': True}}


def opinion(ref='operacao-1', verdict='APROVADO'):
    return {'veredito': verdict, 'justificativa': 'Contrato conferido no escopo recebido.',
            'proximo_passo': 'Prosseguir somente nesta etapa.', 'evidencias': [ref],
            'achados': [], 'correcoes': []}


class TeamTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'SUPERVISOR_AUTO_AI': 'true', 'SUPERVISOR_AGENT_TEAM': 'true',
            'SUPERVISOR_GCS_SYNC': 'false', 'SUPERVISOR_DB_PATH': self.tmp.name + '/audit.sqlite',
            'OPENAI_API_KEY': 'dummy-only-offline', 'SUPERVISOR_AUTO_AI_DAILY_LIMIT': '0'})
        self.env.start(); self.calls = []
        auto._PAUSE_STATE.update(until=0.0, reason='')

    def tearDown(self):
        self.env.stop(); self.tmp.cleanup()

    def reviewer(self, role, context, previous):
        self.calls.append((role, copy.deepcopy(context), copy.deepcopy(previous)))
        return {'agente': role, 'modelo': 'offline', 'response_id': 'mock-' + role,
                'parecer': opinion(context['provas'][0]['id'] if context.get('provas') else context['id'])}

    def motor(self, source='BB', operation='download', result=None):
        @s.supervised(source, operation, guard='identity')
        def run(ibge='2907004', ano=2026):
            return result if result is not None else {'ok': True}
        return run

    def test_three_explicit_roles_and_four_tasks_each(self):
        d = team.definition()
        self.assertEqual(list(d['agentes']), ['TECNICO', 'AUDITOR', 'COORDENADOR'])
        for spec in d['agentes'].values(): self.assertEqual(set(spec['tarefas']), set(team.STAGES))

    def test_definition_is_not_mutable_global_state(self):
        team.definition()['agentes']['TECNICO']['nome'] = 'wrong'
        self.assertEqual(team.definition()['agentes']['TECNICO']['nome'], 'Agente Técnico')

    def test_classifies_all_four_services(self):
        for operation, expected in [('buscar_daf', 'BUSCAR'), ('download', 'BAIXAR'),
                                    ('extracao_documento', 'PROCESSAR'), ('gravar_mensal', 'ENTREGAR')]:
            self.assertEqual(team.stage_for(operation), expected)

    def test_all_modules_all_services_reviewed_before_and_after(self):
        with patch.object(team, 'call_agent', side_effect=self.reviewer):
            for source in ('BB', 'TCM', 'FNDE'):
                for operation in ('buscar', 'download', 'extracao', 'entregar'):
                    self.motor(source, operation)()
        self.assertEqual(len(self.calls), 72)
        for r in s.recent_reports():
            self.assertEqual(set(r['equipe_agentes']), {'ANTES', 'DEPOIS'})
            for entry in r['equipe_agentes'].values(): self.assertEqual(len(entry['agentes']), 3)

    def test_auditor_and_coordinator_receive_same_original_proofs(self):
        r = report(); r['provas'] = [{'id': 'doc-a', 'trecho': 'Fonte original: 1.500,00'}]
        team.review_team(r, 'DEPOIS', reviewer=self.reviewer)
        self.assertTrue(all(c[1]['provas'] == r['provas'] for c in self.calls))
        self.assertEqual(set(self.calls[1][2]), {'TECNICO'})
        self.assertEqual(set(self.calls[2][2]), {'TECNICO', 'AUDITOR'})

    def test_reviewer_cannot_change_next_reviewers_context(self):
        def mutate(role, context, previous):
            answer = self.reviewer(role, context, previous)
            context['identidade']['municipio'] = 'wrong'
            return answer
        r = report(); team.review_team(r, 'ANTES', reviewer=mutate)
        self.assertTrue(all(c[1]['identidade']['municipio'] == 'Cardeal da Silva' for c in self.calls))

    def test_coordinator_cannot_overrule_auditor(self):
        def disagree(role, context, previous):
            answer = self.reviewer(role, context, previous)
            if role == 'AUDITOR': answer['parecer']['veredito'] = 'REVISAR'
            return answer
        result = team.review_team(report(), 'DEPOIS', reviewer=disagree)
        self.assertEqual(result['veredito'], 'REVISAR')

    def test_deterministic_pending_cannot_be_overruled(self):
        r = report(); r['resumo'] = {'concluido': False}
        self.assertEqual(team.review_team(r, 'DEPOIS', reviewer=self.reviewer)['veredito'], 'REVISAR')

    def test_original_error_forces_review(self):
        r = report(); r['erro'] = 'PDF incompleto'
        self.assertEqual(team.review_team(r, 'ERRO', reviewer=self.reviewer)['veredito'], 'REVISAR')

    def test_before_does_not_require_nonexistent_result(self):
        r = report(); r['resumo'] = {'fase': 'PRE_EXECUCAO', 'resultado_ainda_nao_produzido': True}
        self.assertEqual(team.review_team(r, 'ANTES', reviewer=self.reviewer)['veredito'], 'APROVADO')

    def test_fake_evidence_is_rejected(self):
        with self.assertRaisesRegex(s.SupervisorBlocked, 'EVIDENCIA_INVALIDA'):
            team.validate_answer(opinion('invented'), {'operacao-1'})

    def test_approval_without_evidence_is_rejected(self):
        a = opinion(); a['evidencias'] = []
        with self.assertRaisesRegex(s.SupervisorBlocked, 'APROVACAO_SEM_PROVA'):
            team.validate_answer(a, {'operacao-1'})

    def test_mechanical_error_without_evidence_is_rejected(self):
        a = opinion(); a['achados'] = [{'tipo':'MECANICO','gravidade':'ALTA','descricao':'OCR','evidencias':[]}]
        with self.assertRaisesRegex(s.SupervisorBlocked, 'ACHADO_SEM_PROVA'): team.validate_answer(a, {'operacao-1'})

    def test_correction_without_evidence_is_rejected(self):
        a = opinion(); a['correcoes'] = [{'campo':'J11','antes':'15000','depois':'1500','regra':'OCR','evidencias':[]}]
        with self.assertRaisesRegex(s.SupervisorBlocked, 'CORRECAO_SEM_PROVA'): team.validate_answer(a, {'operacao-1'})

    def test_proposed_correction_remains_visible_and_unapplied(self):
        def propose(role, context, previous):
            a = self.reviewer(role, context, previous)
            if role == 'TECNICO':
                a['parecer']['correcoes'] = [{'campo':'J11','antes':'15000','depois':'1500','regra':'OCR','evidencias':[context['id']]}]
            return a
        r = report(); result = team.review_team(r, 'DEPOIS', reviewer=propose)
        self.assertEqual(result['veredito'], 'REVISAR')
        self.assertEqual(r['trilha_correcoes'][0]['status'], 'PROPOSTA_NAO_APLICADA')
        self.assertEqual(r['trilha_correcoes'][0]['antes'], '15000')

    def test_coordinator_cannot_invent_correction(self):
        def invent(role, context, previous):
            a = self.reviewer(role, context, previous)
            if role == 'COORDENADOR': a['parecer']['correcoes'] = [{'campo':'J11','antes':'1','depois':'2','regra':'invento','evidencias':[context['id']]}]
            return a
        with self.assertRaisesRegex(s.SupervisorBlocked, 'COORDENADOR_CRIOU_CORRECAO'):
            team.review_team(report(), 'DEPOIS', reviewer=invent)

    def test_coordinator_cannot_invent_finding(self):
        def invent(role, context, previous):
            a = self.reviewer(role, context, previous)
            if role == 'COORDENADOR': a['parecer']['achados'] = [{'tipo':'MECANICO','gravidade':'ALTA','descricao':'novo','evidencias':[context['id']]}]
            return a
        with self.assertRaisesRegex(s.SupervisorBlocked, 'COORDENADOR_CRIOU_ACHADO'):
            team.review_team(report(), 'DEPOIS', reviewer=invent)

    def test_missing_key_blocks_before_motor(self):
        with patch.dict(os.environ, {'OPENAI_API_KEY': ''}), patch.object(team, 'call_agent') as call:
            with self.assertRaises(s.SupervisorAIPaused): self.motor()()
            call.assert_not_called()

    def test_quota_failure_does_not_repeat_paid_requests(self):
        with patch.object(team, 'call_agent', side_effect=s.SupervisorBlocked('API_INDISPONIVEL_HTTP_429')) as call:
            for _ in range(3):
                with self.assertRaises(s.SupervisorAIPaused): self.motor()()
            self.assertEqual(call.call_count, 1)

    def test_invalid_input_stops_before_any_agent(self):
        with patch.object(team, 'call_agent', side_effect=self.reviewer):
            with self.assertRaises(s.SupervisorBlocked): self.motor()(ibge='bad')
        # Only ERRO may be reviewed; no ANTES execution can be approved.
        self.assertTrue(all(c[1]['fase'] == 'ERRO' for c in self.calls))

    def test_partial_agent_responses_are_audited_on_failure(self):
        def fail(role, context, previous):
            if role == 'AUDITOR': raise TimeoutError('timeout')
            return self.reviewer(role, context, previous)
        with patch.object(team, 'call_agent', side_effect=fail):
            with self.assertRaises(s.SupervisorAIPaused): self.motor()()
        r = s.recent_reports()[0]
        self.assertEqual(set(r['equipe_agentes']['ANTES']['agentes']), {'TECNICO'})

    def test_transport_uses_existing_key_responses_and_strict_schema(self):
        sent = []
        def opener(req, **kwargs):
            sent.append(req)
            return io.BytesIO(json.dumps({'status':'completed','id':'resp-test',
                'output':[{'content':[{'type':'output_text','text':json.dumps(opinion())}]}]}).encode())
        c = {**report(), 'servico':'PROCESSAR','fase':'ANTES','provas':[]}
        answer = team.call_agent('AUDITOR', c, {}, opener=opener)
        self.assertEqual(answer['response_id'], 'resp-test')
        payload = json.loads(sent[0].data)
        self.assertEqual(sent[0].full_url, 'https://api.openai.com/v1/responses')
        self.assertTrue(payload['text']['format']['strict'])
        self.assertFalse(payload['store'])
        self.assertNotIn('dummy-only-offline', str(payload))
        self.assertIn('contraprovas', payload['instructions'])

    def test_incomplete_response_is_not_approval(self):
        def opener(*a, **k): return io.BytesIO(b'{"status":"incomplete","output":[]}')
        with self.assertRaisesRegex(s.SupervisorBlocked, 'RESPOSTA_INCOMPLETA'):
            team.call_agent('TECNICO', {**report(),'servico':'BAIXAR'}, {}, opener=opener)

    def test_coordinator_schema_only_allows_catalogued_selections(self):
        sent = []
        previous = {k:{'parecer':opinion()} for k in ('TECNICO','AUDITOR')}
        def opener(req, **kwargs):
            sent.append(json.loads(req.data))
            return io.BytesIO(json.dumps({'status':'completed','output':[{'content':[{
                'type':'output_text','text':json.dumps(opinion())}]}]}).encode())
        team.call_agent('COORDENADOR', {**report(),'servico':'PROCESSAR'}, previous, opener=opener)
        props = sent[0]['text']['format']['schema']['properties']
        self.assertEqual(props['correcoes']['maxItems'], 0)
        self.assertEqual(props['achados']['maxItems'], 0)

    def test_coordinator_selection_restores_exact_original_proposal(self):
        correction={'campo':'J11','antes':'15000','depois':'1500','regra':'OCR','evidencias':['operacao-1']}
        previous={'TECNICO':{'parecer':opinion()},'AUDITOR':{'parecer':opinion()}}
        previous['TECNICO']['parecer']['correcoes']=[correction]
        def opener(req, **kwargs):
            body=json.loads(json.loads(req.data)['input']); options=body['catalogo_de_decisoes']['correcoes']
            a=opinion(verdict='REVISAR');a['correcoes']=[next(iter(options))]
            return io.BytesIO(json.dumps({'status':'completed','output':[{'content':[{
                'type':'output_text','text':json.dumps(a)}]}]}).encode())
        a=team.call_agent('COORDENADOR',{**report(),'servico':'PROCESSAR'},previous,opener=opener)
        self.assertEqual(a['parecer']['correcoes'],[correction])

    def test_large_context_is_not_silently_truncated(self):
        with self.assertRaisesRegex(s.SupervisorBlocked, 'EVIDENCIA_EXCEDE_LIMITE'):
            team.call_agent('TECNICO', {**report(),'servico':'BAIXAR','provas':[], 'x':'z'*56000}, {})

    def test_lineage_keeps_hash_location_and_value(self):
        r = report(); token = s._CURRENT.set(r)
        try:
            ref = lineage.add_proof(documento='origem.xls', sha256='a'*64,
                local='linha 12', trecho='01/OUT/26 | 00001 | 1.500,00', campo='PNAE', valor=150000)
        finally: s._CURRENT.reset(token)
        self.assertEqual(r['provas'][0]['valor'],150000)
        self.assertEqual(r['provas'][0]['local'],'linha 12')
        self.assertTrue(ref.startswith('doc-'))

    def test_duplicate_source_not_double_counted(self):
        r = report(); token = s._CURRENT.set(r)
        try:
            for _ in range(2): lineage.add_proof(documento='x',sha256='a'*64,local='p1',trecho='1500')
        finally: s._CURRENT.reset(token)
        self.assertEqual(len(r['provas']), 1)

    def test_no_truncated_proof_or_secret_is_accepted(self):
        token = s._CURRENT.set(report())
        try:
            for text in ('x'*1201, 'Bearer NEVER_EXPORT'):
                with self.assertRaises(s.SupervisorBlocked): lineage.add_proof(documento='x',sha256='a'*64,local='p1',trecho=text)
        finally: s._CURRENT.reset(token)

    def test_status_does_not_expose_key(self):
        self.assertNotIn('dummy-only-offline', json.dumps(auto.status()))

    def pdf(self, text):
        from reportlab.pdfgen.canvas import Canvas
        out = io.BytesIO(); c = Canvas(out)
        c.drawString(20, 750, text); c.save(); return out.getvalue()

    def test_internal_month_disagreement_is_blocked(self):
        raw = self.pdf('Municipio: CARDEAL DA SILVA - Competencia: 07/2026')
        with self.assertRaisesRegex(s.SupervisorBlocked, 'COMPETENCIA_INTERNA_DIVERGENTE'):
            lineage.validate_pdf_identity(raw, municipio='Cardeal da Silva', competencia='08/2026')

    def test_pdf_identity_is_verified_without_changing_bytes(self):
        raw = self.pdf('Municipio: CARDEAL DA SILVA - Competencia: 07/2026')
        sha = hashlib.sha256(raw).hexdigest()
        checked = lineage.validate_pdf_identity(raw, municipio='Cardeal da Silva', competencia='07/2026')
        self.assertEqual(checked['sha256'], sha)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), sha)

    def test_pdf_proof_has_actual_page_lines_and_source_hash(self):
        raw = self.pdf('CARDEAL DA SILVA - Competencia: 07/2026 - Receita 1.500,00')
        r = report(); token = s._CURRENT.set(r)
        try: lineage.register_pdf(raw, 'julho.pdf')
        finally: s._CURRENT.reset(token)
        self.assertIn('página 1', r['provas'][0]['local'])
        self.assertIn('1.500,00', r['provas'][0]['trecho'])
        self.assertEqual(r['provas'][0]['sha256'], hashlib.sha256(raw).hexdigest())

    def test_cell_lineage_keeps_before_and_after_without_painting(self):
        r = report(); token = s._CURRENT.set(r)
        original = {'fonte':'BB','linhas':[{'competencia':'07/2026','linha':11,
                    'celulas':[{'celula':'J11','campo':'VAAT Ajuste','valor':1500,'valor_anterior':15000}]}]}
        before = copy.deepcopy(original)
        try: lineage.attach_cell_lineage(original)
        finally: s._CURRENT.reset(token)
        self.assertEqual(original, before)
        self.assertEqual(r['linhagem_celulas']['celulas'][0]['valor_anterior'],15000)

    def test_nested_html_rows_are_not_duplicated_or_truncated(self):
        r = report(); token = s._CURRENT.set(r)
        rows = ''.join(f'<tr><td>Pagamento {i}</td><td>1.500,00</td></tr>' for i in range(60))
        try: lineage.register_html('<table><tr><td><table>'+rows+'</table></td></tr></table>')
        finally: s._CURRENT.reset(token)
        self.assertEqual(len(r['provas']),60)
        self.assertTrue(all('1.500,00' in p['trecho'] for p in r['provas']))

    def test_long_html_row_keeps_complete_literal_source(self):
        r = report(); token = s._CURRENT.set(r)
        text = ('Documento original ' * 130) + 'VALOR FINAL 1.500,00'
        try: lineage.register_html('<table><tr><td>'+text+'</td></tr></table>')
        finally: s._CURRENT.reset(token)
        self.assertEqual(''.join(p['trecho'] for p in r['provas']), text)

    def test_connection_test_calls_three_agents_without_motor(self):
        with patch.object(team,'call_agent',side_effect=self.reviewer): r = team.connection_test()
        self.assertEqual(len(self.calls),3)
        self.assertFalse(r['resumo']['downloads_iniciados'])
        self.assertFalse(r['resumo']['planilhas_alteradas'])


if __name__ == '__main__': unittest.main()
