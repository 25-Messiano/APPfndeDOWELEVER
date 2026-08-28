import re
import unicodedata


def slug(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode("ascii")
    texto = re.sub(r"[^A-Za-z0-9]+", "_", texto).strip("_")
    return texto.upper() or "SEM_NOME"


def nome_html(ibge: str, municipio: str, uf: str, ano: int, cnpj: str = "") -> str:
    sufixo = f"_{re.sub(r'\D', '', cnpj)}" if cnpj else ""
    return f"FNDE_{ibge}_{slug(municipio)}_{uf.upper()}_{ano}{sufixo}.html"
