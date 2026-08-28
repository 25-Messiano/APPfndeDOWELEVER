import hashlib
import json
import os
import re
import zipfile
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup

from core.nomes_arquivos import nome_html, slug
from core.validacao_html import validar_html
from core.logger import log
from database.db import registrar
from cloud.storage import salvar as salvar_storage
from pdf.gerador_pdf import gerar_pdf, validar_pdf_textual

ROOT = Path(__file__).resolve().parents[1]
DOWNLOADS = ROOT / "downloads"
DOWNLOADS.mkdir(parents=True, exist_ok=True)

DEFAULT_ENDPOINTS = [
    "https://www.fnde.gov.br/pls/edw_fnde/internet_fnde.liberacoes_result_pc",
    "https://www.fnde.gov.br/pls/simad/internet_fnde.liberacoes_result_pc",
]

ARACI_REFERENCIA_2025 = {
    "PNAE": 2366078.00,
    "PDDE": 616100.00,
    "QSE": 9368968.61,
    "NOVAS_TURMAS": 370608.62,
    "PNATE": 911562.38,
    "PDDE_QUALIDADE": 273042.00,
    "PDDE_ESTRUTURA": 422850.00,
}


def codigo_fnde_municipio(ibge: str) -> str:
    d = re.sub(r"\D", "", str(ibge))
    if len(d) != 7:
        raise ValueError("IBGE deve possuir 7 digitos")
    return d[:6]


def limpar_cnpj(cnpj: str) -> str:
    return re.sub(r"\D", "", cnpj or "")


def moeda_br_para_float(valor: str):
    if not valor:
        return None
    texto = str(valor).strip().replace("R$", "").replace(" ", "")
    m = re.search(r"-?\d{1,3}(?:\.\d{3})*,\d{2}|-?\d+,\d{2}", texto)
    if not m:
        return None
    return float(m.group(0).replace(".", "").replace(",", "."))


def classificar_programa(titulo: str) -> str:
    t = re.sub(r"\s+", " ", (titulo or "").upper()).strip()
    if "ALIMENTA" in t and "ESCOLAR" in t:
        return "PNAE"
    if "PROGRAMA DINHEIRO DIRETO NA ESCOLA" in t and "EDUCAÇÃO INTEGRAL" not in t and "EDUCACAO INTEGRAL" not in t:
        return "PDDE"
    if "QUOTA ESTADUAL" in t or "QUOTA - QUOTA" in t or "SALÁRIO-EDUCAÇÃO" in t or "SALARIO-EDUCACAO" in t:
        return "QSE"
    if "NOVAS TURMAS" in t:
        return "NOVAS_TURMAS"
    if "PNATE" in t or "APOIO AO TRANSP" in t:
        return "PNATE"
    if "ENSINO MÉDIO INOVADOR" in t or "ENSINO MEDIO INOVADOR" in t or "MAIS CULTURA" in t or "ATLETA NA ESCOLA" in t or "SUSTENT" in t:
        return "PDDE_QUALIDADE"
    if "ANTIGO PDDE ESTRUTURA" in t or "ÁGUA NA ESCOLA" in t or "AGUA NA ESCOLA" in t or "ESCOLA ACESSÍVEL" in t or "ESCOLA ACESSIVEL" in t:
        return "PDDE_ESTRUTURA"
    return slug(t)[:80]


