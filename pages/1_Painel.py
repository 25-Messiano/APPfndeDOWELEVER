from pathlib import Path
import streamlit as st

from core.downloader import baixar_fnde, baixar_fnde_municipio_completo

st.set_page_config(page_title="Painel FNDE", layout="wide")
st.title("Painel FNDE")

c1, c2, c3 = st.columns(3)
with c1:
    ibge = st.text_input("Codigo IBGE", value="2902708", max_chars=7)
    municipio = st.text_input("Municipio", value="Araci")
with c2:
    uf = st.text_input("UF", value="BA", max_chars=2)
    ano = st.number_input("Ano", min_value=2000, max_value=2100, value=2025, step=1)
with c3:
    modo = st.selectbox("Modo de download", ["Municipio completo - todas as entidades", "CNPJ especifico"])
    cnpj = st.text_input("CNPJ", value="14.232.086/0001-92", disabled=modo.startswith("Municipio completo"))

st.caption("Para obter os mesmos totais da consulta geral/PDF, use 'Municipio completo - todas as entidades'. O CNPJ da Prefeitura nao representa sozinho todos os repasses do municipio.")

if st.button("Baixar arquivo FNDE", type="primary"):
    with st.spinner("Consultando FNDE e percorrendo as entidades..."):
        if modo.startswith("Municipio completo"):
            res = baixar_fnde_municipio_completo(ibge.strip(), municipio.strip(), uf.strip(), int(ano))
        else:
            res = baixar_fnde(ibge.strip(), municipio.strip(), uf.strip(), int(ano), cnpj.strip())
    if res.get("ok"):
        st.success("Consulta FNDE concluida com sucesso.")
        st.write("Modo:", res.get("modo", "CNPJ_ESPECIFICO"))
        st.write("Endpoint:", res.get("endpoint"))
        st.write("HTTP:", res.get("http_status"))
        st.write("Arquivo principal:", res.get("arquivo"))
        st.write("Metadados:", res.get("metadados"))
        if res.get("quantidade_entidades_descobertas") is not None:
            st.metric("Entidades descobertas", res.get("quantidade_entidades_descobertas"))
            st.metric("Detalhes baixados", res.get("detalhes_baixados", 0))

        totais = res.get("totais_programas", [])
        if totais:
            st.subheader("Totais oficiais por programa - pagina resumo do municipio")
            st.dataframe(totais, use_container_width=True)

        ref = res.get("validacao_referencia", {})
        if ref.get("aplicavel"):
            st.subheader("Conferencia com o PDF de referencia - Araci/BA 2025")
            linhas = []
            for programa, item in ref.get("comparacao", {}).items():
                linhas.append({"Programa": programa, "Esperado": item.get("esperado"), "Encontrado": item.get("encontrado"), "Confere": item.get("confere")})
            st.dataframe(linhas, use_container_width=True)
            if ref.get("ok"):
                st.success("Todos os totais conferem com o PDF de referencia.")
            else:
                st.warning("Ainda existe divergencia. O arquivo foi mantido para auditoria; nao considerar validado enquanto houver diferenca.")

        st.json(res.get("validacao", {}))
        caminho = Path(res["arquivo"])
        if caminho.exists():
            st.download_button("Baixar HTML principal para o computador", data=caminho.read_bytes(), file_name=caminho.name, mime="text/html")
        meta = Path(res.get("metadados", ""))
        if meta.exists():
            st.download_button("Baixar JSON de auditoria", data=meta.read_bytes(), file_name=meta.name, mime="application/json")
        pacote = Path(res.get("pacote_zip", ""))
        if pacote.exists():
            st.download_button("Baixar pacote completo do municipio", data=pacote.read_bytes(), file_name=pacote.name, mime="application/zip")
    else:
        st.error("A consulta nao retornou um HTML FNDE validado.")
        st.json(res)
