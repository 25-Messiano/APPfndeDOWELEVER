"""Downloads independent of AI availability; processing remains fail-closed."""
import os,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from supervisao import supervisor as s, supervisor_auto as auto, supervisor_ai as ai

class DownloadScopeTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory()
  self.env=patch.dict(os.environ,{'SUPERVISOR_AUTO_AI':'true','SUPERVISOR_AGENT_TEAM':'false','OPENAI_API_KEY':'','SUPERVISOR_GCS_SYNC':'false','SUPERVISOR_DB_PATH':self.tmp.name+'/audit.sqlite'})
  self.env.start();auto._PAUSE_STATE.update(until=time.monotonic()+300,reason='API unavailable')
 def tearDown(self):
  auto._PAUSE_STATE.update(until=0,reason='');self.env.stop();self.tmp.cleanup()
 def test_download_and_nested_helper_ignore_missing_key_and_api_pause(self):
  @s.supervised('FNDE','helper')
  def helper():return 'original'
  @s.supervised('FNDE','download',ai_review=False)
  def download():return helper()
  with patch.object(ai,'advise') as api:
   self.assertEqual(download(),'original');api.assert_not_called()
  for r in s.recent_reports():
   self.assertFalse(r['revisao_ia_obrigatoria'])
   self.assertEqual(r['orientacao_automatica']['ANTES']['status'],'DISPENSADA_DOWNLOAD')
   self.assertEqual(r['orientacao_automatica']['DEPOIS']['status'],'DISPENSADA_DOWNLOAD')
 def test_processing_still_blocks_without_key(self):
  @s.supervised('BB','preencher_planilha')
  def process():self.fail('must not write')
  with self.assertRaises(s.SupervisorAIPaused):process()
 def test_download_scope_does_not_leak_to_next_processing_stage(self):
  @s.supervised('BB','download',ai_review=False)
  def download():return 'file'
  @s.supervised('BB','extracao')
  def extract():return {'ok':True}
  @s.supervised('BB','processamento')
  def process():download();return extract()
  auto._PAUSE_STATE.update(until=0,reason='')
  with patch.dict(os.environ,{'OPENAI_API_KEY':'dummy'}),patch.object(ai,'advise',return_value={'prioridade':'normal'}) as api:
   process();self.assertEqual(api.call_count,4)
  reports=s.recent_reports()
  self.assertTrue(next(r for r in reports if r['operacao']=='extracao')['revisao_ia_obrigatoria'])
 def test_invalid_pdf_still_rejected_before_storage(self):
  @s.supervised('TCM','guardar_download',guard='pdf',ai_review=False)
  def save(pdf_bytes):self.fail('invalid PDF must not be saved')
  with patch.object(ai,'advise') as api:
   with self.assertRaises(s.SupervisorBlocked):save(b'not a PDF')
   api.assert_not_called()
 def test_download_preserves_original_network_error(self):
  @s.supervised('BB','download',ai_review=False)
  def download():raise TimeoutError('source unavailable')
  with patch.object(ai,'advise') as api:
   with self.assertRaisesRegex(TimeoutError,'source unavailable'):download()
   api.assert_not_called()

 def test_independent_download_worker_does_not_require_ai(self):
  from concurrent.futures import ThreadPoolExecutor
  @s.supervised('BB','consulta_oficial',ai_review=False)
  def fetch():return 'file'
  with patch.object(ai,'advise') as api, ThreadPoolExecutor(max_workers=1) as pool:
   self.assertEqual(pool.submit(fetch).result(),'file');api.assert_not_called()

 def test_real_download_entrypoints_explicitly_skip_ai(self):
  import ast
  root=Path(__file__).resolve().parents[1]
  expected={'core/downloader.py': ['download_fnde_cnpj', 'download_fnde_municipio_completo'], 'core/validacao_html.py': ['validar_html'], 'cloud/storage.py': ['armazenar_arquivo'], 'pdf/gerador_pdf.py': ['gerar_pdf', 'validar_pdf_textual'], 'fontes/fnde_liberacoes_legado.py': ['consultar_liberacoes', 'entregar_html', 'coletar_entidades_e_pacote', 'coletar_liberacoes']}
  for filename, operations in expected.items():
   tree=ast.parse((root/filename).read_text())
   for operation in operations:
    calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='supervised' and n.args[1].value==operation]
    self.assertTrue(calls,filename+':'+operation)
    for call in calls:
     self.assertTrue(any(k.arg=='ai_review' and isinstance(k.value,ast.Constant) and k.value.value is False for k in call.keywords),filename+':'+operation)
