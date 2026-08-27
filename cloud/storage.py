import os
from pathlib import Path


def salvar_local(origem: Path) -> str:
    return str(origem)


def salvar(origem: Path) -> str:
    backend = os.getenv("STORAGE_BACKEND", "local").lower()
    if backend == "s3":
        from .s3_storage import enviar
        return enviar(origem)
    return salvar_local(origem)
