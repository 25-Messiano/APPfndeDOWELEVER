from pathlib import Path
import streamlit as st

from core.downloader import baixar_fnde

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
    cnpj = st.text_input("CNPJ (opcional)", value="14.232.086/0001-92")

st.caption("O primeiro teste vem preenchido para Araci/BA 2025. O CNPJ pode ser removido para testar a descoberta por municipio.")

if st.button("Baixar arquivo FNDE", type="primary"):
    with st.spinner("Consultando FNDE..."):
        res = baixar_fnde(ibge.strip(), municipio.strip(), uf.strip(), int(ano), cnpj.strip())
    if res.get("ok"):
        st.success("Arquivo oficial salvo com sucesso.")
        st.write("Endpoint:", res.get("endpoint"))
        st.write("HTTP:", res.get("http_status"))
        st.write("Arquivo:", res.get("arquivo"))
        st.write("Metadados:", res.get("metadados"))
        st.json(res.get("validacao", {}))
        achados = res.get("cnpjs_encontrados", [])
        if achados:
            st.subheader("CNPJs encontrados no HTML")
            st.dataframe(achados, use_container_width=True)
        caminho = Path(res["arquivo"])
        if caminho.exists():
            st.download_button("Baixar HTML para o computador", data=caminho.read_bytes(), file_name=caminho.name, mime="text/html")
    else:
        st.error("A consulta nao retornou um HTML FNDE validado.")
        st.json(res)