def extrair_totais_programas(html: str) -> list[dict]:
    """Extrai cada bloco/tabela e o respectivo total mostrado pelo FNDE."""
    soup = BeautifulSoup(html or "", "html.parser")
    saida = []
    vistos = set()

    # Pagina-resumo atual: "NOME DO PROGRAMA - Valor Total R$ 1.234,56".
    texto_geral = soup.get_text(" ", strip=True)
    padrao_resumo = re.compile(
        r"(.{5,220}?)\s*-\s*Valor\s+Total\s+R\$\s*([0-9.]+,[0-9]{2})",
        flags=re.I,
    )
    for m in padrao_resumo.finditer(texto_geral):
        titulo = re.sub(r"\s+", " ", m.group(1)).strip(" :-")
        # Evita carregar texto de navegacao muito anterior ao titulo.
        if "Exibindo" in titulo:
            titulo = titulo.split("Exibindo")[-1].strip(" :-")
        if len(titulo) > 220:
            titulo = titulo[-220:]
        total = moeda_br_para_float(m.group(2))
        if total is None:
            continue
        chave = (titulo, total)
        if chave not in vistos:
            vistos.add(chave)
            saida.append({"programa": titulo, "categoria": classificar_programa(titulo), "total": total})
    for tabela in soup.find_all("table"):
        texto = tabela.get_text(" ", strip=True)
        if "Total" not in texto and "TOTAL" not in texto:
            continue
        titulo = ""
        primeira = tabela.find("tr")
        if primeira:
            titulo = primeira.get_text(" ", strip=True)
        if not titulo or titulo.upper().startswith("DATA PGTO"):
            anterior = tabela.find_previous("table")
            if anterior:
                cand = anterior.get_text(" ", strip=True)
                if len(cand) < 400:
                    titulo = cand
        valores = []
        for tag in tabela.find_all(["b", "td"]):
            v = moeda_br_para_float(tag.get_text(" ", strip=True))
            if v is not None:
                valores.append((tag.get_text(" ", strip=True), v))
        total = None
        for tr in tabela.find_all("tr"):
            linha = tr.get_text(" ", strip=True)
            if re.search(r"\bTotal\s*:", linha, flags=re.I):
                vals = [moeda_br_para_float(td.get_text(" ", strip=True)) for td in tr.find_all("td")]
                vals = [x for x in vals if x is not None]
                if vals:
                    total = vals[-1]
        if total is None and valores:
            total = valores[-1][1]
        if total is None:
            continue
        chave = (titulo, total)
        if chave in vistos:
            continue
        vistos.add(chave)
        saida.append({"programa": titulo, "categoria": classificar_programa(titulo), "total": total})
    return saida


