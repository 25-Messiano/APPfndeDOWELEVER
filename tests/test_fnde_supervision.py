"""Verifica etapas FNDE e interrupção real dos laços, sem rede ou credenciais."""
import ast
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from supervisao import supervisor as s, supervisor_ai as ai, supervisor_auto as auto


class FndeSupervisionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {
            "SUPERVISOR_AUTO_AI": "true", "OPENAI_API_KEY": "dummy-no-network",
            "SUPERVISOR_GCS_SYNC": "false", "SUPERVISOR_DB_PATH": self.tmp.name + "/audit.sqlite",
        })
        self.env.start()
        auto._PAUSE_STATE.update(until=0, reason="")

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_all_fnde_stages_have_automatic_supervision(self):
        wanted = {
            "core/downloader.py": {"baixar_fnde", "baixar_fnde_municipio_completo"},
            "core/validacao_html.py": {"validar_html"},
            "fontes/fnde_liberacoes_legado.py": {"extrair_totais_programas", "consultar", "_salvar_html", "baixar_municipio_completo", "baixar"},
            "cloud/storage.py": {"salvar"},
            "pdf/gerador_pdf.py": {"gerar_pdf", "validar_pdf_textual"},
        }
        for filename, names in wanted.items():
            tree = ast.parse((ROOT / filename).read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name in names:
                    with self.subTest(filename=filename, function=node.name):
                        self.assertTrue(any(isinstance(d, ast.Call) and isinstance(d.func, ast.Name)
                                            and d.func.id == "supervised" for d in node.decorator_list))
                    names = names - {node.name}
            self.assertFalse(names, f"Funções não encontradas: {names}")

    def test_consulta_does_not_swallow_ai_pause_or_try_second_endpoint(self):
        # Executa o método real com dependências isoladas, simulando pausa na validação.
        tree = ast.parse((ROOT / "fontes/fnde_liberacoes_legado.py").read_text())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef))
        method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "consultar")
        method.decorator_list = []
        module = ast.Module(body=[method], type_ignores=[])
        ns = {"urlencode": lambda x: "", "SupervisorAIPaused": s.SupervisorAIPaused,
              "validar_html": lambda html: (_ for _ in ()).throw(s.SupervisorAIPaused("sem saldo"))}
        exec(compile(ast.fix_missing_locations(module), "consulta-real", "exec"), ns)
        from types import SimpleNamespace
        session = unittest.mock.Mock()
        session.get.return_value = SimpleNamespace(text="html")
        source = SimpleNamespace(endpoints=["primeiro", "segundo"], timeout=5, session=session,
                                 _params=lambda *a: {})
        with self.assertRaises(s.SupervisorAIPaused):
            ns["consultar"](source, ano=2026, uf="BA", ibge="2902104")
        self.assertEqual(session.get.call_count, 1)

    def test_no_key_blocks_storage_before_any_side_effect(self):
        tree = ast.parse((ROOT / "cloud/storage.py").read_text())
        ns = {"__name__": "isolated_storage"}
        exec(compile(tree, "storage-real", "exec"), ns)
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            with self.assertRaises(s.SupervisorAIPaused):
                ns["salvar"](Path("arquivo.pdf"))
        report = s.recent_reports()[0]
        self.assertEqual(report["operacao"], "armazenar_arquivo")
        self.assertEqual(report["orientacao_automatica"]["ANTES"]["status"], "PAUSADO_SEM_CHAVE")

    def test_financial_summary_preserves_values_without_raw_document(self):
        summary = s._summary([{"programa": "PNAE", "total": 123.45, "html": "SEGREDO"}])
        self.assertEqual(summary["programas"][0]["total"], 123.45)
        self.assertNotIn("SEGREDO", str(summary))

    def test_rejected_validation_is_pending(self):
        result = {"ok": True, "status_validacao": "PENDENTE_CONFERENCIA"}
        self.assertTrue(s._pending(s._summary(result)))

    def test_automatic_review_with_no_evidence_never_calls_api(self):
        with patch.object(ai.urllib.request, "urlopen") as call:
            with self.assertRaisesRegex(s.SupervisorBlocked, "Sem registros"):
                ai.advise("Revisar", [], automatic=True)
            call.assert_not_called()


if __name__ == "__main__":
    unittest.main()
