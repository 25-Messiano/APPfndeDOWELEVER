import json
from pathlib import Path
import streamlit as st

CFG = Path(__file__).resolve().parents[1] / "config" / "sistema.json"
st.set_page_config(page_title="Configuracoes", layout="wide")
st.title("Configuracoes")
st.code(CFG.read_text(encoding="utf-8"), language="json")
st.info("Para mudar armazenamento para S3, configure STORAGE_BACKEND=s3 e as variaveis AWS/S3 no Render.")
