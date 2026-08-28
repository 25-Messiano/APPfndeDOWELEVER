# DOCUMENTO MESTRE — APPfndeDOWELEVER

**Versão de referência:** 0.6.1  
**Finalidade:** reunir em um único documento as regras de confiabilidade, arquitetura, parâmetros de identificação, geração de PDF textual, configuração do Render, auditoria e testes do APPfndeDOWELEVER.

---

## 1. PRINCÍPIO GERAL

O APPfndeDOWELEVER deve baixar dados oficiais do FNDE, identificar corretamente o município, preservar a evidência original, estruturar os dados, validar os resultados e gerar um PDF textual analítico no padrão visual de referência do SIGEF/FNDE.

Fluxo principal:

**FNDE → HTML bruto → identificação → extração → normalização → JSON estruturado → validação → template HTML/CSS → Chromium/Playwright → PDF textual → validação do PDF → armazenamento/auditoria**

---

## 2. IDENTIFICAÇÃO DO MUNICÍPIO

O sistema deve usar dois parâmetros complementares:

1. **Parâmetro externo:** nome do arquivo.
2. **Parâmetro interno:** conteúdo do HTML/PDF.

A base `data/municipios_brasil.json` é a referência oficial para:

- código IBGE de 7 dígitos;
- município;
- UF;
- código FNDE de 6 dígitos.

Regra:

- o nome externo orienta a identificação e o roteamento inicial;
- o conteúdo interno confirma e valida;
- pequenas diferenças de grafia não devem bloquear o processamento;
- divergências reais devem ser registradas em log;
- nenhum arquivo deve ser descartado silenciosamente por divergência simples.

Exemplo:

`FNDE_2025_2902104_ARACI_BA.pdf`

deve resultar em:

- Ano: 2025
- IBGE: 2902104
- Município: Araci
- UF: BA
- Código FNDE: 290210

---

## 3. PDF DE REFERÊNCIA

O PDF oficial/modelo colocado no repositório deve ser tratado como **MODELO-MESTRE VISUAL**.

Ele serve para parametrizar:

- posição e ordem dos títulos;
- fontes;
- margens;
- tabelas;
- espaçamento;
- cores;
- quebras de página;
- cabeçalho;
- rodapé;
- paginação;
- aparência geral.

O PDF gerado pelo app deve ser **texto nativo**, pesquisável e selecionável.

Não usar clone em imagem como saída principal.

---

## 4. TECNOLOGIAS PRINCIPAIS

Usar o máximo de recursos úteis sem tornar o projeto pesado:

- `requests` ou `httpx`: download e consulta;
- `BeautifulSoup` / `lxml`: leitura do HTML;
- `pandas`: organização e consolidação;
- `json`: estrutura intermediária;
- `sqlite`: checkpoint e auditoria;
- `rapidfuzz` / `difflib`: tolerância de nomes;
- `jinja2`: template HTML;
- `HTML/CSS`: layout de impressão;
- `Playwright + Chromium`: gerador principal de PDF;
- `ReportLab` ou equivalente: fallback;
- `pypdf` / `PyMuPDF`: validação do PDF;
- `hashlib SHA-256`: integridade e deduplicação.

---

## 5. CAMADAS DE CONFIABILIDADE

O sistema deve possuir:

- validação dupla da identidade;
- comparação com a base de municípios;
- validação por programa;
- soma e comparação de totais;
- retry automático;
- espera progressiva em falhas de rede;
- checkpoint persistente;
- deduplicação por hash;
- cache;
- logs legíveis;
- auditoria estruturada;
- releitura direcionada em divergências;
- separação entre dado oficial e apresentação;
- teste de integridade após geração do PDF;
- modo diagnóstico;
- manifesto por execução.

Status permitidos:

- `VALIDADO`
- `DIVERGENTE`
- `PENDENTE_CONFERENCIA`
- `NAO_ENCONTRADO`
- `ERRO_FONTE`

---

## 6. REGRA DE GRAVAÇÃO

O dado só deve ser considerado oficial quando validado.

Divergências não devem contaminar a base principal.

Fluxo:

**extração inicial → verificação → comparação → releitura direcionada → validação ou PENDENTE_CONFERENCIA**

---

## 7. ARQUIVOS GERADOS POR MUNICÍPIO

O ideal é gerar:

- `original.html`
- `dados_brutos.json`
- `dados_validados.json`
- `auditoria.json`
- `manifest.json`
- `FNDE_ANO_IBGE_MUNICIPIO_UF.pdf`
- pacote `.zip` de diagnóstico/auditoria quando necessário.

