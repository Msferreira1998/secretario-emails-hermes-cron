"""Extras da faxina e comandos de leitura: vencimentos, pedidos, recorrentes, aprender, desfaz, busca e alerta."""
import traceback
from collections import Counter, defaultdict
from datetime import timedelta

from src import classificar as cl
from src import contas as ct
from src import estado
from src.estado import casa
from src.imap import Caixa

APRENDE_DIAS = 14  # FR-022: janela para notar troca de marcador
PEDIDO_DIAS = 60  # FR-024: pedido sem novidade sai da lista
MAX_BUSCA = 10


# ---------------------------------------------------------------- durante a faxina

def guardar(con, conta, msgs, t, ensaio):
    """Vencimentos (FR-016), pedidos (FR-024) e a classificação original (FR-022) dos e-mails novos."""
    for m in msgs:
        if not m["msgid"]:
            continue
        if m["tipo"] == "Finanças":
            vence = cl.vencimento(m, t.date())
            if vence:
                con.execute("INSERT OR IGNORE INTO vencimentos VALUES (?,?,?,?,?,?)",
                            (conta, m["msgid"], m["de"], m["nome"], m["assunto"], vence.isoformat()))
        if m["tipo"] == "Compras" and cl.PEDIDO.search(m["assunto"]):
            numero = cl.NUMERO.search(m["assunto"])
            chave = numero.group(0) if numero else m["msgid"]
            if cl.ENTREGUE.search(m["assunto"]):
                con.execute("DELETE FROM pedidos WHERE conta = ? AND chave = ?", (conta, chave))
            else:
                con.execute("INSERT OR REPLACE INTO pedidos VALUES (?,?,?,?,?)",
                            (conta, chave, m["nome"] or m["de"].rsplit("@", 1)[-1], m["assunto"], m["data"].isoformat()))
        if not ensaio:
            con.execute("INSERT OR REPLACE INTO classificados VALUES (?,?,?,?,?)",
                        (conta, m["msgid"], m["de"], m["tipo"], t.isoformat()))


def aprender(con, cx, conta, t, regras):
    """FR-022: o usuário tirou o Secretário/<tipo> original e pôs outro → regra remetente → novo tipo."""
    linhas = con.execute("SELECT msgid, remetente, tipo FROM classificados WHERE conta = ? AND quando >= ?",
                         (conta, (t - timedelta(days=APRENDE_DIAS)).isoformat())).fetchall()
    if not linhas:
        return []
    atuais = defaultdict(set)
    for tipo in cl.TIPOS:
        for m in cx.recentes(tipo, APRENDE_DIAS + 1):
            atuais[m["msgid"]].add(tipo)
    aprendidos = []
    for msgid, remetente, original in linhas:
        agora = atuais.get(msgid, set())
        if len(agora) != 1 or original in agora:
            continue  # sem troca, com dois marcadores ou sem marcador nenhum: não dá para saber
        novo = agora.pop()
        con.execute("UPDATE classificados SET tipo = ? WHERE conta = ? AND msgid = ?", (novo, conta, msgid))
        if regras.get(remetente) != novo:
            con.execute("INSERT OR REPLACE INTO regras VALUES (?, ?)", (remetente, novo))
            regras[remetente] = novo
            aprendidos.append((remetente, novo))
    return aprendidos


def recorrentes(cx):
    """FR-018: domínio → meses distintos com recibo/fatura/assinatura nos últimos 95 dias (2 ou mais)."""
    meses = defaultdict(set)
    for tipo in ("Finanças", "Compras"):
        for m in cx.recentes(tipo, 95):
            if m["data"] and cl.RECIBO.search(m["assunto"]):
                meses[m["de"].rsplit("@", 1)[-1]].add((m["data"].year, m["data"].month))
    return {dom: len(ms) for dom, ms in meses.items() if len(ms) >= 2}


def vencem(con, t):
    hoje, amanha = t.date().isoformat(), (t.date() + timedelta(days=1)).isoformat()
    rows = con.execute("SELECT vence, conta, remetente, nome, assunto FROM vencimentos WHERE vence IN (?, ?) "
                       "ORDER BY vence, conta", (hoje, amanha)).fetchall()
    return [{"quando": "hoje" if v == hoje else "amanhã", "conta": c, "de": de, "nome": n, "assunto": a}
            for v, c, de, n, a in rows]


def pedidos(con, t):
    return con.execute("SELECT loja, assunto, conta FROM pedidos WHERE quando >= ? ORDER BY quando DESC",
                       ((t - timedelta(days=PEDIDO_DIAS)).isoformat(),)).fetchall()


