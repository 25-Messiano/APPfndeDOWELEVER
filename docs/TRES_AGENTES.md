# Equipe de supervisão por evidências

Três papéis explícitos usam a `OPENAI_API_KEY` já configurada e o modelo
`SUPERVISOR_OPENAI_MODEL`. Não requer três serviços Render, novas chaves ou SDK.
O transporte conserva Responses API, como a integração existente.

| Papel | Responsabilidade |
| --- | --- |
| Técnico | Organizar fontes e conferir a execução com origem demonstrável. |
| Auditor | Contraprova independente contra as mesmas fontes originais. |
| Coordenador | Julgar os pareceres e emitir veredito/nota técnica, sem inventar argumentos. |

Todos têm tarefas para BUSCAR, BAIXAR, PROCESSAR e ENTREGAR. Cada chamada do
decorador `supervised` faz uma rodada antes e outra depois. A fase ANTES julga
somente pré-condições; não certifica um resultado que ainda não existe. Erros
preservam a exceção original e sua auditoria. Cada rodada completa usa três
chamadas, com o mesmo saldo compartilhado. Não há votação por maioria.

## Controles

- Respostas estruturadas por JSON Schema, validadas também no servidor.
- Referências limitadas aos IDs realmente fornecidos. Não aceitar páginas ou
  arquivos inventados como prova. Uma referência de operação prova apenas o
  contrato/registro, não substitui leitura de documento.
- Auditor recebe as fontes originais e o parecer do Técnico. Coordenador recebe
  as mesmas fontes e os dois pareceres. Cada revisor recebe cópias isoladas.
- Bloqueio/pendência dos revisores ou do motor não pode ser superado pelo
  Coordenador. Correção proposta não significa correção aplicada.
- Propostas registram campo, antes/depois, regra e prova e ficam
  `PROPOSTA_NAO_APLICADA`. A implementação não dá ao modelo escrita livre nem
  altera automaticamente regras contábeis. Uma alteração exige execução pelo
  motor, nova conferência e registro dos valores efetivamente escritos.
- Células do relatório de gravação registram valor anterior e posterior; a
  linhagem aponta para provas disponíveis e operações de origem. Ausência de
  vínculo documental completo é uma limitação explícita, não aprovação presumida.
- PDFs recebem segunda leitura textual com página/linhas/hash; FNDE recebe
  referências de linhas HTML/pagamentos. Isto não é inspeção visual de imagens
  nem OCR certificado. PDF sem texto, fonte inconsistente ou contexto maior que
  o limite pausa a operação; nenhuma evidência é omitida para obter aprovação.
- Recepção TCM confere município e competência internos antes da persistência.
- Fórmulas, nomes/ordem das abas, VBA, estilos, tabelas e pivôs não são alterados
  pelos agentes. Não pintar células nem acrescentar abas de auditoria.
- A auditoria segue o mecanismo SQLite/GCS existente. Operações filhas possuem
  auditoria própria e referência no registro pai. Falha de persistência fica
  explícita; o histórico local não é anunciado como Cloud confirmado.

## Configuração e observação

`SUPERVISOR_AUTO_AI=true` habilita supervisão obrigatória. A equipe de três
papéis é habilitada por padrão (`SUPERVISOR_AGENT_TEAM=true`). Definir a segunda
como `false` volta ao supervisor único; o painel informa esse modo.

Falta de chave/saldo, limite, timeout ou resposta inválida pausa as etapas.
Falha da API recebe intervalo de proteção para evitar repetição de chamadas.
Pendência documental local não bloqueia a API global dos demais municípios.
O código não consulta nem promete conhecer antecipadamente o saldo da conta.

No BB: abrir **Supervisor BB / TCM / FNDE**. No FNDE: **Supervisão**.
Os painéis mostram funções, tarefas e auditorias e oferecem **Testar os três
agentes**, diagnóstico de três chamadas reais, sem baixar nem alterar planilhas.
No TCM, `GET /agent/supervisao/agentes` fornece definição e estado sem chamar a
API, sem criar tarefas e sem expor a chave. Configuração não prova chamada real.

Os testes automatizados usam respostas simuladas: verificam os contratos e
bloqueios, não comprovam disponibilidade/saldo da API em produção. Essa distinção
também vale para validação numérica determinística versus parecer real da IA.