---

## 8. VALIDAÇÃO DO PDF

Após gerar o PDF textual, o sistema deve abrir novamente o documento e confirmar:

- PDF válido;
- texto extraível;
- município presente;
- UF presente;
- ano presente;
- programas esperados presentes;
- valores esperados presentes;
- quantidade de páginas coerente;
- ausência de página vazia inesperada.

---

## 9. RENDER

Configuração recomendada:

```yaml
services:
  - type: web
    name: appfndedowelever
    runtime: python
    plan: starter
    buildCommand: pip install -r requirements.txt && python -m playwright install chromium
    startCommand: streamlit run app.py --server.address 0.0.0.0 --server.port $PORT
    envVars:
      - key: STORAGE_BACKEND
        value: local
      - key: FNDE_TIMEOUT
        value: 60
```

O projeto deve evitar fixar uma versão desnecessária do Python, salvo necessidade técnica comprovada.

---

## 10. TESTES DE REGRESSÃO

O projeto deve manter testes automáticos repetíveis.

Municípios-padrão devem ser usados para verificar:

- identificação;
- consulta;
- parsing;
- consolidação;
- geração do PDF;
- leitura do PDF;
- validação final.

Araci/BA deve permanecer como caso de referência:

- IBGE: `2902104`
- Código FNDE: `290210`

---

## 11. REGRA DE NÃO SOBRESCRITA SILENCIOSA

Se um arquivo já existir e o conteúdo novo for diferente:

- comparar hash;
- registrar alteração;
- preservar histórico ou versão anterior;
- nunca substituir silenciosamente um arquivo divergente.

---

## 12. REGRA DE DESEMPENHO

O sistema deve ser eficiente sem exagerar nas dependências:

- usar paralelismo controlado;
- evitar OCR quando o conteúdo textual estiver disponível;
- não baixar novamente arquivos já validados;
- usar cache;
- limitar retries;
- priorizar processamento direcionado em vez de repetir o município inteiro.

---

## 13. DOCUMENTAÇÃO ORIGINAL CONSOLIDADA

### 13.1 Regras de Confiabilidade

# APPfndeDOWELEVER - Regras de Confiabilidade

Versão do protocolo: 1.0 - compatível com APPfndeDOWELEVER 0.6.0

## Objetivo

Garantir que um erro de identificação, download, extração, consolidação ou geração do PDF nunca seja tratado silenciosamente como dado validado.

## Fluxo oficial

Fonte FNDE -> HTML bruto -> identificação -> extração -> normalização -> JSON de auditoria -> validação -> template HTML/CSS -> Chromium -> PDF textual -> validação do PDF -> armazenamento.

## Regras obrigatórias

1. **Nome externo é o parâmetro primário de roteamento.** O padrão recomendado é `FNDE_ANO_IBGE_MUNICIPIO_UF.pdf`.
2. **Conteúdo interno é parâmetro de confirmação e fallback.** Diferenças leves de acento, hífen, caixa ou grafia não interrompem o processamento.
3. **Base municipal oficial interna.** `data/municipios_brasil.json` é usada para conferir IBGE, município, UF e derivar o código FNDE de seis dígitos.
4. **Divergência não é descarte.** Conflitos relevantes viram `DIVERGENCIA_IDENTIFICACAO` e seguem para auditoria.
5. **Resumo municipal é autoridade para totais.** Detalhes por entidade são trilha de auditoria e não devem ser somados cegamente quando programas se sobrepõem.
6. **HTML bruto sempre preservado.** Nunca substituir a evidência original pelo PDF recriado.
7. **PDF é apresentação, não fonte primária.** O PDF textual é gerado somente depois de os dados estruturados estarem consolidados.
8. **PDF deve ser textual.** Após a geração, o próprio sistema abre o PDF e confirma que município, IBGE e valores são extraíveis.
9. **Hash SHA-256.** Arquivos oficiais e produtos derivados devem ter hash registrado no JSON de auditoria.
10. **Estados de validação.** Usar `VALIDADO`, `DIVERGENTE`, `PENDENTE_CONFERENCIA`, `NAO_ENCONTRADO` e `ERRO_FONTE`.
11. **Retries controlados.** Falhas transitórias de rede devem ser repetidas com espera progressiva, sem bombardear o FNDE.
12. **Limite de entidades.** `FNDE_MAX_ENTIDADES` protege a aplicação contra loops ou páginas malformadas.
13. **Sem sobrescrita silenciosa.** Se um produto já existir com hash diferente, registrar a alteração.
14. **Template versionado.** Toda auditoria deve registrar a versão do template e do parser usados.
15. **Teste de regressão.** Araci/BA 2025 é município-padrão e deve permanecer compatível com os valores do PDF de referência.

