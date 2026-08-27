import json
import os
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

from core.nomes_arquivos import nome_html
from core.validacao_html import validar_html
from core.logger import log
from database.db import registrar
from cloud.storage import salvar as salvar_storage

ROOT = Path(__file__).resolve().parents[1]
DOWNLOADS = ROOT / "downloads"
DOWNLOADS.mkdir(parents=True, exist_ok=True)

DEFAULT_ENDPOINTS = [
    "https://www.fnde.gov.br/pls/edw_fnde/internet_fnde.liberacoes_result_pc",
    "https://www.fnde.gov.br/pls/simad/internet_fnde.liberacoes_result_pc",
]


def codigo_fnde_municipio(ibge: str) -> str:
    d = re.sub(r"\D", "", str(ibge))
    if len(d) != 7:
        raise ValueError("IBGE deve possuir 7 digitos")
    return d[:6]


def limpar_cnpj(cnpj: str) -> str:
    return re.sub(r"\D", "", cnpj or "")


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


class FndeLiberacoesLegado:
    nome = "FNDE_LIBERACOES_LEGADO"

    def __init__(self, endpoints=None):
        self.endpoints = endpoints or DEFAULT_ENDPOINTS
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": os.getenv("FNDE_USER_AGENT", "APPfndeDOWELEVER/0.1"),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.5",
            "Connection": "keep-alive",
        })
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
                tentativa = {
                    "endpoint": endpoint,
                    "url_final": r.url,
                    "http_status": r.status_code,
                    "validacao": validacao,
                }
                tentativas.append(tentativa)
                log(f"consulta endpoint={endpoint} status={r.status_code} ok={validacao['ok']} url={url}")
                if r.ok and validacao["ok"]:
                    return {
                        "ok": True,
                        "html": html,
                        "endpoint": endpoint,
                        "url_final": r.url,
                        "http_status": r.status_code,
                        "validacao": validacao,
                        "cnpjs_encontrados": extrair_cnpjs_entidades(html),
                        "tentativas": tentativas,
                    }
            except Exception as exc:
                ultimo_erro = repr(exc)
                tentativas.append({"endpoint": endpoint, "erro": ultimo_erro})
                log(f"erro endpoint={endpoint} erro={ultimo_erro}")
        return {"ok": False, "erro": ultimo_erro or "Nenhum endpoint retornou HTML validado", "tentativas": tentativas}

    def baixar(self, *, ano, uf, ibge, municipio, cnpj=None):
        res = self.consultar(ano=ano, uf=uf, ibge=ibge, cnpj=cnpj, municipio=municipio)
        if not res.get("ok"):
            registrar(ibge=ibge, municipio=municipio, uf=uf, ano=ano, cnpj=limpar_cnpj(cnpj), fonte=self.nome,
                      endpoint="", arquivo="", status="ERRO", http_status=None, tamanho_bytes=0,
                      detalhe=json.dumps(res, ensure_ascii=False))
            return res

        nome = nome_html(ibge, municipio, uf, ano, limpar_cnpj(cnpj))
        arq = DOWNLOADS / nome
        arq.write_text(res["html"], encoding="utf-8")

        meta = {
            "baixado_em": datetime.now().isoformat(timespec="seconds"),
            "fonte": self.nome,
            "ibge": ibge,
            "municipio": municipio,
            "uf": uf,
            "ano": ano,
            "cnpj_consultado": limpar_cnpj(cnpj),
            "endpoint": res["endpoint"],
            "url_final": res["url_final"],
            "http_status": res["http_status"],
            "validacao": res["validacao"],
            "cnpjs_encontrados": res["cnpjs_encontrados"],
        }
        meta_path = arq.with_suffix(".json")
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

        destino = salvar_storage(arq)
        registrar(ibge=ibge, municipio=municipio, uf=uf, ano=ano, cnpj=limpar_cnpj(cnpj), fonte=self.nome,
                  endpoint=res["endpoint"], arquivo=str(arq), status="OK", http_status=res["http_status"],
                  tamanho_bytes=res["validacao"]["tamanho_bytes"], detalhe=destino)

        res.update({"arquivo": str(arq), "metadados": str(meta_path), "storage": destino})
        return res
