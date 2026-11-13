"""Provas documentais e origem de células, separadas da aparência do Excel."""
from __future__ import annotations
import hashlib
import io
import json
import re
import unicodedata
from .supervisor import _CURRENT, SupervisorBlocked, redact


def add_proof(*, documento, sha256, local, trecho, campo=None, valor=None, tipo='DOCUMENTAL'):
    import os
    from .supervisor_agents import enabled
    report = _CURRENT.get()
    if (report is None or not enabled() or
            os.getenv('SUPERVISOR_AUTO_AI', 'true').strip().lower() not in {'1', 'true', 'yes', 'on'}):
        return None
    if not re.fullmatch(r'[a-f0-9]{64}', str(sha256)):
        raise SupervisorBlocked('PROVA_SEM_HASH: documento precisa de SHA-256 válido.')
    if len(str(trecho)) > 1200:
        raise SupervisorBlocked('PROVA_EXCEDE_LIMITE: dividir o trecho sem omitir evidência.')
    proof = {'tipo': tipo, 'documento': str(documento), 'sha256': str(sha256),
             'local': str(local), 'trecho': str(trecho)}
    if campo is not None: proof['campo'] = str(campo)
    if valor is not None: proof['valor'] = valor
    safe = redact(proof)
    # Never silently store a truncated or non-finite source value.
    if any(isinstance(v, str) and safe.get(k) != v for k, v in proof.items()):
        raise SupervisorBlocked('PROVA_NAO_PUBLICAVEL: conteúdo sensível ou campo excede limite.')
    safe['id'] = 'doc-' + hashlib.sha256(json.dumps(safe, sort_keys=True, ensure_ascii=False,
                                                allow_nan=False).encode()).hexdigest()[:24]
    proofs = report.setdefault('provas', [])
    if not any(p['id'] == safe['id'] for p in proofs):
        if len(proofs) >= 180:
            raise SupervisorBlocked('PROVAS_EXCEDEM_LIMITE: dividir a operação; não aprovar com fontes omitidas.')
        proofs.append(safe)
    return safe['id']


def register_pdf(pdf_bytes, name='documento.pdf'):
    """Segunda leitura textual, com página e linhas, para os revisores independentes."""
    import os
    from .supervisor_agents import enabled
    if (_CURRENT.get() is None or not enabled() or
            os.getenv('SUPERVISOR_AUTO_AI', 'true').strip().lower() not in {'1', 'true', 'yes', 'on'}):
        return []
    from pypdf import PdfReader
    sha = hashlib.sha256(pdf_bytes).hexdigest()
    refs = []
    for page_no, page in enumerate(PdfReader(io.BytesIO(pdf_bytes)).pages, 1):
        lines = (page.extract_text() or '').splitlines()
        if not any(x.strip() for x in lines):
            raise SupervisorBlocked('PDF_SEM_TEXTO: leitura documental exige OCR conferido.')
        buffer = []; first = 1
        for line_no, line in enumerate(lines, 1):
            if len(line) > 1200:
                raise SupervisorBlocked('LINHA_PDF_EXCEDE_LIMITE: dividir fonte antes da revisão.')
            if len('\n'.join(buffer + [line])) > 1100:
                refs.append(add_proof(documento=name, sha256=sha,
                    local=f'página {page_no}, linhas {first}-{line_no-1}', trecho='\n'.join(buffer)))
                buffer = []; first = line_no
            buffer.append(line)
        if buffer:
            refs.append(add_proof(documento=name, sha256=sha,
                local=f'página {page_no}, linhas {first}-{len(lines)}', trecho='\n'.join(buffer)))
    return refs


def register_html(html, name='FNDE.html'):
    import os
    from .supervisor_agents import enabled
    if (_CURRENT.get() is None or not enabled() or
            os.getenv('SUPERVISOR_AUTO_AI', 'true').strip().lower() not in {'1', 'true', 'yes', 'on'}):
        return []
    from bs4 import BeautifulSoup
    raw = html.encode('utf-8') if isinstance(html, str) else html
    sha = hashlib.sha256(raw).hexdigest()
    soup = BeautifulSoup(raw, 'html.parser')
    for tag in soup(['script', 'style']): tag.decompose()
    refs = []
    for index, row in enumerate(soup.find_all('tr'), 1):
        text = row.get_text(' | ', strip=True)
        if text:
            refs.append(add_proof(documento=name, sha256=sha, local=f'linha HTML {index}', trecho=text))
    if not refs:
        text = soup.get_text(' ', strip=True)
        for index in range(0, len(text), 1100):
            refs.append(add_proof(documento=name, sha256=sha,
                local=f'texto HTML, caracteres {index+1}-{min(index+1100,len(text))}', trecho=text[index:index+1100]))
    return refs


def validate_pdf_identity(pdf_bytes, *, municipio, competencia):
    """Confrontar cabeçalho interno; data de emissão não substitui competência."""
    from pypdf import PdfReader
    def norm(text):
        return ' '.join(unicodedata.normalize('NFKD', str(text)).encode('ascii', 'ignore').decode().upper().split())
    text = norm('\n'.join(page.extract_text() or '' for page in PdfReader(io.BytesIO(pdf_bytes)).pages))
    found = set(re.findall(r'COMPETENCIA\s*:?\s*((?:0[1-9]|1[0-2])/\d{4})', text))
    expected = str(competencia).replace('-', '/')
    if not found or found != {expected}:
        raise SupervisorBlocked(f'COMPETENCIA_INTERNA_DIVERGENTE: esperado {expected}; cabeçalho {sorted(found)}.')
    if not municipio or norm(municipio) not in text:
        raise SupervisorBlocked('MUNICIPIO_INTERNO_DIVERGENTE: município não comprovado no PDF.')
    return {'municipio': str(municipio), 'competencia': expected, 'sha256': hashlib.sha256(pdf_bytes).hexdigest()}


def attach_cell_lineage(report):
    """Guardar destino, antes/depois e dependências que o motor efetivamente informou."""
    current = _CURRENT.get()
    if current is None or not isinstance(report, dict):
        return
    cells = []
    for row in report.get('linhas', []):
        for cell in row.get('celulas', []):
            cells.append({'competencia': row.get('competencia'), 'linha': row.get('linha'),
                          **{k: cell[k] for k in ('celula', 'campo', 'valor', 'valor_anterior', 'anterior', 'novo', 'formula') if k in cell}})
    current['linhagem_celulas'] = {
        'fonte': report.get('fonte'), 'celulas': cells,
        'registros_origem': [p['id'] for p in current.get('provas', [])],
        'operacoes_origem': current.get('operacoes_origem', []),
        'limite': 'Vínculo documental apenas quando o motor forneceu prova; fórmulas preservadas.',
        'agentes': 'Ver pareceres da equipe nesta operação; não presumir aprovação antes da rodada DEPOIS.',
    }
