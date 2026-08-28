from pathlib import Path
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
PASTA = ROOT / "downloads"
st.set_page_config(page_title="Arquivos FNDE", layout="wide")
st.title("Arquivos FNDE")
arquivos = sorted([p for p in PASTA.glob("*") if p.is_file()])
if not arquivos:
    st.info("Nenhum arquivo baixado ainda.")
for p in arquivos:
    c1, c2 = st.columns([4,1])
    c1.write(f"{p.name} — {p.stat().st_size:,} bytes")
    c2.download_button("Baixar", p.read_bytes(), file_name=p.name, key=str(p))
