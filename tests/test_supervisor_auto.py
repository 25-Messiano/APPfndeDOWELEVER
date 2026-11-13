"""Testes offline: nenhuma credencial real, nenhuma conexao externa."""
import io,json,os,socket,sys,tempfile,unittest,urllib.request
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from supervisao import supervisor as s,supervisor_auto as auto,supervisor_ai as ai

def deny_network(*args,**kwargs):raise AssertionError('REDE_PROIBIDA_NESTE_TESTE')
# Defesa independente dos mocks: o processo inteiro nao abre sockets nem urlopen.
socket.socket.connect=deny_network
socket.create_connection=deny_network
urllib.request.urlopen=deny_network

class AutomaticTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory()
  self.env=patch.dict(os.environ,{'SUPERVISOR_AGENT_TEAM':'false','SUPERVISOR_AUTO_AI':'true','OPENAI_API_KEY':'dummy-no-network','SUPERVISOR_GCS_SYNC':'false','SUPERVISOR_DB_PATH':self.tmp.name+'/audit.sqlite','SUPERVISOR_AUTO_AI_DAILY_LIMIT':'0'})
  self.env.start();self.calls=[]
  auto._PAUSE_STATE.update(until=0.0,reason='')
 def tearDown(self):self.env.stop();self.tmp.cleanup()
 def answer(self,question,reports,**kw):
  self.calls.append((question,reports,kw))
  return {'resumo':'Conferir registros.','prioridade':'normal','acoes':[],'evidencias':[reports[0]['id']],'limitacoes':[]}
 def motor(self,source='BB'):
  @s.supervised(source,'etapa',guard='identity')
  def run(ibge='2900108',ano=2026):return {'ok':True}
  return run
 def test_before_and_after_every_module(self):
  with patch.object(ai,'advise',side_effect=self.answer):
   for source in ['BB','TCM','FNDE','GERAL']:self.motor(source)()
  self.assertEqual(len(self.calls),8)
  self.assertTrue(all(x[2]['automatic'] for x in self.calls))
  for r in s.recent_reports():self.assertEqual(set(r['orientacao_automatica']),{'ANTES','DEPOIS'})
 def test_missing_key_stops_before_motor(self):
  with patch.dict(os.environ,{'OPENAI_API_KEY':''}),patch.object(ai,'advise') as call:
   with self.assertRaises(s.SupervisorAIPaused):self.motor()()
   call.assert_not_called()
  self.assertEqual(s.recent_reports()[0]['orientacao_automatica']['ANTES']['status'],'PAUSADO_SEM_CHAVE')
 def test_quota_stops_before_motor(self):
  done=[]
  @s.supervised('FNDE','gravar')
  def run():done.append(True)
  with patch.object(ai,'advise',side_effect=s.SupervisorBlocked('A API esta sem saldo')):
   with self.assertRaises(s.SupervisorAIPaused):run()
  self.assertEqual(done,[])
 def test_connection_error_pauses(self):
  with patch.object(ai,'advise',side_effect=TimeoutError('timeout')):
   with self.assertRaises(s.SupervisorAIPaused):self.motor()()
  self.assertEqual(s.recent_reports()[0]['status'],'BLOQUEADO')
 def test_no_retry_storm(self):
  with patch.object(ai,'advise',side_effect=s.SupervisorBlocked('429')) as call:
   with self.assertRaises(s.SupervisorAIPaused):self.motor()()
   self.assertEqual(call.call_count,1)
 def test_ai_block_pauses(self):
  def blocked(*args,**kw):return {'prioridade':'bloqueio','resumo':'Dados divergentes'}
  with patch.object(ai,'advise',side_effect=blocked):
   with self.assertRaises(s.SupervisorAIPaused):self.motor()()
 def test_post_failure_preserves_result_audit(self):
  answers=[self.answer('x',[{'id':'a'}]),s.SupervisorBlocked('Sem saldo')]
  with patch.object(ai,'advise',side_effect=answers):
   with self.assertRaises(s.SupervisorAIPaused):self.motor()()
  r=s.recent_reports()[0];self.assertEqual(r['resumo']['ok'],True);self.assertEqual(r['status'],'BLOQUEADO')
 def test_original_error_is_not_replaced(self):
  @s.supervised('TCM','extrair')
  def run():raise RuntimeError('PDF incompleto')
  with patch.object(ai,'advise',side_effect=[self.answer('x',[{'id':'a'}]),TimeoutError('timeout')]):
   with self.assertRaisesRegex(RuntimeError,'PDF incompleto'):run()
  self.assertIn('ERRO',s.recent_reports()[0]['orientacao_automatica'])
 def test_nested_steps_are_each_reviewed(self):
  child=self.motor('TCM')
  @s.supervised('GERAL','lote')
  def run():return child()
  with patch.object(ai,'advise',side_effect=self.answer):run()
  self.assertEqual(len(self.calls),4)
 def test_secrets_and_binary_arguments_not_sent(self):
  @s.supervised('TCM','extrair')
  def run(pdf_bytes,settings):return {'ok':True}
  with patch.object(ai,'advise',side_effect=self.answer):run(b'%PDF-PRIVATE',{'OPENAI_API_KEY':'NEVER_SEND'})
  serialized=str(self.calls);self.assertNotIn('NEVER_SEND',serialized);self.assertNotIn('%PDF-PRIVATE',serialized)
 def test_deterministic_invalid_identity_blocks_motor(self):
  with patch.object(ai,'advise',side_effect=self.answer):
   with self.assertRaises(s.SupervisorBlocked):self.motor()('invalid')
  self.assertEqual(s.recent_reports()[0]['status'],'BLOQUEADO')
 def test_disabled_mode_is_explicit(self):
  with patch.dict(os.environ,{'SUPERVISOR_AUTO_AI':'false'}),patch.object(ai,'advise') as call:self.motor()();call.assert_not_called()
  self.assertEqual(s.recent_reports()[0]['orientacao_automatica']['ANTES']['status'],'DESATIVADA')
 def test_recursion_is_blocked(self):
  def recursive(*a,**k):return self.motor('TCM')()
  with patch.object(ai,'advise',side_effect=recursive):
   with self.assertRaises(s.SupervisorAIPaused):self.motor()()
 def test_explicit_daily_limit(self):
  with patch.dict(os.environ,{'SUPERVISOR_AUTO_AI_DAILY_LIMIT':'1'}):
   s.reserve_ai_call(automatic=True)
   with self.assertRaises(s.SupervisorBlocked):s.reserve_ai_call(automatic=True)
 def test_automatic_calls_do_not_hit_manual_cooldown(self):
  s.reserve_ai_call(automatic=True);s.reserve_ai_call(automatic=True)
 def test_api_pause_does_not_repeat_paid_requests(self):
  with patch.object(ai,'advise',side_effect=s.SupervisorBlocked('Sem saldo')) as call:
   for _ in range(3):
    with self.assertRaises(s.SupervisorAIPaused):self.motor()()
   self.assertEqual(call.call_count,1)
  self.assertTrue(auto.status()['api_em_pausa'])
 def test_status_never_exposes_key(self):
  self.assertNotIn('dummy-no-network',json.dumps(auto.status()))
 def test_real_transport_is_disabled(self):
  with self.assertRaisesRegex(AssertionError,'REDE_PROIBIDA'):urllib.request.urlopen('https://api.openai.com/')

if __name__=='__main__':unittest.main()