def anotar_lixeira(con, t, conta, msgs):
    """FR-019: o que o secretário mandou para a lixeira, para o `desfaz`."""
    con.executemany("INSERT INTO lixeira VALUES (?,?,?,?)",
                    [(conta, m["msgid"], m["de"], t.isoformat()) for m in msgs if m.get("msgid")])


# ---------------------------------------------------------------- comandos

def desfaz(con, t):
    """FR-019: devolve à INBOX o que a última faxina real mandou para a lixeira."""
    dia = con.execute("SELECT MAX(dia) FROM execucoes WHERE ensaio = 0").fetchone()[0]
    por_conta = defaultdict(set)
    if dia:
        for conta, msgid in con.execute("SELECT conta, msgid FROM lixeira WHERE quando >= ?", (dia,)):
            por_conta[conta].add(msgid)
    voltaram = Counter()
    for conta in ct.listar():
        msgids = por_conta.get(conta["nome"])
        if not msgids:
            continue
        cx = Caixa(conta)
        try:
            volta = cx.restaurar(msgids)
        finally:
            cx.sair()
        con.executemany("INSERT OR REPLACE INTO restaurados VALUES (?, ?)", [(m["msgid"], t.isoformat()) for m in volta])
        con.executemany("DELETE FROM lixeira WHERE conta = ? AND msgid = ?", [(conta["nome"], m["msgid"]) for m in volta])
        voltaram.update(m["de"] for m in volta)
    con.commit()
    if not voltaram:
        print("Nada para desfazer: a última faxina não mandou nada para a lixeira que ainda esteja lá.")
        return 0
    quem = ", ".join(f"{de} ({n})" for de, n in voltaram.most_common(10))
    print(f"↩️ {sum(voltaram.values())} e-mails voltaram para a caixa de entrada: {quem}.\n"
          "Eles não serão apagados de novo. Para os próximos desse remetente: \"protege <remetente>\".")
    return 0


def busca(texto):
    """FR-020: os mais recentes das duas contas, fora da lixeira, sem alterar nada."""
    if not texto:
        print("Uso: busca <texto>. Ex.: busca fatura nubank")
        return 2
    achados = []
    for conta in ct.listar():
        try:
            cx = Caixa(conta)
        except Exception:
            print(f"{conta['nome']}: sem conexão")
            continue
        try:
            if cx.gmail and "\\All" in cx.especiais:
                uids = cx.buscar(texto)[-50:]  # UIDs maiores costumam ser os mais novos; a data decide abaixo
                achados += [dict(m, conta=conta["nome"]) for m in cx.cabecalhos(uids)]
        finally:
            cx.sair()
    if not achados:
        print(f"Nada encontrado para {texto}.")
        return 0
    achados.sort(key=lambda m: m["data"].timestamp() if m["data"] else 0, reverse=True)
    print(f"🔎 {min(len(achados), MAX_BUSCA)} mais recentes:")
    for m in achados[:MAX_BUSCA]:
        data = f"{m['data']:%d/%m/%Y}" if m["data"] else "sem data"
        print(f"{data} {m['conta']} — {m['nome'] or m['de']}: {m['assunto']}")
    return 0


def alerta(con):
    """FR-021: novos da INBOX desde a rodada anterior; 🚨 segurança, ⭐ VIP. Silêncio sem alerta ou com erro."""
    regras, vips = estado.regras(con), estado.lista(con, "vips")
    linhas = []
    for conta in ct.listar():
        nome = conta["nome"]
        try:
            cx = Caixa(conta)
            try:
                r = con.execute("SELECT alerta_uid FROM contas WHERE nome = ?", (nome,)).fetchone()
                ponteiro = r[0] if r else None
                if ponteiro is None:
                    novo = cx.maior_uid()  # primeira rodada só posiciona: nada de alertar o passado
                else:
                    msgs = cx.novos(ponteiro, so_leitura=True)
                    for m in msgs:
                        quem = m["nome"] or m["de"]
                        if any(casa(m["de"], v) for v in vips):
                            linhas.append(f"⭐ {nome}: {quem} — {m['assunto']}")
                        elif cl.por_regras(m, regras) == "Segurança":
                            linhas.append(f"🚨 {nome}: {quem} — {m['assunto']}")
                    novo = max([m["uid"] for m in msgs], default=ponteiro)
            finally:
                cx.sair()
            con.execute("INSERT INTO contas(nome, alerta_uid) VALUES (?, ?) "
                        "ON CONFLICT(nome) DO UPDATE SET alerta_uid = excluded.alerta_uid", (nome, novo))
            con.commit()
        except Exception:
            with open(estado.caminho().parent / "erros.log", "a") as f:
                f.write(f"--- alerta {nome}\n{traceback.format_exc()}")
    if linhas:
        print("\n".join(linhas))
    return 0
