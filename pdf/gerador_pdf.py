import os
from pathlib import Path
from jinja2 import Template

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "fnde_sigef_print.html"
CSS = ROOT / "static" / "fnde_sigef_print.css"


def moeda_br(valor):
    return f"{float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def normalizar_programas(programas):
    out = []
    for p in programas or []:
        total = p.get("total", p.get("valor_total", 0)) or 0
        out.append({
            "programa": p.get("programa") or p.get("titulo") or p.get("categoria") or "Programa não identificado",
            "esfera": p.get("esfera") or "NÃO INFORMADA",
            "quantidade_entidades": p.get("quantidade_entidades", p.get("entidades", "-")),
            "valor_br": moeda_br(total),
            "total": float(total),
        })
    return out


def render_html(*, ibge, municipio, uf, ano, programas):
    tpl = Template(TEMPLATE.read_text(encoding="utf-8"))
    css = CSS.read_text(encoding="utf-8")
    return tpl.render(ibge=ibge, municipio=municipio, uf=uf, ano=ano, programas=normalizar_programas(programas), css=css)


def _playwright_pdf(html: str, destino: Path):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1240, "height": 1754})
        page.set_content(html, wait_until="load")
        page.emulate_media(media="print")
        page.pdf(path=str(destino), format="A4", print_background=True, prefer_css_page_size=True,
                 margin={"top":"0mm","right":"0mm","bottom":"0mm","left":"0mm"})
        browser.close()


def _reportlab_pdf(*, ibge, municipio, uf, ano, programas, destino: Path):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_LEFT
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
    from reportlab.lib import colors
    doc = SimpleDocTemplate(str(destino), pagesize=A4, rightMargin=34, leftMargin=34, topMargin=28, bottomMargin=30)
    styles = getSampleStyleSheet()
    small = ParagraphStyle('small', parent=styles['BodyText'], fontName='Helvetica', fontSize=8.5, leading=10, alignment=TA_LEFT)
    link = ParagraphStyle('link', parent=small, textColor=colors.HexColor('#0645ad'), underline=True, fontName='Helvetica-Bold')
    story = [Paragraph('FNDE', styles['Title']), Paragraph('Fundo Nacional de Desenvolvimento da Educação', small), Spacer(1, 6),
             Paragraph('Liberações', styles['Heading2']), Paragraph('Consultas Gerais', styles['Heading3']), Spacer(1, 6),
             Paragraph(f'<b>Município:</b> {municipio}/{uf} &nbsp;&nbsp; <b>IBGE:</b> {ibge} &nbsp;&nbsp; <b>Ano:</b> {ano}', small), Spacer(1, 8)]
    for item in normalizar_programas(programas):
        t = Table([
            [Paragraph(item['programa'], link), ''],
            ['Esfera', item['esfera']],
            ['Quantidade de Entidades', str(item['quantidade_entidades'])],
            ['Valor Total', 'R$ ' + item['valor_br']],
        ], colWidths=[180, 330])
        t.setStyle(TableStyle([
            ('SPAN',(0,0),(1,0)), ('LINEBELOW',(0,3),(1,3),0.5,colors.grey),
            ('FONTNAME',(0,1),(0,3),'Helvetica'), ('FONTSIZE',(0,0),(-1,-1),8.5),
            ('BOTTOMPADDING',(0,0),(-1,-1),4), ('TOPPADDING',(0,0),(-1,-1),3),
        ]))
        story.append(KeepTogether([t, Spacer(1, 4)]))
    doc.build(story)


def gerar_pdf(*, ibge, municipio, uf, ano, programas, destino):
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    html = render_html(ibge=ibge, municipio=municipio, uf=uf, ano=ano, programas=programas)
    engine = os.getenv("PDF_ENGINE", "playwright").lower()
    usado = "playwright"
    erro_playwright = None
    if engine == "playwright":
        try:
            _playwright_pdf(html, destino)
        except Exception as exc:
            erro_playwright = repr(exc)
            usado = "reportlab_fallback"
            _reportlab_pdf(ibge=ibge, municipio=municipio, uf=uf, ano=ano, programas=programas, destino=destino)
    else:
        usado = "reportlab"
        _reportlab_pdf(ibge=ibge, municipio=municipio, uf=uf, ano=ano, programas=programas, destino=destino)
    return {"arquivo": str(destino), "engine": usado, "erro_playwright": erro_playwright, "html": html}


def validar_pdf_textual(caminho: str, termos=None):
    from pypdf import PdfReader
    reader = PdfReader(caminho)
    texto = "\n".join((p.extract_text() or "") for p in reader.pages)
    termos = termos or []
    faltantes = [t for t in termos if t not in texto]
    return {"ok": len(reader.pages) >= 1 and bool(texto.strip()) and not faltantes, "paginas": len(reader.pages), "caracteres": len(texto), "faltantes": faltantes, "texto": texto}
