import re
from pathlib import Path
from core.municipios import validar_identidade

PADRAO = re.compile(r"FNDE[_-](?P<ano>\d{4})[_-](?P<ibge>\d{7})[_-](?P<municipio>.+?)[_-](?P<uf>[A-Z]{2})(?:\.[A-Za-z0-9]+)?$", re.I)


def identificar_nome_externo(nome: str) -> dict:
    stem = Path(nome).name
    m = PADRAO.match(stem)
    if not m:
        return {"ok": False, "status": "NOME_FORA_DO_PADRAO", "nome": stem}
    d = m.groupdict()
    d["uf"] = d["uf"].upper()
    d["municipio"] = re.sub(r"[_-]+", " ", d["municipio"]).strip()
    d["ano"] = int(d["ano"])
    val = validar_identidade(d["ibge"], d["municipio"], d["uf"])
    return {"ok": True, "status": "OK" if val.get("ok") else "DIVERGENCIA_IDENTIFICACAO", **d, "validacao_base": val}
