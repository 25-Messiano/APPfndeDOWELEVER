from pathlib import Path
import streamlit as st

from core.downloader import baixar_fnde, baixar_fnde_municipio_completo
from core.municipios import ufs, municipios_da_uf

st.set_page_config(page_title="Painel FNDE", layout="wide")
st.title("Painel FNDE")
st.caption("Consulta municipal completa, auditoria e PDF textual no padrão visual FNDE/SIGEF.")

lista_ufs = ufs()
idx_ba = lista_ufs.index("BA") if "BA" in lista_ufs else 0
uf = st.selectbox("UF", lista_ufs, index=idx_ba)
lista_m = municipios_da_uf(uf)
nomes = [m["municipio"] for m in lista_m]
idx_araci = nomes.index("Araci") if uf == "BA" and "Araci" in nomes else 0
municipio_nome = st.selectbox("Município", nomes, index=idx_araci)
registro = next(m for m in lista_m if m["municipio"] == municipio_nome)

c1, c2, c3 = st.columns(3)
with c1:
    st.text_input("Código IBGE", value=registro["ibge"], disabled=True)
with c2:
    st.text_input("Código FNDE (6 dígitos)", value=registro["codigo_fnde_6"], disabled=True)
with c3:
    ano = st.number_input("Ano", min_value=2000, max_value=2100, value=2025, step=1)

modo = st.selectbox("Modo de download", ["Município completo - todas as entidades", "CNPJ específico"])
cnpj = st.text_input("CNPJ", value="", disabled=modo.startswith("Município completo"))

st.info("O nome/IBGE da base municipal orienta o roteamento. O conteúdo interno confirma a identidade e divergências são registradas, não descartadas silenciosamente.")

if st.button("Baixar e gerar PDF FNDE", type="primary"):
    with st.spinner("Consultando FNDE, percorrendo entidades e gerando auditoria..."):
        if modo.startswith("Município completo"):
            res = baixar_fnde_municipio_completo(registro["ibge"], registro["municipio"], registro["uf"], int(ano))
        else:
            res = baixar_fnde(registro["ibge"], registro["municipio"], registro["uf"], int(ano), cnpj.strip())
    if res.get("ok"):
        st.success("Consulta FNDE concluída.")
        cols = st.columns(4)
        cols[0].metric("Entidades descobertas", res.get("quantidade_entidades_descobertas", 0))
        cols[1].metric("Detalhes baixados", res.get("detalhes_baixados", 0))
        cols[2].metric("HTTP", res.get("http_status", "-"))
        cols[3].metric("Status", res.get("status_validacao", "COLETADO"))

        totais = res.get("totais_programas", [])
        if totais:
            st.subheader("Totais municipais encontrados")
            st.dataframe(totais, use_container_width=True)

        ref = res.get("validacao_referencia", {})
        if ref.get("aplicavel"):
            st.subheader("Validação - Araci/BA 2025")
            linhas = [{"Programa": k, **v} for k, v in ref.get("comparacao", {}).items()]
            st.dataframe(linhas, use_container_width=True)
            if ref.get("ok"):
                st.success("Referência de Araci conferiu integralmente.")
            else:
                st.warning("Existe divergência. O material foi preservado para auditoria e não deve ser tratado como validado.")

        for chave, rotulo, mime in [
            ("pdf", "Baixar PDF textual", "application/pdf"),
            ("arquivo", "Baixar HTML principal", "text/html"),
            ("metadados", "Baixar JSON de auditoria", "application/json"),
            ("pacote_zip", "Baixar pacote completo", "application/zip"),
        ]:
            caminho = Path(res.get(chave, ""))
            if caminho.exists():
                st.download_button(rotulo, data=caminho.read_bytes(), file_name=caminho.name, mime=mime, key=chave)
        st.expander("Diagnóstico técnico").json(res.get("diagnostico", res.get("validacao", {})))
    else:
        st.error("A consulta não retornou uma página FNDE validada.")
        st.json(res)