## Valores de referência - Araci/BA 2025

- PNAE: R$ 2.366.078,00
- PDDE: R$ 616.100,00
- QSE: R$ 9.368.968,61
- Novas Turmas: R$ 370.608,62
- PNATE: R$ 911.562,38
- PDDE Qualidade: R$ 273.042,00
- PDDE Estrutura: R$ 422.850,00

Identificação correta: `2902104 | Araci | BA | código FNDE 290210`.

## Regra de gravação oficial

Somente registros `VALIDADO` podem alimentar a planilha/base oficial. Registros divergentes permanecem isolados em auditoria até conferência.


---

### 13.2 Análise do Código e Render

# Análise do código e Render - 27/08/2026

## Situação encontrada no ZIP recebido

1. O `render.yaml` estava funcional para Streamlit e os logs confirmavam `Build successful` e `Your service is live`.
2. O build anterior não instalava Chromium/Playwright; portanto não havia suporte completo ao PDF textual baseado em HTML/CSS.
3. `config/sistema.json` ainda mostrava versão `0.1.0`.
4. `pages/1_Painel.py` usava `2902708` como IBGE padrão para Araci. O correto é `2902104`.
5. `validar_referencia_araci()` também verificava `2902708`; isso impedia a validação correta de Araci.
6. O script `scripts/testar_araci.py` repetia o IBGE incorreto.
7. A base nacional `municipios_brasil.json` não estava integrada ao ZIP recebido.
8. O sistema já possuía pontos fortes importantes: fallback de endpoint FNDE, preservação do HTML, JSON de auditoria, SQLite, ZIP completo e percurso de entidades.

## Alterações aplicadas na versão 0.6.0

- Base nacional de 5.570 municípios integrada.
- Seleção `UF -> Município` na interface; IBGE e código FNDE são preenchidos automaticamente.
- Identificação externa e interna com tolerância de grafia e registro de divergências.
- Araci corrigido para `2902104`, código FNDE `290210`.
- Retry HTTP com backoff para 429/500/502/503/504.
- Gerador de PDF textual com HTML/CSS + Playwright/Chromium.
- Fallback em ReportLab caso Chromium não esteja disponível.
- Validação pós-geração com `pypdf` para garantir texto extraível.
- SHA-256 do HTML e PDF registrado na auditoria.
- Estados `VALIDADO` e `PENDENTE_CONFERENCIA` aplicados no fluxo principal.
- Modelo oficial do PDF e organograma preservados no repositório.
- `render.yaml` passou a instalar Chromium durante o build.

## Observação sobre o Render

Os logs fornecidos mostram uma instância com `WEB_CONCURRENCY=1`. Para este app isso é aceitável porque Streamlit é a interface e o trabalho é majoritariamente I/O. A parte mais pesada será a renderização Chromium, executada somente quando o PDF for gerado.

O Python foi deixado sem pinagem, preservando a decisão atual. O build observado estava usando Python 3.14; as dependências da versão 0.6.0 foram escolhidas com faixas amplas para reduzir conflitos.

## Testes

O script `scripts/selfcheck_10x.py` foi executado 10 vezes consecutivas. Cada ciclo validou:

- 5.570 municípios carregados;
- Araci/BA e IBGE correto;
- código FNDE de seis dígitos;
- reconhecimento do nome externo;
- conversão monetária;
- classificação PNAE;
- valores de referência de Araci;
- validação de HTML;
- extração do total PNAE em HTML sintético;
- geração de PDF textual e reextração de município, IBGE e valores.

Resultado local: `10/10 CICLOS OK`.

O teste de Playwright no ambiente de montagem não encontrou o binário Chromium, como esperado porque o browser não estava instalado nesse ambiente. O fallback ReportLab funcionou. No Render, a versão 0.6.0 corrige isso incluindo `python -m playwright install chromium` no `buildCommand`.


---

## 14. REGRA FINAL

O APPfndeDOWELEVER deve funcionar como um pipeline auditável de documentos oficiais:

**fonte oficial preservada + dados estruturados + validação + PDF textual fiel + auditoria completa**

O PDF final é a apresentação humana.  
A evidência original e o JSON validado são a base técnica da confiabilidade.
