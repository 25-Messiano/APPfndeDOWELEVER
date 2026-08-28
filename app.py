import json
from pathlib import Path
import streamlit as st

ROOT = Path(__file__).resolve().parent
CFG = json.loads((ROOT / "config" / "sistema.json").read_text(encoding="utf-8"))

st.set_page_config(page_title="APPfndeDOWELEVER", page_icon="⬇️", layout="wide")
st.title("APPfndeDOWELEVER")
st.caption(f"Versão {CFG.get('version')} - Download, auditoria e PDF textual FNDE")
st.success("Sistema online. Use Painel no menu lateral para selecionar UF e Município.")
st.markdown("**Fluxo:** FNDE → HTML bruto → validação → JSON de auditoria → PDF textual → pacote completo.")
