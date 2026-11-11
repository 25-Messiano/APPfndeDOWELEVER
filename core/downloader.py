from fontes.fnde_liberacoes_legado import FndeLiberacoesLegado
from supervisao.supervisor import supervised


@supervised("FNDE", "download_fnde_cnpj")
def baixar_fnde(ibge: str, municipio: str, uf: str, ano: int, cnpj: str = ""):
    fonte = FndeLiberacoesLegado()
    return fonte.baixar(ibge=ibge, municipio=municipio, uf=uf, ano=ano, cnpj=cnpj or None)


@supervised("FNDE", "download_fnde_municipio_completo")
def baixar_fnde_municipio_completo(ibge: str, municipio: str, uf: str, ano: int):
    fonte = FndeLiberacoesLegado()
    return fonte.baixar_municipio_completo(ibge=ibge, municipio=municipio, uf=uf, ano=ano)

