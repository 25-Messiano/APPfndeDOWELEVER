import streamlit as st
from supervisao.supervisor import recent_reports
from supervisao.supervisor_auto import status

st.set_page_config(page_title="Supervisão FNDE", layout="wide")
st.title("Supervisão FNDE")
st.json(status())
st.caption("Histórico local de consultas, validação, extração, arquivos e geração de PDF. A presença da chave não comprova saldo nem uma chamada bem-sucedida.")
if st.button("Atualizar auditoria"):
    st.rerun()
for report in recent_reports(100):
    with st.expander(f"{report['operacao']} · {report['status']} · {report['id'][:8]}"):
        st.json(report)
