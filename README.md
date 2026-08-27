# APPfndeDOWELEVER

Aplicativo separado para localizar e baixar evidencias/arquivos oficiais do FNDE sem modificar o app RREO existente.

## Primeira meta

Validar Araci/BA, ano 2025, usando a consulta legada de Liberacoes do FNDE.

## O que o app salva

- HTML bruto retornado pelo FNDE;
- JSON de metadados/auditoria;
- historico SQLite;
- opcionalmente copia para S3.

## Fonte principal

`FNDE_LIBERACOES_LEGADO`

Endpoints configurados com fallback:

- `https://www.fnde.gov.br/pls/edw_fnde/internet_fnde.liberacoes_result_pc`
- `https://www.fnde.gov.br/pls/simad/internet_fnde.liberacoes_result_pc`

O app nao tenta contornar CAPTCHA. A rota SIGEF nova fica apenas documentada como fallback manual.

## Executar localmente

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
streamlit run app.py
```

## Teste de linha de comando

```bash
python scripts/testar_araci.py
```

## Render

O projeto inclui `render.yaml`. Build: `pip install -r requirements.txt`.
Start: `streamlit run app.py --server.address 0.0.0.0 --server.port $PORT`.

## Observacao importante

Esta versao e propositalmente separada do RREO. Somente depois da validacao do modulo FNDE deve ser considerada a integracao em `APPrreufndeDOWELEVER`.
