import streamlit as st
from database.db import listar

st.set_page_config(page_title="Historico", layout="wide")
st.title("Historico de downloads")
rows = listar(500)
if rows:
    st.dataframe(rows, use_container_width=True)
else:
    st.info("Nenhum download registrado ainda.")
