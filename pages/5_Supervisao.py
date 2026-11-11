import uuid
import streamlit as st
from supervisao.supervisor import recent_reports, SupervisorBlocked
from supervisao.supervisor_auto import status
from supervisao.supervisor_ai import advise, configured

st.set_page_config(page_title="Supervisão FNDE", layout="wide")
st.title("Supervisão FNDE")
st.json(status())
st.caption("Histórico local de consultas, validação, extração, arquivos e geração de PDF. A presença da chave não comprova saldo nem uma chamada bem-sucedida.")

st.subheader("Teste de conexão")
st.caption("Faz uma chamada real à API para conferir o acesso. Consome uma orientação; não inicia downloads nem altera planilhas.")
if st.button("Testar conexão com a IA", disabled=not configured()):
    st.session_state.pop("fnde_ia_test_result", None)
    evidence = {
        "id": uuid.uuid4().hex, "fonte": "FNDE",
        "operacao": "teste_conexao_ia", "status": "DIAGNOSTICO",
        "resumo": {"teste_de_conexao": True, "downloads_iniciados": False,
                   "planilhas_alteradas": False},
    }
    try:
        with st.spinner("Conferindo resposta da API..."):
            answer = advise(
                "Este é somente um teste de conexão da IA. Informe que recebeu o registro de diagnóstico, sem declarar downloads, processamento ou planilhas concluídos.",
                [evidence],
            )
        st.session_state["fnde_ia_test_result"] = answer
    except SupervisorBlocked as exc:
        st.error(str(exc))
    except Exception as exc:
        st.error(f"Não foi possível concluir o teste: {type(exc).__name__}.")
if st.session_state.get("fnde_ia_test_result"):
    st.success("Chamada real concluída. A API aceitou a chave e retornou uma resposta válida.")
    st.json(st.session_state["fnde_ia_test_result"])

if st.button("Atualizar auditoria"):
    st.rerun()
for report in recent_reports(100):
    with st.expander(f"{report['operacao']} · {report['status']} · {report['id'][:8]}"):
        st.json(report)
