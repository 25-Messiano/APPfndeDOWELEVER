"""Complete documentary packets are bounded, never trimmed to obtain approval."""
import io,json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from supervisao import supervisor as s, supervisor_agents as team, supervisor_lineage as lineage

class DocumentEvidenceTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory()
  self.env=patch.dict(os.environ,{'OPENAI_API_KEY':'dummy-offline','SUPERVISOR_AUTO_AI':'true','SUPERVISOR_AGENT_TEAM':'true','SUPERVISOR_GCS_SYNC':'false','SUPERVISOR_DB_PATH':self.tmp.name+'/audit.sqlite'})
  self.env.start()
 def tearDown(self):self.env.stop();self.tmp.cleanup()
 def context(self,n=70):
  return {'id':'operation-1','fonte':'TCM','operacao':'extracao_documento','servico':'PROCESSAR','fase':'DEPOIS',
          'status':'CONCLUIDO','resumo':{'valores':{'ISS':123.45}},
          'provas':[{'id':f'doc-{i}','tipo':'DOCUMENTAL','sha256':'a'*64,'local':f'pagina {i+1}','trecho':'x'*1100} for i in range(n)]}
 def answer(self):
  return {'veredito':'APROVADO','justificativa':'Fonte conferida','proximo_passo':'Prosseguir','evidencias':['doc-0'],'achados':[],'correcoes':[]}
 def test_complete_pdf_packet_above_old_bound_reaches_api_untrimmed(self):
  sent=[]
  def opener(req,**kw):
   sent.append(json.loads(req.data))
   return io.BytesIO(json.dumps({'status':'completed','output':[{'content':[{'type':'output_text','text':json.dumps(self.answer())}]}]}).encode())
  with patch.object(team,'reserve_ai_call'):
   team.call_agent('TECNICO',self.context(),{},opener=opener)
  context=json.loads(sent[0]['input'])['contexto']
  self.assertEqual(len(context['provas']),70)
  self.assertEqual(context['provas'][-1]['trecho'],'x'*1100)
  self.assertEqual(context['resumo']['valores']['ISS'],123.45)
 def test_oversize_packet_still_blocks_without_network(self):
  context=self.context(150);context['large_contract']='x'*100000
  with patch.object(team,'reserve_ai_call') as reserve:
   with self.assertRaisesRegex(s.SupervisorBlocked,'EVIDENCIA_EXCEDE_LIMITE'):
    team.call_agent('TECNICO',context,{},opener=lambda *a,**kw:self.fail('network'))
   reserve.assert_not_called()
 def test_download_does_not_build_ai_proof_packet(self):
  token=s._CURRENT.set({'id':'download','revisao_ia_obrigatoria':False})
  try:
   self.assertEqual(lineage.register_pdf(b'not parsed by AI proof collector'),[])
   self.assertIsNone(lineage.add_proof(documento='source',sha256='invalid',local='p1',trecho='text'))
   self.assertNotIn('provas',s._CURRENT.get())
  finally:s._CURRENT.reset(token)
