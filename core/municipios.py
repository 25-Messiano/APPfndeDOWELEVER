import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from rapidfuzz.fuzz import ratio

ROOT = Path(__file__).resolve().parents[1]
BASE_JSON = ROOT / "data" / "municipios_brasil.json"


def _norm(texto: str) -> str:
    t = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^A-Z0-9]+", " ", t.upper()).strip()


@lru_cache(maxsize=1)
def carregar_municipios() -> list[dict]:
    data = json.loads(BASE_JSON.read_text(encoding="utf-8"))
    return data.get("municipios", [])


def ufs() -> list[str]:
    return sorted({m["uf"] for m in carregar_municipios()})


def municipios_da_uf(uf: str) -> list[dict]:
    uf = (uf or "").upper()
    return sorted([m for m in carregar_municipios() if m["uf"] == uf], key=lambda x: _norm(x["municipio"]))


def por_ibge(ibge: str):
    d = re.sub(r"\D", "", str(ibge or ""))
    return next((m for m in carregar_municipios() if m["ibge"] == d), None)


def por_nome_uf(municipio: str, uf: str, limiar: int = 88):
    alvo = _norm(municipio)
    candidatos = municipios_da_uf(uf)
    exato = next((m for m in candidatos if _norm(m["municipio"]) == alvo), None)
    if exato:
        return {**exato, "score": 100, "aproximado": False}
    if not candidatos:
        return None
    melhor = max(candidatos, key=lambda m: ratio(alvo, _norm(m["municipio"])))
    score = int(round(ratio(alvo, _norm(melhor["municipio"]))))
    if score < limiar:
        return None
    return {**melhor, "score": score, "aproximado": True}


def validar_identidade(ibge: str, municipio: str, uf: str) -> dict:
    base = por_ibge(ibge)
    if not base:
        aprox = por_nome_uf(municipio, uf)
        return {"ok": bool(aprox), "status": "IBGE_NAO_LOCALIZADO", "base": aprox, "bloquear": False}
    score = int(round(ratio(_norm(municipio), _norm(base["municipio"]))))
    uf_ok = base["uf"] == (uf or "").upper()
    nome_ok = score >= 88
    divergencias = []
    if not uf_ok:
        divergencias.append("UF")
    if not nome_ok:
        divergencias.append("MUNICIPIO")
    return {
        "ok": uf_ok and nome_ok,
        "status": "OK" if uf_ok and nome_ok else "DIVERGENCIA_IDENTIFICACAO",
        "base": base,
        "score_nome": score,
        "divergencias": divergencias,
        "bloquear": False,
    }
