class FndeSigefCaptcha:
    """Fallback documentado. Nao tenta contornar CAPTCHA."""
    nome = "FNDE_SIGEF_CAPTCHA"

    def consultar(self, **kwargs):
        return {
            "ok": False,
            "status": "CAPTCHA_REQUER_INTERACAO",
            "mensagem": "Rota SIGEF nova mantida apenas como fallback manual; o app nao contorna CAPTCHA."
        }
