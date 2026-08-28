# APPfndeDOWELEVER 0.6.0

Aplicativo independente para consultar liberações oficiais do FNDE, preservar evidências, consolidar os totais do município e produzir um PDF textual no padrão visual do documento de referência.

## Fluxo

FNDE -> HTML bruto -> identificação municipal -> extração -> JSON de auditoria -> validação -> HTML/CSS de impressão -> Chromium -> PDF textual -> pacote ZIP.

## Identificação

A identificação usa dois parâmetros complementares:

1. **externo**: nome do arquivo / IBGE / município / UF;
2. **interno**: conteúdo do documento para confirmação e auditoria.

A base `data/municipios_brasil.json` contém 5.570 municípios e é a referência para IBGE, nome, UF e código FNDE de seis dígitos.

Araci/BA: `2902104 -> 290210`.

## PDF

O motor principal é Playwright/Chromium, usando:

- `templates/fnde_sigef_print.html`
- `static/fnde_sigef_print.css`
- `referencias/FNDE_MODELO_OFICIAL_ARACI_2025.pdf`

Se Chromium não iniciar, existe fallback textual em ReportLab. O JSON de auditoria registra qual motor foi usado.

## Render

O `render.yaml` instala as dependências Python e o Chromium do Playwright no build. A versão do Python permanece livre, seguindo a configuração atual do projeto.

## Confiabilidade

Leia `docs/REGRAS_DE_CONFIABILIDADE.md`.

## Teste local repetido

```bash
python scripts/selfcheck_10x.py
```

O script executa dez ciclos de regressão verificando base municipal, identificação, parser, referência de Araci e geração/extração de texto do PDF.