def extrair_cnpjs_entidades(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    texto = soup.get_text(" ", strip=True)
    encontrados = []
    vistos = set()
    padrao = re.compile(r"(?<!\d)(\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2})(?!\d)")
    for match in padrao.finditer(texto):
        cnpj = limpar_cnpj(match.group(1))
        if cnpj in vistos:
            continue
        vistos.add(cnpj)
        ini = max(0, match.start() - 120)
        fim = min(len(texto), match.end() + 160)
        contexto = texto[ini:fim]
        encontrados.append({"cnpj": cnpj, "contexto": contexto})
    return encontrados


def _params_de_texto(texto: str) -> dict:
    """Tenta descobrir parametros mesmo quando o FNDE os esconde em href/JS."""
    out = {}
    texto = texto or ""
    for nome in ("p_programa", "p_tp_entidade", "p_cgc", "p_ano", "p_uf", "p_municipio"):
        m = re.search(rf"{nome}\s*(?:=|value\s*=|\.value\s*=)\s*['\"]?([^'\"&;\s)]+)", texto, re.I)
        if m:
            out[nome] = m.group(1)
    if "?" in texto:
        try:
            q = parse_qs(urlparse(texto).query)
            for k, v in q.items():
                if v:
                    out[k] = v[0]
        except Exception:
            pass
    return out


def extrair_rotas_descoberta(html: str) -> list[dict]:
    """Extrai combinacoes programa/tipo-entidade/CNPJ presentes em links e JavaScript."""
    soup = BeautifulSoup(html or "", "html.parser")
    rotas, vistos = [], set()
    candidatos = []
    for a in soup.find_all("a"):
        candidatos.extend([a.get("href", ""), a.get("onclick", "")])
    for tag in soup.find_all(True):
        for attr in ("onclick", "onchange", "action"):
            if tag.get(attr):
                candidatos.append(tag.get(attr))
    candidatos.append(html or "")

    for texto in candidatos:
        p = _params_de_texto(texto)
        programa = p.get("p_programa", "")
        tp = p.get("p_tp_entidade", "")
        cnpj = limpar_cnpj(p.get("p_cgc", ""))
        if not (programa or tp or cnpj):
            continue
        chave = (programa, tp, cnpj)
        if chave in vistos:
            continue
        vistos.add(chave)
        rotas.append({"programa": programa, "tp_entidade": tp, "cnpj": cnpj})
    return rotas


def extrair_links_resultados(html: str, base_url: str = "") -> list[str]:
    """Coleta links diretos de resultados FNDE, sem usar a tela protegida por captcha."""
    soup = BeautifulSoup(html or "", "html.parser")
    links = []
    vistos = set()
    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        if not href or href.lower().startswith("javascript:"):
            continue
        url = urljoin(base_url, href) if base_url else href
        u = url.lower()
        if "fnde.gov.br" not in u:
            continue
        if "liberacoes" not in u and "internet_fnde.liberacoes" not in u:
            continue
        if url in vistos:
            continue
        vistos.add(url)
        links.append(url)
    return links


def validar_referencia_araci(ibge: str, ano: int, totais: list[dict]) -> dict:
    if re.sub(r"\D", "", str(ibge)) != "2902104" or int(ano) != 2025:
        return {"aplicavel": False}
    consol = {}
    for item in totais:
        cat = item.get("categoria")
        val = item.get("total")
        if cat and val is not None:
            # Em pagina-resumo deve existir uma linha por bloco. Se houver repeticao,
            # mantemos o maior total, evitando somar o mesmo resumo duas vezes.
            consol[cat] = max(float(val), consol.get(cat, float("-inf")))
    comparacao = {}
    ok = True
    for cat, esperado in ARACI_REFERENCIA_2025.items():
        encontrado = consol.get(cat)
        confere = encontrado is not None and abs(encontrado - esperado) < 0.01
        comparacao[cat] = {"esperado": esperado, "encontrado": encontrado, "confere": confere}
        ok = ok and confere
    return {"aplicavel": True, "ok": ok, "comparacao": comparacao}


class FndeLiberacoesLegado:
    nome = "FNDE_LIBERACOES_LEGADO"

    def __init__(self, endpoints=None):
        self.endpoints = endpoints or DEFAULT_ENDPOINTS
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": os.getenv("FNDE_USER_AGENT", "APPfndeDOWELEVER/0.6.0"),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.5",
            "Connection": "keep-alive",
        })
        retry = Retry(total=3, connect=3, read=3, backoff_factor=0.8,
                      status_forcelist=(429, 500, 502, 503, 504), allowed_methods=frozenset(["GET"]))
        adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.timeout = int(os.getenv("FNDE_TIMEOUT", "60"))

    def _params(self, ano, uf, ibge=None, cnpj=None, programa="", tp_entidade=""):
        return {
            "p_ano": str(ano),
            "p_cgc": limpar_cnpj(cnpj),
            "p_municipio": codigo_fnde_municipio(ibge) if ibge else "",
            "p_programa": programa or "",
            "p_tp_entidade": tp_entidade or "",
            "p_uf": (uf or "").upper(),
            "p_verifica": "sigef",
        }

    def consultar(self, *, ano, uf, ibge=None, cnpj=None, municipio="", programa="", tp_entidade=""):
        params = self._params(ano, uf, ibge, cnpj, programa, tp_entidade)
        tentativas = []
        ultimo_erro = None
        for endpoint in self.endpoints:
            url = endpoint + "?" + urlencode(params)
            try:
                r = self.session.get(endpoint, params=params, timeout=self.timeout, allow_redirects=True)
                html = r.text
                validacao = validar_html(html)
                tentativa = {"endpoint": endpoint, "url_final": r.url, "http_status": r.status_code, "validacao": validacao}
                tentativas.append(tentativa)
                log(f"consulta endpoint={endpoint} status={r.status_code} ok={validacao['ok']} url={url}")
                if r.ok and validacao["ok"]:
                    totais = extrair_totais_programas(html)
                    return {
                        "ok": True,
                        "html": html,
                        "endpoint": endpoint,
                        "url_final": r.url,
                        "http_status": r.status_code,
                        "validacao": validacao,
                        "cnpjs_encontrados": extrair_cnpjs_entidades(html),
                        "totais_programas": totais,
                        "rotas_descoberta": extrair_rotas_descoberta(html),
                        "tentativas": tentativas,
                    }
            except Exception as exc:
                ultimo_erro = repr(exc)
                tentativas.append({"endpoint": endpoint, "erro": ultimo_erro})
                log(f"erro endpoint={endpoint} erro={ultimo_erro}")
        return {"ok": False, "erro": ultimo_erro or "Nenhum endpoint retornou HTML validado", "tentativas": tentativas}

    def _salvar_html(self, html: str, nome: str):
        arq = DOWNLOADS / nome
        arq.write_text(html, encoding="utf-8")
        salvar_storage(arq)
        return arq

    def baixar_municipio_completo(self, *, ano, uf, ibge, municipio):
        """Baixa o resumo municipal e percorre programa/tipo/entidade encontrados.

        O resumo municipal e a fonte dos totais iguais aos exibidos na consulta geral/PDF.
        Os detalhes servem como trilha de auditoria e nao substituem o total do resumo.
        """
        resumo = self.consultar(ano=ano, uf=uf, ibge=ibge, cnpj=None, municipio=municipio)
        if not resumo.get("ok"):
            return resumo

        nome_resumo = f"FNDE_{ibge}_{slug(municipio)}_{uf.upper()}_{ano}_MUNICIPIO_COMPLETO.html"
        arq_resumo = self._salvar_html(resumo["html"], nome_resumo)

        paginas = []
        entidades = {}
        rotas = resumo.get("rotas_descoberta", [])

        # 1) consulta por programa/tipo de entidade para descobrir todos os CNPJs.
        for rota in rotas:
            programa = rota.get("programa", "")
            tp = rota.get("tp_entidade", "")
            cnpj_rota = rota.get("cnpj", "")
            if cnpj_rota:
                entidades[(programa, tp, cnpj_rota)] = True
                continue
            if not (programa or tp):
                continue
            lista = self.consultar(ano=ano, uf=uf, ibge=ibge, programa=programa, tp_entidade=tp, municipio=municipio)
            if not lista.get("ok"):
                paginas.append({"tipo": "LISTA", "programa": programa, "tp_entidade": tp, "status": "ERRO", "detalhe": lista.get("erro")})
                continue
            nome_lista = f"FNDE_{ibge}_{slug(municipio)}_{uf.upper()}_{ano}_LISTA_{slug(programa or 'TODOS')}_{slug(tp or 'TODOS')}.html"
            arq_lista = self._salvar_html(lista["html"], nome_lista)
            paginas.append({"tipo": "LISTA", "programa": programa, "tp_entidade": tp, "status": "OK", "arquivo": str(arq_lista)})
            for ent in lista.get("cnpjs_encontrados", []):
                entidades[(programa, tp, ent["cnpj"])] = True
            for sub in lista.get("rotas_descoberta", []):
                c = limpar_cnpj(sub.get("cnpj", ""))
                if c:
                    entidades[(sub.get("programa") or programa, sub.get("tp_entidade") or tp, c)] = True

        # 2) se a pagina-resumo ja trouxer CNPJs, inclui-os.
        for ent in resumo.get("cnpjs_encontrados", []):
            entidades[("", "", ent["cnpj"])] = True

        # 3) baixa detalhes de cada entidade descoberta, com limite de seguranca configuravel.
        max_entidades = int(os.getenv("FNDE_MAX_ENTIDADES", "500"))
        detalhes = []
        for i, (programa, tp, cnpj) in enumerate(entidades.keys()):
            if i >= max_entidades:
                break
            det = self.consultar(ano=ano, uf=uf, ibge=ibge, cnpj=cnpj, programa=programa, tp_entidade=tp, municipio=municipio)
            if not det.get("ok"):
                detalhes.append({"cnpj": cnpj, "programa": programa, "tp_entidade": tp, "status": "ERRO"})
                continue
            nome_det = f"FNDE_{ibge}_{slug(municipio)}_{uf.upper()}_{ano}_{cnpj}_{slug(programa or 'TODOS')}.html"
            arq_det = self._salvar_html(det["html"], nome_det)
            detalhes.append({"cnpj": cnpj, "programa": programa, "tp_entidade": tp, "status": "OK", "arquivo": str(arq_det), "totais": det.get("totais_programas", [])})

        validacao_ref = validar_referencia_araci(ibge, ano, resumo.get("totais_programas", []))

        # PDF textual: apresentação humana gerada a partir do resumo estruturado.
        pdf_path = DOWNLOADS / f"FNDE_{ano}_{ibge}_{slug(municipio)}_{uf.upper()}.pdf"
        pdf_info = gerar_pdf(ibge=ibge, municipio=municipio, uf=uf.upper(), ano=ano,
                             programas=resumo.get("totais_programas", []), destino=pdf_path)
        pdf_validacao = validar_pdf_textual(str(pdf_path), [str(ibge), str(municipio)])
        salvar_storage(pdf_path)

        def sha256(path):
            h = hashlib.sha256()
            with Path(path).open("rb") as f:
                for bloco in iter(lambda: f.read(1024 * 1024), b""):
                    h.update(bloco)
            return h.hexdigest()

        status_validacao = "VALIDADO" if (not validacao_ref.get("aplicavel") or validacao_ref.get("ok")) and pdf_validacao.get("ok") else "PENDENTE_CONFERENCIA"

        meta = {
            "baixado_em": datetime.now().isoformat(timespec="seconds"),
            "fonte": self.nome,
            "modo": "MUNICIPIO_COMPLETO",
            "ibge": ibge,
            "municipio": municipio,
            "uf": uf,
            "ano": ano,
            "endpoint": resumo.get("endpoint"),
            "url_final": resumo.get("url_final"),
            "totais_programas": resumo.get("totais_programas", []),
            "validacao_referencia_araci_2025": validacao_ref,
            "rotas_descoberta": rotas,
            "quantidade_entidades_descobertas": len(entidades),
            "detalhes": detalhes,
            "paginas_intermediarias": paginas,
            "status_validacao": status_validacao,
            "pdf": {
                "arquivo": str(pdf_path),
                "engine": pdf_info.get("engine"),
                "validacao_textual": {k:v for k,v in pdf_validacao.items() if k != "texto"},
                "sha256": sha256(pdf_path),
                "template_version": "0.6.0",
            },
            "hashes": {"html_resumo_sha256": sha256(arq_resumo)},
        }
        meta_path = arq_resumo.with_suffix(".json")
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

        # Pacote unico da rodada: resumo + listas + detalhes + auditoria.
        zip_path = DOWNLOADS / f"FNDE_{ibge}_{slug(municipio)}_{uf.upper()}_{ano}_PACOTE_COMPLETO.zip"
        arquivos_rodada = [arq_resumo, meta_path, pdf_path]
        arquivos_rodada += [Path(x["arquivo"]) for x in paginas if x.get("arquivo")]
        arquivos_rodada += [Path(x["arquivo"]) for x in detalhes if x.get("arquivo")]
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            usados = set()
            for item in arquivos_rodada:
                if item.exists() and item.name not in usados:
                    zf.write(item, arcname=item.name)
                    usados.add(item.name)
        salvar_storage(zip_path)

        registrar(ibge=ibge, municipio=municipio, uf=uf, ano=ano, cnpj="", fonte=self.nome,
                  endpoint=resumo.get("endpoint", ""), arquivo=str(arq_resumo), status=status_validacao,
                  http_status=resumo.get("http_status"), tamanho_bytes=resumo["validacao"]["tamanho_bytes"],
                  detalhe=json.dumps({"modo":"MUNICIPIO_COMPLETO","entidades":len(entidades),"validacao_ref":validacao_ref}, ensure_ascii=False))

        return {
            "ok": True,
            "modo": "MUNICIPIO_COMPLETO",
            "arquivo": str(arq_resumo),
            "metadados": str(meta_path),
            "pdf": str(pdf_path),
            "pacote_zip": str(zip_path),
            "endpoint": resumo.get("endpoint"),
            "http_status": resumo.get("http_status"),
            "validacao": resumo.get("validacao"),
            "totais_programas": resumo.get("totais_programas", []),
            "validacao_referencia": validacao_ref,
            "quantidade_entidades_descobertas": len(entidades),
            "detalhes_baixados": len([x for x in detalhes if x.get("status") == "OK"]),
            "detalhes": detalhes,
            "status_validacao": status_validacao,
            "diagnostico": {"pdf_engine": pdf_info.get("engine"), "pdf_erro_playwright": pdf_info.get("erro_playwright"), "pdf_validacao": {k:v for k,v in pdf_validacao.items() if k != "texto"}},
        }

    def baixar(self, *, ano, uf, ibge, municipio, cnpj=None):
        # CNPJ informado mantem compatibilidade com a versao antiga; vazio usa municipio completo.
        if not limpar_cnpj(cnpj):
            return self.baixar_municipio_completo(ano=ano, uf=uf, ibge=ibge, municipio=municipio)

        res = self.consultar(ano=ano, uf=uf, ibge=ibge, cnpj=cnpj, municipio=municipio)
        if not res.get("ok"):
            registrar(ibge=ibge, municipio=municipio, uf=uf, ano=ano, cnpj=limpar_cnpj(cnpj), fonte=self.nome,
                      endpoint="", arquivo="", status="ERRO", http_status=None, tamanho_bytes=0,
                      detalhe=json.dumps(res, ensure_ascii=False))
            return res

        nome = nome_html(ibge, municipio, uf, ano, limpar_cnpj(cnpj))
        arq = DOWNLOADS / nome
        arq.write_text(res["html"], encoding="utf-8")
        meta = {"baixado_em": datetime.now().isoformat(timespec="seconds"), "fonte": self.nome, "ibge": ibge,
                "municipio": municipio, "uf": uf, "ano": ano, "cnpj_consultado": limpar_cnpj(cnpj),
                "endpoint": res["endpoint"], "url_final": res["url_final"], "http_status": res["http_status"],
                "validacao": res["validacao"], "cnpjs_encontrados": res["cnpjs_encontrados"],
                "totais_programas": res.get("totais_programas", [])}
        meta_path = arq.with_suffix(".json")
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        destino = salvar_storage(arq)
        registrar(ibge=ibge, municipio=municipio, uf=uf, ano=ano, cnpj=limpar_cnpj(cnpj), fonte=self.nome,
                  endpoint=res["endpoint"], arquivo=str(arq), status="OK", http_status=res["http_status"],
                  tamanho_bytes=res["validacao"]["tamanho_bytes"], detalhe=destino)
        res.update({"arquivo": str(arq), "metadados": str(meta_path), "storage": destino})
        return res
