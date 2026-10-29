# Secretário de e-mails para o Hermes

Um faxineiro diário de caixa de entrada. Roda como cron do Hermes, rotula tudo com
`Secretário/<categoria>`, tira da caixa de entrada o que já está rotulado e manda um resumo
no Telegram. Também avisa, a cada 15 minutos, quando chega e-mail de segurança ou de alguém
que você marcou como VIP.

Python puro da biblioteca padrão. Nenhuma dependência para instalar.

## O que ele faz

| Comando | Para que serve |
| --- | --- |
| `faxina` | a rodada diária: classifica, rotula, tira da caixa, limpa o que venceu, manda o resumo |
| `alerta` | novidades da caixa desde a última checagem; só fala quando é segurança ou VIP |
| `busca <texto>` | procura nas duas contas, sem mexer em nada |
| `desfaz` | devolve à caixa de entrada o que a última faxina mandou para a lixeira |
| `limpa <remetente> <dias\|desliga>` | regra de lixeira por remetente |
| `vip <remetente>` / `desvip` | quem dispara o alerta de 15 minutos |
| `protege <remetente>` | nunca mexer nos e-mails desse remetente |
| `instalar` | cria os dois crons no Hermes e instala a skill (idempotente) |

## Antes de instalar

1. **Hermes funcionando**, com o Telegram pareado.
2. **Uma senha de aplicativo por conta de e-mail.** No Gmail: Conta Google → Segurança →
   Verificação em duas etapas → Senhas de app. A senha normal não serve.
3. **Python 3.11 ou mais novo** (usa `tomllib`).

## Instalação

```bash
git clone <onde-você-recebeu> ~/secretario-emails
cd ~/secretario-emails
python3 -m unittest discover tests     # 78 testes, tudo deve passar antes de configurar
```

### Cadastrar as contas

Crie o arquivo de credenciais, **com permissão 600**, uma seção por conta:

```bash
mkdir -p ~/.config/secretario-emails
cat > ~/.config/secretario-emails/contas.toml <<'FIM'
[trabalho]
provedor = "gmail"
email = "voce@gmail.com"
senha = "a-senha-de-app-de-16-letras"

[pessoal]
provedor = "gmail"
email = "outra@gmail.com"
senha = "a-outra-senha-de-app"
FIM
chmod 600 ~/.config/secretario-emails/contas.toml
```

O nome da seção (`trabalho`, `pessoal`) é como você vai se referir à conta. Pode ser um só,
ou mais de dois. Provedores com preset: `gmail`, `outlook`, `hotmail`. Outro provedor exige
`imap_servidor`, `smtp_servidor` e as portas.

Depois, para cada conta:

```bash
bin/secretario conta adicionar trabalho
```

Ele testa o login por IMAP e SMTP e **só grava se entrar**. A senha não aparece em log nem
no resumo.

### Primeira rodada

```bash
bin/secretario faxina
```

**A primeira rodada é ensaio automático**: ela mostra o que faria e não altera nada. Não existe
opção `--ensaio` — é o próprio programa que sabe que é a primeira vez. Leia o resumo com calma;
é a sua única chance de ver o estrago antes dele acontecer.

A **segunda** chamada é real. Depois dela:

```bash
bin/secretario instalar      # cria os crons: faxina 07:30 e alerta a cada 15 min
```

`faxina` não aceita argumento nenhum: se você passar qualquer coisa, ele recusa em vez de rodar.
Isso existe porque `faxina` mexe na caixa de entrada de verdade, e um argumento digitado errado
não deve virar uma rodada real por acidente.

## O que esperar na primeira faxina real

A primeira rodada real mexe em caixa de entrada antiga e pode ser grande. Três defesas:

- O ensaio automático da primeira chamada mostra o tamanho antes.
- `desfaz` devolve à caixa de entrada tudo o que a última faxina mandou para a lixeira, e
  marca esses remetentes para não repetir.
- Nada é apagado de verdade: vai para a lixeira, que o Gmail guarda 30 dias.

O que o `desfaz` **não** devolve é o que saiu da caixa de entrada por arquivamento — esses
continuam no "Todos os e-mails" com o marcador, mas voltar um por um é trabalho manual. Então
leia o ensaio.

## Ajustes que você provavelmente vai querer

Em `src/cli.py`, no topo:

| Constante | Padrão | O que faz |
| --- | --- | --- |
| `CAIXA_DIAS` | 3 | dias até um e-mail rotulado sair da caixa de entrada |
| `PROMO_DIAS` | 7 | dias até promoção ir para a lixeira |
| `CODIGO_DIAS` | 1 | dias até código de verificação ir para a lixeira |

A limpeza mais agressiva é por conta: `bin/secretario limpeza <conta> <dias>` manda para a
lixeira o que não for Pessoal, Compras ou Finanças acima desse prazo. `desliga` no lugar dos
dias desliga. Use numa conta que você não liga de perder, não na principal.

## Duas coisas que você precisa saber

1. **A classificação é em português.** As expressões que reconhecem promoção, cobrança,
   código de verificação e recibo estão em português, em `src/classificar.py`. Se a sua
   caixa for majoritariamente em inglês, a classificação por regra vai errar mais e cair
   na IA com mais frequência (que custa mais).
2. **O que as regras não resolvem vai para a IA**, por `hermes -z`, com toolset mínimo. O
   nível de raciocínio **não** é passado por argumento, porque alguns provedores recusam o
   campo: ele vem do modelo configurado no seu perfil do Hermes. Se o seu provedor aceitar o
   campo e você quiser economizar mais, acrescente `--reasoning none` em `src/ia.py`.

## Como desinstalar

```bash
hermes cron list                      # ache os ids de "Faxina de e-mails" e "Alerta de e-mails"
hermes cron remove <id>
rm -rf ~/.config/secretario-emails ~/.local/state/secretario-emails
```

Os marcadores `Secretário/...` continuam no Gmail; apague pela interface se quiser.

## Os dois crons, se você quiser criar à mão

`bin/secretario instalar` faz isso por você, de forma idempotente. Os comandos equivalentes:

```bash
hermes cron create "30 7 * * *"    --name "Secretário de e-mails" --no-agent \
  --script secretario.sh --deliver telegram
hermes cron create "*/15 * * * *"  --name "Alerta de e-mails"     --no-agent \
  --script secretario-alerta.sh --deliver telegram --failure-deliver local
```

`--no-agent` significa que o stdout do script vai direto para o Telegram, sem passar por um
modelo: a faxina já devolve o resumo pronto. O `--failure-deliver local` no alerta é de
propósito — se ele falhar a cada 15 minutos, o erro vai para o log em vez do seu Telegram.

Os scripts em `scripts/` têm `{{RAIZ}}` no lugar do caminho; o instalador troca pelo caminho
real e copia para `~/.hermes/scripts/`.
