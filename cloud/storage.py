import os
from pathlib import Path
from supervisao.supervisor import supervised


def salvar_local(origem: Path) -> str:
    return str(origem)


@supervised("FNDE", "armazenar_arquivo")
def salvar(origem: Path) -> str:
    backend = os.getenv("STORAGE_BACKEND", "local").lower()
    if backend == "s3":
        from .s3_storage import enviar
        return enviar(origem)
    return salvar_local(origem)

