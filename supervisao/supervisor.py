"""Supervisao verificavel dos motores BB/TCM/FNDE; a IA nunca grava valores."""
from __future__ import annotations

import contextvars
import functools
import hashlib
import inspect
import io
import json
import math
import os
import re
import sqlite3
import threading
import time
import uuid
import zipfile
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

_CURRENT = contextvars.ContextVar("app_supervisor", default=None)
_LOCK = threading.RLock()
SOURCES = {"BB", "TCM", "FNDE", "GERAL"}
VERSION = "1.2.0"
SECRET_RE = re.compile(r"sk-[A-Za-z0-9_-]+|Bearer\s+[A-Za-z0-9._-]+", re.I)
PRIVATE_RE = re.compile(r"-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----", re.S)


class SupervisorBlocked(ValueError):
    pass


class SupervisorAIPaused(SupervisorBlocked):
    """Etapa pendente; nao autoriza execucao sem revisao da IA."""
    supervisor_ai_paused = True


def redact(value):
    if isinstance(value, dict):
        return {str(k): ("[PROTEGIDO]" if any(s in str(k).lower() for s in
                ("token", "api_key", "password", "private_key", "service_account", "authorization"))
                else redact(v)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value[:200]]
    if isinstance(value, str):
        return SECRET_RE.sub("[PROTEGIDO]", PRIVATE_RE.sub("[PROTEGIDO]", value))[:1500]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return "[OBJETO]"


def _path():
    return Path(os.getenv("SUPERVISOR_DB_PATH", "/tmp/appdowelever_supervisor.sqlite3"))


def _connect():
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(path, timeout=15)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("CREATE TABLE IF NOT EXISTS operations (id TEXT PRIMARY KEY, updated REAL, payload TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS ai_calls (id TEXT PRIMARY KEY, created REAL)")
    return c


def _save(report):
    safe = redact(report)
    with _LOCK, _connect() as c:
        c.execute("INSERT OR REPLACE INTO operations VALUES (?,?,?)",
                  (safe["id"], time.time(), json.dumps(safe, ensure_ascii=False)))
    return safe


def _bucket():
    return (os.getenv("SUPERVISOR_GCS_BUCKET") or os.getenv("GCS_BUCKET")
            or os.getenv("TCM_GCS_BUCKET") or os.getenv("FNDE_GCS_BUCKET") or "").strip()


def persist_cloud(report):
    """Somente metadados saneados. Falha de auditoria aparece sem mascarar o motor."""
    bucket = _bucket()
    if not bucket or os.getenv("SUPERVISOR_GCS_SYNC", "true").lower() in {"0", "false", "no"}:
        report["auditoria_cloud"] = "DESATIVADA"
        return
    try:
        from .gcs_access import storage_client
        obj = f"SUPERVISOR/OPERACOES/{report['iniciado_em'][:10]}/{report['id']}.json"
        safe = redact({**report, "auditoria_cloud": "GRAVADA"})
        storage_client().bucket(bucket).blob(obj).upload_from_string(
            json.dumps(safe, ensure_ascii=False), content_type="application/json",
            timeout=3, retry=None)
        report["auditoria_cloud"] = "GRAVADA"
        report["objeto_auditoria"] = obj
    except Exception as exc:
        report["auditoria_cloud"] = "PENDENTE"
        report["erro_auditoria"] = redact(f"{type(exc).__name__}: {exc}")


def recent_reports(limit=100):
    with _LOCK, _connect() as c:
        rows = c.execute("SELECT payload FROM operations ORDER BY updated DESC LIMIT ?",
                         (min(max(int(limit), 1), 300),)).fetchall()
    return [json.loads(row[0]) for row in rows]


def cloud_reports(days=2, limit=100):
    if not _bucket():
        return []
    from .gcs_access import storage_client
    c = storage_client()
    names = []
    for delta in range(min(max(int(days), 1), 7)):
        day = (datetime.now(timezone.utc)-timedelta(days=delta)).strftime("%Y-%m-%d")
        names.extend(c.list_blobs(_bucket(), prefix=f"SUPERVISOR/OPERACOES/{day}/",
                                  max_results=500, timeout=8, retry=None))
    reports = []
    for blob in sorted(names, key=lambda b:b.updated or datetime.min.replace(tzinfo=timezone.utc),
                       reverse=True)[:min(int(limit), 150)]:
        if (blob.size or 0) > 100000:
            continue
        item = json.loads(blob.download_as_bytes(timeout=8, retry=None))
        if (isinstance(item, dict) and re.fullmatch(r"[a-f0-9]{32}", str(item.get("id", "")))
                and item.get("status") in {"EXECUTANDO", "CONCLUIDO", "PENDENTE", "BLOQUEADO", "ERRO"}):
            reports.append(redact(item))
    return reports


def merged_reports(remote=None, limit=100):
    items = {r["id"]: r for r in (remote or [])}
    items.update({r["id"]: r for r in recent_reports(limit)})
    return sorted(items.values(), key=lambda r:r.get("iniciado_em", ""), reverse=True)[:limit]


def _identity(arguments):
    result = {}
    candidates = [arguments]
    for key in ("ident", "identity", "expected_identity", "identidade", "meta", "extracao", "payload"):
        obj = arguments.get(key)
        if isinstance(obj, dict):
            candidates.extend([obj, obj.get("identidade", {})])
        elif obj is not None:
            candidates.append({k:getattr(obj, k, None) for k in ("ibge","uf","municipio","ano")})
    aliases = {"ibge":("ibge",), "uf":("uf",), "municipio":("municipio","municipality"),
               "ano":("ano","year"), "job_id":("job_id","jid")}
    for obj in candidates:
        if not isinstance(obj, dict):
            continue
        for canonical, keys in aliases.items():
            for key in keys:
                value = obj.get(key)
                if isinstance(value, (str, int)) and value != "":
                    result.setdefault(canonical, str(value)[:120])
    return result


def _summary(result):
    if isinstance(result, list):
        summary = {"quantidade": len(result)}
        if result and all(isinstance(item, dict) for item in result):
            summary["programas"] = [
                {k: item[k] for k in ("programa", "categoria", "total") if k in item}
                for item in result[:100]
            ]
        return redact(summary)
    if isinstance(result, tuple):
        result = next((r for r in reversed(result) if isinstance(r, dict)), {})
    if not isinstance(result, dict):
        return {}
    keys = ("status", "ok", "concluido", "gravados", "criados", "atualizados",
            "quantidade_planilhas", "quantidade_pagamentos", "quantidade",
            "municipal_ok", "mensal_ok", "geral_ok", "backend", "auditoria_cloud", "erros", "ausentes", "error", "fontes",
            "status_validacao", "quantidade_entidades_descobertas", "detalhes_baixados",
            "http_status", "paginas", "caracteres", "captcha_detectado", "tamanho_bytes")
    summary = {k:result[k] for k in keys if k in result}
    if isinstance(result.get("resumo"), dict):
        summary["resumo"] = {k:v for k,v in result["resumo"].items()
                            if isinstance(v,(str,int,float,bool))}
    for key in ("cloud", "anual", "planilha_geral", "planilha_geral_mensal", "resultado", "storage", "validacao", "validacao_referencia"):
        item = result.get(key)
        if isinstance(item, dict):
            summary[key] = _summary(item)
    for key in ("dados", "dados_centavos", "competencias"):
        if isinstance(result.get(key), (list,dict)):
            summary["quantidade_"+key] = len(result[key])
    return redact(summary)


def _pending(summary):
    if not isinstance(summary, dict):
        return False
    status = (str(summary.get("status", "")) + " " + str(summary.get("status_validacao", ""))).upper()
    if (summary.get("ok") is False or summary.get("concluido") is False
            or any(summary.get(k) is False for k in ("geral_ok", "mensal_ok", "municipal_ok"))
            or any(s in status for s in ("PENDENTE", "PARCIAL", "FALH", "ERRO"))
            or summary.get("backend") == "local_fallback" or "SEM_FONTE" in status
            or any(isinstance(summary.get(k),(int,float)) and summary[k]>0 for k in ("erros","ausentes"))):
        return True
    return any(_pending(v) for v in summary.values() if isinstance(v,dict))


def validate_identity(arguments):
    ident = _identity(arguments)
    if "ibge" in ident and not re.fullmatch(r"\d{7}", ident["ibge"]):
        raise SupervisorBlocked("SUPERVISOR: codigo IBGE invalido.")
    if "ano" in ident and not (ident["ano"].isdigit() and 1900 <= int(ident["ano"]) <= 2100):
        raise SupervisorBlocked("SUPERVISOR: ano invalido.")
    if "uf" in ident and not re.fullmatch(r"[A-Za-z]{2}", ident["uf"]):
        raise SupervisorBlocked("SUPERVISOR: UF invalida.")


def validate_archive(data, *, workbook=False):
    if not isinstance(data, bytes) or not data:
        raise SupervisorBlocked("SUPERVISOR: arquivo vazio.")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            if not z.infolist() or z.testzip() is not None:
                raise ValueError("integridade ZIP")
            if workbook and not {"[Content_Types].xml", "xl/workbook.xml"} <= set(z.namelist()):
                raise ValueError("estrutura Excel")
    except Exception as exc:
        raise SupervisorBlocked("SUPERVISOR: arquivo ZIP/Excel invalido.") from exc


def validate_monthly(arguments):
    validate_identity(arguments)
    data = arguments.get("dados")
    if not isinstance(data, dict) or not data:
        raise SupervisorBlocked("SUPERVISOR: dados mensais ausentes.")
    fonte = str(arguments.get("fonte", "")).upper()
    from appbb_processing.monthly_master import BB_COLUMNS, TCM_COLUMNS, FNDE_COLUMNS
    allowed = {"BB": set(BB_COLUMNS), "TCM": set(TCM_COLUMNS),
               "FNDE": set(FNDE_COLUMNS)}.get(fonte)
    if allowed is None:
        raise SupervisorBlocked("SUPERVISOR: fonte mensal desconhecida.")
    for comp, values in data.items():
        match = re.fullmatch(r"(0[1-9]|1[0-2])/(\d{4})", str(comp))
        if not match or int(match[2]) != int(arguments["ano"]):
            raise SupervisorBlocked("SUPERVISOR: competencia diverge do ano.")
        if not isinstance(values, dict) or not values or set(values)-allowed:
            raise SupervisorBlocked("SUPERVISOR: campos fora das colunas da fonte.")
        for value in values.values():
            try:
                number = Decimal(str(value))
            except (InvalidOperation, ValueError):
                raise SupervisorBlocked("SUPERVISOR: valor mensal nao numerico.")
            if isinstance(value, bool) or not number.is_finite():
                raise SupervisorBlocked("SUPERVISOR: valor mensal nao finito.")


def _preflight(arguments, guard):
    if guard in {"monthly", "identity"}:
        validate_identity(arguments)
    if guard == "monthly":
        validate_monthly(arguments)
    if guard == "archive":
        data = arguments.get("zip_bytes", arguments.get("data"))
        if data is None and arguments.get("caminho"):
            data = Path(arguments["caminho"]).read_bytes()
        name = str(arguments.get("object_name", arguments.get("obj", ""))).lower()
        mime = str(arguments.get("content_type", "")).lower()
        if data is not None and (name.endswith((".xlsm",".xlsx",".zip")) or
                "spreadsheet" in mime or "macroenabled" in mime or "zip_bytes" in arguments or "caminho" in arguments):
            validate_archive(data, workbook=name.endswith((".xlsm",".xlsx")) or "spreadsheet" in mime or "macroenabled" in mime)
    if guard == "pdf":
        data = arguments.get("pdf_bytes")
        if not isinstance(data, bytes) or not data.startswith(b"%PDF-"):
            raise SupervisorBlocked("SUPERVISOR: conteudo recebido nao e PDF.")


def _postflight(result, arguments, guard):
    if guard == "monthly" and isinstance(result, tuple):
        data, report = result
        from appbb_processing.monthly_master import _verify_pi_report_bytes, validate_monthly_master_bytes
        validate_monthly_master_bytes(data, expected_year=int(arguments["ano"]))
        checked = _verify_pi_report_bytes(data, report)
        if checked.get("quantidade") != report.get("gravados") or report.get("campos_nao_reconhecidos"):
            raise SupervisorBlocked("SUPERVISOR: celulas mensais nao conferem com o relatorio.")
    if guard == "workbook" and isinstance(result, tuple) and isinstance(result[0], bytes):
        validate_archive(result[0], workbook=True)


def supervised(source, operation, guard=None):
    """Envolve as funcoes reais, preservando assinaturas e excecoes originais."""
    def decorate(func):
        signature = inspect.signature(func)

        @functools.wraps(func)
        def wrapped(*args, **kwargs):
            arguments = dict(signature.bind(*args, **kwargs).arguments)
            parent = _CURRENT.get()
            chosen = str(arguments.get("fonte") or source).upper()
            if chosen == "AUTO":
                chosen = "GERAL"
            report = {"versao": VERSION, "id": uuid.uuid4().hex,
                      "parent_id": parent["id"] if parent else None,
                      "fonte": chosen, "operacao": operation, "identidade": _identity(arguments),
                      "status": "EXECUTANDO", "iniciado_em": datetime.now(timezone.utc).isoformat(),
                      "etapas": [], "auditoria_cloud": "PENDENTE"}
            token = _CURRENT.set(report)
            started = time.monotonic()
            try:
                _save(report)
                _preflight(arguments, guard)
                report["resumo"] = {"fase":"PRE_EXECUCAO", "contrato_previo":"APROVADO", "resultado_ainda_nao_produzido":True}
                from .supervisor_auto import review_stage
                review_stage(report, "ANTES")
                result = func(*args, **kwargs)
                _postflight(result, arguments, guard)
                returned = result[-1] if isinstance(result,tuple) and result else result
                for k,v in _identity({"payload":returned}).items():
                    report["identidade"].setdefault(k,v)
                report["resumo"] = _summary(result)
                report["alertas"] = sum(e["status"] in {"PENDENTE","BLOQUEADO","ERRO"} for e in report["etapas"])
                report["status"] = "PENDENTE" if (_pending(report["resumo"]) or report["alertas"]) else "CONCLUIDO"
                review_stage(report, "DEPOIS")
                return result
            except Exception as exc:
                report["status"] = "BLOQUEADO" if (isinstance(exc,(SupervisorBlocked,ValueError)) or getattr(exc,"supervisor_ai_paused",False)) else "ERRO"
                report["erro"] = redact(f"{type(exc).__name__}: {exc}")
                if not getattr(exc, "supervisor_ai_paused", False):
                    try:
                        from .supervisor_auto import review_stage
                        review_stage(report, "ERRO")
                    except Exception:
                        pass  # O erro original do motor deve ser preservado.
                raise
            finally:
                report["finalizado_em"] = datetime.now(timezone.utc).isoformat()
                report["duracao_segundos"] = round(time.monotonic()-started,3)
                _CURRENT.reset(token)
                if parent is not None:
                    persist_cloud(report)
                    parent["etapas"].append({k:report.get(k) for k in
                        ("id","fonte","operacao","identidade","status","erro","resumo","duracao_segundos","objeto_auditoria")})
                    parent["etapas"] = parent["etapas"][-200:]
                else:
                    persist_cloud(report)
                try:
                    _save(report)
                except Exception:
                    print("SUPERVISOR_AUDITORIA_LOCAL_INDISPONIVEL", flush=True)
        return wrapped
    return decorate


def ai_budget():
    now = datetime.now(timezone.utc)
    day = now.replace(hour=0,minute=0,second=0,microsecond=0).timestamp()
    with _LOCK, _connect() as c:
        used, last = c.execute("SELECT count(*),max(created) FROM ai_calls WHERE created>=?", (day,)).fetchone()
    return {"utilizadas":used, "limite":max(0,int(os.getenv("SUPERVISOR_AI_DAILY_LIMIT","20"))), "ultima":last}


def reserve_ai_call(*, automatic=False):
    now = datetime.now(timezone.utc)
    day = now.replace(hour=0,minute=0,second=0,microsecond=0).timestamp()
    with _LOCK, _connect() as c:
        table = "automatic_ai_calls" if automatic else "ai_calls"
        c.execute(f"CREATE TABLE IF NOT EXISTS {table} (id TEXT PRIMARY KEY, created REAL)")
        c.execute("BEGIN IMMEDIATE")
        used,last = c.execute(f"SELECT count(*),max(created) FROM {table} WHERE created>=?", (day,)).fetchone()
        limit = max(0,int(os.getenv("SUPERVISOR_AUTO_AI_DAILY_LIMIT" if automatic else "SUPERVISOR_AI_DAILY_LIMIT", "0" if automatic else "20")))
        if (not automatic or limit > 0) and used >= limit:
            raise SupervisorBlocked("Limite diario de orientacoes atingido.")
        if not automatic and last and now.timestamp()-last < 10:
            raise SupervisorBlocked("Aguarde alguns segundos antes da proxima orientacao.")
        call_id=uuid.uuid4().hex
        c.execute(f"INSERT INTO {table} VALUES (?,?)",(call_id,now.timestamp()))
    return call_id

