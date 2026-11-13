"""Revisao consultiva obrigatoria por etapa; falha da API pausa o motor."""
from __future__ import annotations
import contextvars,os,time,threading
from datetime import datetime,timezone
from .supervisor import SupervisorAIPaused,SupervisorBlocked,redact
from . import supervisor_ai
_ACTIVE=contextvars.ContextVar('automatic_ai_review',default=False)
_PAUSE_LOCK=threading.RLock()
_PAUSE_STATE={'until':0.0,'reason':''}

def status():
    from .supervisor_agents import definition
    with _PAUSE_LOCK:
        paused=_PAUSE_STATE['until']>time.monotonic()
        return {'automatica':enabled(),'chave_configurada':supervisor_ai.configured(),'modo':'OBRIGATORIO_POR_ETAPA','api_em_pausa':paused,'motivo':_PAUSE_STATE['reason'] if paused else '', 'equipe': definition()}

def enabled():
    return os.getenv('SUPERVISOR_AUTO_AI','true').strip().lower() in {'1','true','yes','on'}

def review_stage(report,phase):
    if _ACTIVE.get():
        raise SupervisorAIPaused('PAUSADO_IA: chamada recursiva de supervisao bloqueada.')
    if not enabled():
        report.setdefault('orientacao_automatica',{})[phase]={'status':'DESATIVADA'}
        return
    entry={'status':'AGUARDANDO','fase':phase,'atualizado_em':datetime.now(timezone.utc).isoformat()}
    report.setdefault('orientacao_automatica',{})[phase]=entry
    if not supervisor_ai.configured():
        entry.update(status='PAUSADO_SEM_CHAVE',motivo='OPENAI_API_KEY nao configurada neste ambiente.')
        raise SupervisorAIPaused('PAUSADO_IA: OPENAI_API_KEY nao configurada; etapa nao liberada.')
    with _PAUSE_LOCK:
        if _PAUSE_STATE['until']>time.monotonic():
            entry.update(status='PAUSADO_API_INDISPONIVEL',motivo=_PAUSE_STATE['reason'])
            raise SupervisorAIPaused('PAUSADO_IA: '+_PAUSE_STATE['reason'])
    token=_ACTIVE.set(True)
    try:
        # Nunca enviar argumentos, PDFs, credenciais ou a propria orientacao anterior.
        context=redact({k:report.get(k) for k in ('id','fonte','operacao','identidade','status','resumo','erro')})
        context['fase_supervisao']=phase
        question=f'Revise a etapa {report.get("operacao")} do modulo {report.get("fonte")}, fase {phase}. Use so os registros; sinalize bloqueio se houver evidencia de inconsistencia. Antes da execucao nao declare sucesso. Nao altere dados nem proponha preencher lacunas com zero.'
        if phase == 'ANTES':
            question += ' Esta fase e PRE-EXECUCAO: avalie somente o contrato previo e as entradas informadas. O resultado final e as etapas filhas ainda nao existem. A ausencia de resultado posterior, por si so, nao e evidencia de erro; nao exija resultados de um processo ainda nao executado. Bloqueie quando houver inconsistencia concreta nas entradas, preservando todas as verificacoes.'
        if report.get('operacao') == 'conferir_parcelas_fundeb':
            question += ' A evidencia conferencia_fundeb contem as parcelas do TOTAL POR PARCELA / NATUREZA. Confira individualmente VAAF, VAAT e VAAR, nomenclatura completa, valor original e natureza C positiva/D negativa, inclusive ajustes e acertos de credito ou debito. Compare cada parcela com campo e coluna mensal e a contraprova diaria. Nao aprove apenas porque a soma final bate. Nao some novamente resumo e linhas diarias. Uma parcela normal de debito continua na coluna normal; um ajuste de credito continua na coluna de ajuste. Bloqueie divergencias e nomenclaturas pendentes; nao invente classificacao nem valores.'
        from .supervisor_agents import enabled as team_enabled, review_team
        answer = review_team(report, phase) if team_enabled() else supervisor_ai.advise(question,[context],automatic=True)
        entry.update(status='CONFERIDA',orientacao=answer,atualizado_em=datetime.now(timezone.utc).isoformat())
        if answer.get('prioridade')=='bloqueio':
            entry['status']='PAUSADO_POR_ORIENTACAO'
            raise SupervisorAIPaused('PAUSADO_IA: '+str(answer.get('resumo','Conferencia necessaria.')))
    except SupervisorAIPaused:
        raise
    except Exception as exc:
        reason=redact(str(exc));entry.update(status='PAUSADO_API_INDISPONIVEL',motivo=reason)
        if isinstance(exc, SupervisorBlocked) and reason.startswith(('COORDENADOR_', 'PROVA', 'EVIDENCIA_', 'PARECER_', 'ACHADO_', 'CORRECAO_', 'APROVACAO_')):
            entry['status'] = 'PAUSADO_POR_EVIDENCIA'
            raise SupervisorAIPaused('PAUSADO_IA: ' + reason) from None
        with _PAUSE_LOCK:
            _PAUSE_STATE.update(until=time.monotonic()+300,reason=reason)
        raise SupervisorAIPaused('PAUSADO_IA: '+reason) from None
    finally:
        _ACTIVE.reset(token)

