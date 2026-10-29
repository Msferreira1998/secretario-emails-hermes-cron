# Banco de dados

<!-- specsfy:documentator:start -->
Os diagramas são exemplos de formato. Eles não representam relações confirmadas da aplicação.

## Fontes de persistência

| Arquivo |
| --- |
| migrations/001_inicial.sql |
| migrations/002_limpeza.sql |
| migrations/003_limpa_remetentes.sql |
| migrations/004_extras.sql |
| Nenhuma estrutura confirmada além das fontes listadas. |

```mermaid
erDiagram
  ENTITY { string id }
```
<!-- specsfy:documentator:end -->

## Diagrama (escrito à mão)

Detalhes e retenção em `.specsfy/DATABASE.md`.

```mermaid
erDiagram
  contas ||--o{ historico : registra
  contas ||--o{ vistos : conta
  contas ||--o{ pendentes : guarda
  pendentes ||--o{ rascunhos : origina
  contas { text nome PK  text papel  int ultimo_uid  int limpeza_dias  int alerta_uid }
  historico { int id PK  text quando  text conta  text remetente  text acao  text motivo }
  vistos { text conta PK  int uid PK  text remetente  text quando  int lido }
  pendentes { int id PK  text conta  text msgid  text remetente  text assunto }
  rascunhos { int id PK  text conta  text msgid  text para  text texto  text criado_em }
  regras { text remetente PK  text tipo }
  protegidos { text remetente PK }
  vetos { text remetente PK }
  execucoes { int id PK  text dia  int ensaio }
  limpa_remetentes { text remetente PK  int dias }
  contas ||--o{ vencimentos : avisa
  contas ||--o{ lixeira : apagou
  contas ||--o{ classificados : classificou
  contas ||--o{ pedidos : acompanha
  vencimentos { text conta PK  text msgid PK  text assunto  text vence }
  lixeira { text conta  text msgid  text remetente  text quando }
  restaurados { text msgid PK  text quando }
  vips { text remetente PK }
  classificados { text conta PK  text msgid PK  text remetente  text tipo }
  pedidos { text conta PK  text chave PK  text loja  text assunto  text quando }
```
