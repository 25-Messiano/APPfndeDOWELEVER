from bs4 import BeautifulSoup

MARCADORES = ["FNDE", "LIBERA", "MUNIC", "ENTIDADE", "PROGRAMA", "VALOR"]


def validar_html(html: str) -> dict:
    texto = BeautifulSoup(html or "", "html.parser").get_text(" ", strip=True)
    texto_up = texto.upper()
    achados = [m for m in MARCADORES if m in texto_up]
    captcha = "CAPTCHA" in texto_up or "RECAPTCHA" in texto_up
    return {
        "ok": len(html or "") >= 500 and len(achados) >= 2 and not captcha,
        "tamanho_bytes": len((html or "").encode("utf-8", errors="ignore")),
        "marcadores": achados,
        "captcha_detectado": captcha,
        "titulo": BeautifulSoup(html or "", "html.parser").title.string.strip() if BeautifulSoup(html or "", "html.parser").title and BeautifulSoup(html or "", "html.parser").title.string else ""
    }
