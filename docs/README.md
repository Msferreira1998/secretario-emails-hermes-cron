# Documentação técnica

<!-- specsfy:documentator:start -->
## Visão geral

- Frameworks detectados: não identificados.
- Arquivos de código: 23.
- Arquivos de teste: 12.

## Roteiro

- [Arquitetura](architecture.md)
- [Aplicação](application.md)
- [Banco de dados](database.md)
- [Testes](testing.md)
- [Pacotes](packages.md)
<!-- specsfy:documentator:end -->

## Secretário de e-mails (escrito à mão: o gerador não reconhece Python)

Faxina diária às 07:30 BRT das contas do Himalaya, com resumo no Telegram pelo Hermes.

| Quero… | Onde |
| --- | --- |
| Entender os módulos | [architecture.md](architecture.md) |
| Ver o banco | [database.md](database.md) |
| Ver o fluxo da faxina | [flows.md](flows.md) |
| Rodar os testes | [testing.md](testing.md) |

### Operação

- Faxina manual: `bin/secretario faxina` (a primeira execução de todas é ensaio e não altera nada).
- Comandos do Telegram (pela skill `secretario-emails` do Hermes): `protege`, `desprotege`, `veta` ("não descadastra"), `libera`, `papel`, `regra`, `limpeza <conta> <dias|desliga>`, `limpa <remetente|domínio> <dias|desliga>`, `vip`/`desvip`, `busca <texto>`, `desfaz`, `responder`, `envia`.
- Conta nova: preencher `~/.config/secretario-emails/contas.toml` (600) e rodar `bin/secretario conta adicionar <nome>`.
- Instalação no Hermes: `bin/secretario instalar` (idempotente; cria o cron "Secretário de e-mails", remove a "Triagem de e-mails" e tira o himalaya da "Revisão semanal").
