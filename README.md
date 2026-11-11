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

# Supervisão automática por IA

A integração chama o mesmo supervisor usado no BB/TCM antes e depois das etapas
de consulta, validação HTML/PDF, extração de totais, armazenamento e geração de PDF.
Se a IA bloquear uma etapa, não responder ou ficar sem crédito, a operação lança
`SupervisorAIPaused`. A pausa não é convertida em erro comum de download nem libera
as etapas seguintes. A conferência usa metadados saneados e resumos estruturados;
ela não implica leitura integral dos documentos por IA.

O serviço usa sua própria variável `OPENAI_API_KEY` no Render. A chave nunca deve
entrar no repositório. `SUPERVISOR_AUTO_AI` é `true` por padrão; a ausência da chave
pausa a operação antes do download. O modelo existente é mantido via
`SUPERVISOR_OPENAI_MODEL`. `SUPERVISOR_AUTO_AI_DAILY_LIMIT` permite limitar chamadas
automáticas; `0` segue os limites e créditos da API.

A página **Supervisão** mostra o histórico local e a página **Configurações**
mostra somente presença da chave e estado da integração. O histórico local usa
SQLite; para replicar auditoria no GCS configure `SUPERVISOR_GCS_BUCKET` e o acesso
GCS existente. Falhas de persistência aparecem na auditoria.

Não existe fila retomável de downloads neste serviço legado. Depois de uma pausa,
consulte a auditoria e os arquivos já gerados antes de tentar novamente. A fila
retomável e as planilhas mensais/anuais pertencem ao aplicativo principal.

O pacote `supervisao/` contém a mesma implementação do supervisor preparada no
repositório `APPbbDOWELEVER`; mantenha os três módulos sincronizados ao atualizar.
Os testes offline exercitam bloqueios, erros de quota, chamadas aninhadas e o laço
real de consultas FNDE sem consumir API.

