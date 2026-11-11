import json
from pathlib import Path
import streamlit as st
from supervisao.supervisor_auto import status as supervisor_status

CFG = Path(__file__).resolve().parents[1] / "config" / "sistema.json"
st.set_page_config(page_title="Configuracoes", layout="wide")
st.title("Configuracoes")
st.subheader("Supervisão por IA")
st.json(supervisor_status())
st.code(CFG.read_text(encoding="utf-8"), language="json")
st.info("Para mudar armazenamento para S3, configure STORAGE_BACKEND=s3 e as variaveis AWS/S3 no Render.")

