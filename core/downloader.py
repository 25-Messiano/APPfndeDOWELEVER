from fontes.fnde_liberacoes_legado import FndeLiberacoesLegado


def baixar_fnde(ibge: str, municipio: str, uf: str, ano: int, cnpj: str = ""):
    fonte = FndeLiberacoesLegado()
    return fonte.baixar(ibge=ibge, municipio=municipio, uf=uf, ano=ano, cnpj=cnpj or None)
