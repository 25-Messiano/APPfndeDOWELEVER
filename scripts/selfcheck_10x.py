import os
import tempfile
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("PDF_ENGINE", "reportlab")

from core.municipios import carregar_municipios, por_ibge, validar_identidade
from core.identificacao import identificar_nome_externo
from fontes.fnde_liberacoes_legado import codigo_fnde_municipio, moeda_br_para_float, classificar_programa, validar_referencia_araci, extrair_totais_programas
from core.validacao_html import validar_html
from pdf.gerador_pdf import gerar_pdf, validar_pdf_textual

PROGRAMAS = [
    {"programa":"PROG.NACIONAL DE ALIMENTAÇÃO ESCOLAR", "categoria":"PNAE", "total":2366078.00, "esfera":"ADMINISTRAÇÃO PÚBLICA MUNICIPAL", "quantidade_entidades":1},
    {"programa":"PROGRAMA DINHEIRO DIRETO NA ESCOLA", "categoria":"PDDE", "total":616100.00, "esfera":"PARTICULAR", "quantidade_entidades":54},
    {"programa":"QUOTA ESTADUAL / MUNICIPAL", "categoria":"QSE", "total":9368968.61, "esfera":"ADMINISTRAÇÃO PÚBLICA MUNICIPAL", "quantidade_entidades":2},
    {"programa":"EI - NOVAS TURMAS - MANUTENÇÃO DA EDUCAÇÃO INFANTIL TD", "categoria":"NOVAS_TURMAS", "total":370608.62, "esfera":"ADMINISTRAÇÃO PÚBLICA MUNICIPAL", "quantidade_entidades":1},
    {"programa":"PROGRAMA NACIONAL DE APOIO AO TRANSP DO ESCOLAR", "categoria":"PNATE", "total":911562.38, "esfera":"ADMINISTRAÇÃO PÚBLICA MUNICIPAL", "quantidade_entidades":1},
    {"programa":"ENSINO MÉDIO INOVADOR, MAIS CULTURA, ESC.DE FRONTEIRA, ATLETA NA ESCOLA, ESC.SUSTENTÁVEL", "categoria":"PDDE_QUALIDADE", "total":273042.00, "esfera":"PARTICULAR", "quantidade_entidades":50},
    {"programa":"NOVO ESGOTAMENTO SANITÁRIO, ESCOLA DO CAMPO, ESCOLA ACESSÍVEL E PDE ESCOLA - ANTIGO PDDE ESTRUTURA", "categoria":"PDDE_ESTRUTURA", "total":422850.00, "esfera":"PARTICULAR", "quantidade_entidades":49},
]


def ciclo(n):
    assert len(carregar_municipios()) == 5570
    araci = por_ibge("2902104")
    assert araci and araci["municipio"] == "Araci" and araci["uf"] == "BA" and araci["codigo_fnde_6"] == "290210"
    assert validar_identidade("2902104", "ARACI", "BA")["ok"]
    ident = identificar_nome_externo("FNDE_2025_2902104_Araci_BA.pdf")
    assert ident["ok"] and ident["ibge"] == "2902104" and ident["uf"] == "BA"
    assert codigo_fnde_municipio("2902104") == "290210"
    assert abs(moeda_br_para_float("R$ 9.368.968,61") - 9368968.61) < 0.001
    assert classificar_programa("PROG.NACIONAL DE ALIMENTAÇÃO ESCOLAR") == "PNAE"
    ref = validar_referencia_araci("2902104", 2025, PROGRAMAS)
    assert ref["aplicavel"] and ref["ok"]
    html = '<html><title>FNDE</title><body>FNDE LIBERAÇÕES MUNICÍPIO ENTIDADE PROGRAMA VALOR ' + ('conteudo oficial ' * 40) + '<div>PROG.NACIONAL DE ALIMENTAÇÃO ESCOLAR - Valor Total R$ 2.366.078,00</div></body></html>'
    assert validar_html(html)["ok"]
    totais = extrair_totais_programas(html)
    assert any(x.get("categoria") == "PNAE" and abs(x.get("total",0)-2366078.0)<0.01 for x in totais)
    with tempfile.TemporaryDirectory() as td:
        pdf = Path(td) / f"teste_{n}.pdf"
        r = gerar_pdf(ibge="2902104", municipio="Araci", uf="BA", ano=2025, programas=PROGRAMAS, destino=pdf)
        assert pdf.exists() and pdf.stat().st_size > 1000
        v = validar_pdf_textual(str(pdf), ["Araci", "2902104", "2.366.078,00", "9.368.968,61"])
        assert v["ok"], v
    return True

if __name__ == "__main__":
    for i in range(1, 11):
        ciclo(i)
        print(f"CICLO {i}/10: OK")
    print("RESULTADO FINAL: 10/10 CICLOS OK")
