# Arquitetura

<!-- specsfy:documentator:start -->
Os diagramas são exemplos de formato. Eles não representam relações confirmadas da aplicação.

## Componentes

| Tipo | Quantidade |
| --- | --- |
| Código | 23 |
| Testes | 12 |

## Diagramas

```mermaid
flowchart TD
  Application[Aplicação]
```

```mermaid
classDiagram
  class Application
```
<!-- specsfy:documentator:end -->

## Módulos (escrito à mão)

| Arquivo | Responsabilidade |
| --- | --- |
| `bin/secretario` → `src/cli.py` | Subcomandos; orquestra a faxina por conta (falha de uma conta não para as outras) |
| `src/contas.py` | Lê contas do Himalaya; presets por provedor (porta, ssl/starttls); cadastro testando IMAP e SMTP |
| `src/imap.py` | Conexão, novos por UID, rótulo (`X-GM-LABELS` no Gmail, pasta no IMAP genérico), arquivar, lido, lixeira por atributo `\Trash` |
| `src/classificar.py` | Regras → proteções embutidas → palavras/cabeçalhos → IA em lote (máx. 20 chamadas de 100), saída fechada |
| `src/descadastro.py` | Só One-Click (RFC 8058) ou `mailto:` |
| `src/resumo.py` | Texto do resumo, do ensaio e do plano das segundas |
| `src/estado.py` | SQLite, migrations e retenção |
| `src/instalar.py` | Script, skill e cron no Hermes |

```mermaid
flowchart LR
  cron[Cron Hermes 07:30] --> sh[secretario.sh] --> cli[src/cli.py]
  cli --> contas[src/contas.py] --> him[(config Himalaya)]
  cli --> imap[src/imap.py] --> prov[(IMAP Gmail/Titan/genérico)]
  cli --> cl[src/classificar.py] --> ia[hermes -z]
  cli --> desc[src/descadastro.py] --> web[(One-Click HTTPS / SMTP)]
  cli --> est[src/estado.py] --> db[(secretario.db)]
  cli --> res[src/resumo.py] --> tg[stdout → Telegram]
```
