"""CLI do secretário de e-mails: faxina diária, comandos do Telegram, respostas, contas e instalação."""
import imaplib
import re
import traceback
import unicodedata
from collections import defaultdict
from datetime import datetime, timedelta
from email.message import EmailMessage
from zoneinfo import ZoneInfo

from src import classificar as cl
from src import contas as ct
from src import descadastro, estado, extras, ia, resumo
from src.estado import casa
from src.imap import Caixa

USO = """uso: secretario faxina
       secretario protege|desprotege|veta|libera <remetente|domínio>
       secretario papel <conta> <papel…>
       secretario limpeza <conta> <dias|desliga>
       secretario limpa <remetente|domínio> <dias|desliga>
       secretario regra <remetente|domínio> <tipo>
       secretario vip|desvip <remetente|domínio>
       secretario busca <texto…>
       secretario desfaz
       secretario alerta
       secretario responder <código E…> <texto…>
       secretario envia <código R…>
       secretario conta adicionar <nome>
       secretario instalar"""

PROMO_DIAS = 7  # FR-002: promoções vão para a lixeira depois disso
CAIXA_DIAS = 3  # FR-014: rotulados saem da caixa de entrada depois disso
CODIGO_DIAS = 1  # FR-017: códigos de verificação expiram
REMETENTE = re.compile(r"([\w.+-]+@)?[\w-]+(\.[\w-]+)+")  # e-mail ou domínio; vai para a busca do Gmail

# tipo → palavra que precisa aparecer no papel da conta certa
DONO = {"Compras": "compras", "Promoções": "compras", "Trabalho": "trabalho", "Pessoal": "pessoal", "Finanças": "financas",
        "Newsletters": "newsletters", "Segurança": "seguranca"}


def agora():
    return datetime.now(ZoneInfo("America/Sao_Paulo"))


def _norm(t):
    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()


def conta_certa(tipo, nome, papeis):
    chave = DONO.get(tipo)
    if not chave or nome not in papeis or chave in _norm(papeis[nome]):
        return None
    return next((n for n, p in papeis.items() if n != nome and chave in _norm(p)), None)


# ---------------------------------------------------------------- faxina

def faxina(t):
    con = estado.abrir()
    try:
        return _faxina(con, t)
    finally:
        con.close()


def _faxina(con, t):
    estado.limpar(con, t)
    ensaio = not estado.ja_ensaiou(con)
    ctx = {
        "regras": estado.regras(con), "protegidos": estado.lista(con, "protegidos"),
        "vetos": estado.lista(con, "vetos"), "papeis": estado.papeis(con),
        "restaurados": {r[0] for r in con.execute("SELECT msgid FROM restaurados")},
    }
    resultados, pendentes, descad, manual, avisos = {}, [], set(), set(), []
    ex = {"golpes": [], "aprendidos": [], "recorrentes": {}}
    lista_contas = ct.listar()
    ctx["meus"] = [c["email"].lower() for c in lista_contas]
    for conta in lista_contas:
        c = resultados[conta["nome"]] = {"novos": 0, "rotulados": 0, "arquivados": 0, "apagados": 0, "descadastrados": 0}
        try:
            cx = Caixa(conta)
        except imaplib.IMAP4.error:
            c["erro"] = "login recusado"
            continue
        except Exception as e:
            c["erro"] = f"sem conexão ({type(e).__name__})"
            continue
        try:
            if not ensaio and cx.gmail:  # antes de classificar, para a regra aprendida já valer hoje
                ex["aprendidos"] += extras.aprender(con, cx, conta["nome"], t, ctx["regras"])
            _processar(con, cx, conta, c, ctx, t, ensaio, pendentes, descad, manual, avisos, ex)
            _limpar_antigos(con, cx, conta, c, ctx, t, ensaio)
            c["fora_da_caixa"] = cx.tirar_da_caixa(cl.TIPOS, CAIXA_DIAS, ensaio)
            if t.day == 1 and cx.gmail:
                for dom, n in extras.recorrentes(cx).items():
                    ex["recorrentes"][dom] = max(n, ex["recorrentes"].get(dom, 0))
            con.commit()
        except Exception as e:
            con.rollback()
            c["erro"] = f"falhou no meio ({type(e).__name__}); tento de novo amanhã"
            with open(estado.caminho().parent / "erros.log", "a") as f:
                f.write(f"--- {t.isoformat()} {conta['nome']}\n{traceback.format_exc()}")
        finally:
            cx.sair()
    plano, sem_papel = None, ()
    if t.weekday() == 0:
        plano = _plano(con, t)
        sem_papel = [n for n in resultados if n not in ctx["papeis"]]
    # ensaio só vale como feito se todas as contas foram lidas; senão o próximo também é ensaio
    if not (ensaio and any(c.get("erro") for c in resultados.values())):
        con.execute("INSERT INTO execucoes(dia, ensaio, quando) VALUES (?,?,?)", (t.date().isoformat(), int(ensaio), t.isoformat()))
    con.commit()
    ex["vencem"], ex["pedidos"] = extras.vencem(con, t), extras.pedidos(con, t)
    print(resumo.montar(resultados, pendentes, descad, manual, avisos, ensaio, plano, sem_papel, ex))
    return 0


def _intocavel(cx, ctx, embutida=True):
    """Proteções do FR-004: embutidas, próprias contas, protegidos, vetos, quem já recebeu e-mail seu e restaurados."""
    cache = {}

    def escreveu(de):
        if de not in cache:
            cache[de] = cx.ja_escreveu_para(de)
        return cache[de]

    def intocavel(m):
        de = m["de"]
        return ((embutida and cl.protegido_embutido(m)) or de in ctx["meus"] or m.get("msgid") in ctx["restaurados"]
                or any(casa(de, p) for p in ctx["protegidos"] + ctx["vetos"])
                or escreveu(de))
    return intocavel


def _limpar_antigos(con, cx, conta, c, ctx, t, ensaio):
    """Lixeira dos já rotulados: Promoções (FR-002), limpeza da conta (FR-013), por remetente (FR-015) e códigos (FR-017)."""
    buscas = [(["Promoções"], PROMO_DIAS, None)]
    dias = con.execute("SELECT limpeza_dias FROM contas WHERE nome = ?", (conta["nome"],)).fetchone()
    if dias and dias[0]:
        buscas.append((cl.LIMPAVEIS, dias[0], None))
    buscas += [(cl.LIMPAVEIS, d, r) for r, d in con.execute("SELECT remetente, dias FROM limpa_remetentes")]
    intocavel = _intocavel(cx, ctx)
    achados = {}
    for tipos, d, de in buscas:
        for m in cx.antigos(tipos, d, de):
            if (de is None or casa(m["de"], de)) and not intocavel(m):
                achados[m["uid"]] = m
    sem_embutida = _intocavel(cx, ctx, embutida=False)  # o código já expirou, mesmo vindo do Google ou do banco
    for m in cx.antigos(["Segurança", "Notificações"], CODIGO_DIAS):
        if cl.CODIGO.search(m["assunto"]) and not sem_embutida(m):
            achados[m["uid"]] = m
    alvo = list(achados.values())
    c["antigos"] = len(alvo)
    if alvo and not ensaio:
        cx.lixeira_em_todos({m["uid"] for m in alvo})
        extras.anotar_lixeira(con, t, conta["nome"], alvo)
        for m in alvo:
            estado.registrar(con, t, conta["nome"], m["de"], "antigo_apagado", m["tipo"])


def _processar(con, cx, conta, c, ctx, t, ensaio, pendentes, descad, manual, avisos, ex):
    nome = conta["nome"]
    msgs = cx.novos(estado.ultimo_uid(con, nome), so_leitura=ensaio)
    c["novos"] = len(msgs)
    if not msgs:
        return
    _, aviso = cl.classificar(msgs, ctx["regras"], lambda p: ia.perguntar(p))
    if aviso:
        avisos.append(f"{nome}: {aviso}")
    intocavel = _intocavel(cx, ctx)
    suspeitos = [m for m in msgs if m["suspeito"]]
    ex["golpes"] += [dict(m, conta=nome) for m in suspeitos]
    extras.guardar(con, nome, msgs, t, ensaio)

    lixo = [m for m in msgs if m["tipo"] == "Promoções" and (t - m["data"]).days > PROMO_DIAS and not intocavel(m)]

    # descadastro: 3+ e-mails em 60 dias e nenhum lido (contando os vistos em faxinas anteriores)
    por_remetente = defaultdict(list)
    for m in msgs:
        if m["unsub"] and not m["suspeito"]:  # descadastrar golpe confirma ao golpista que o e-mail existe
            por_remetente[m["de"]].append(m)
    desc, sozinho = [], []
    limite = (t - timedelta(days=60)).isoformat()
    for de, lista in por_remetente.items():
        lista = [m for m in lista if (t - m["data"]).days <= 60]
        vistos = con.execute("SELECT COUNT(*), COALESCE(SUM(lido), 0) FROM vistos "
                             "WHERE conta = ? AND remetente = ? AND quando >= ?", (nome, de, limite)).fetchone()
        if not lista or len(lista) + vistos[0] < 3 or vistos[1] or any(m["lido"] for m in lista):
            continue
        if intocavel(lista[-1]) or _ja_tentou(con, de, t) or any(m["msgid"] in ctx["restaurados"] for m in lista):
            continue
        (desc if descadastro.como(lista[-1]) else sozinho).append(lista[-1])

    errada = {}
    for m in msgs:
        dono = conta_certa(m["tipo"], nome, ctx["papeis"])
        if dono:
            errada[m["uid"]] = dono

    ids_lixo = {m["uid"] for m in lixo}
    sozinhos = {m["de"] for m in sozinho}
    arquivar = [m for m in msgs if m["uid"] not in ids_lixo and (m["tipo"] in cl.SEM_ACAO or m["de"] in sozinhos)]
    c["rotulados"], c["arquivados"], c["apagados"] = len(msgs), len(arquivar), len(lixo)
    manual.update(m["de"] for m in sozinho)

    if not ensaio:
        cx.selecionar_inbox(so_leitura=False)
        por_tipo = defaultdict(set)
        for m in msgs:
            por_tipo[m["tipo"]].add(m["uid"])
        for tipo, uids in por_tipo.items():
            cx.rotular(uids, f"Secretário/{tipo}")
        cx.rotular(set(errada), "Secretário/Conta errada")
        cx.rotular({m["uid"] for m in suspeitos}, "Secretário/Suspeito")
        cx.marcar_lido({m["uid"] for m in msgs if m["tipo"] in cl.SEM_ACAO})
        for tipo in {m["tipo"] for m in arquivar}:
            cx.arquivar({m["uid"] for m in arquivar if m["tipo"] == tipo}, f"Secretário/{tipo}")
        if not cx.lixeira(ids_lixo):
            cx.arquivar(ids_lixo, "Secretário/Promoções")
        else:
            extras.anotar_lixeira(con, t, nome, lixo)
        for m in desc:
            try:
                ok = descadastro.descadastrar(m, conta, ct.smtp)
            except Exception:
                ok = False
            estado.registrar(con, t, nome, m["de"], "descadastrado" if ok else "descadastro_falhou")
            if ok:
                c["descadastrados"] += 1
                descad.add(m["de"])
        for m in msgs:
            acao = "apagado" if m["uid"] in ids_lixo else "arquivado" if m in arquivar else "rotulado"
            estado.registrar(con, t, nome, m["de"], acao, m["tipo"])
            if m["uid"] in errada:
                estado.registrar(con, t, nome, m["de"], "conta_errada", f"{m['nome'] or m['de']}|{errada[m['uid']]}")
        con.executemany("INSERT OR REPLACE INTO vistos(conta, remetente, uid, quando, lido) VALUES (?,?,?,?,?)",
                        [(nome, m["de"], m["uid"], m["data"].isoformat(), int(m["lido"])) for m in msgs])
        estado.gravar_uid(con, nome, max(m["uid"] for m in msgs))
    else:
        c["descadastrados"] = len(desc)
        descad.update(m["de"] for m in desc)

    for m in msgs:
        recente = (t - m["data"]).days <= 7  # os antigos ficam na caixa, rotulados, sem poluir o resumo
        if m["tipo"] in cl.PEDEM_VOCE and m["uid"] not in ids_lixo and not m["lido"] and recente:
            cur = con.execute("INSERT INTO pendentes(conta, msgid, remetente, nome, assunto, quando) VALUES (?,?,?,?,?,?)",
                              (nome, m["msgid"], m["de"], m["nome"], m["assunto"], t.isoformat()))
            pendentes.append({"codigo": f"E{cur.lastrowid}", "nome": m["nome"], "de": m["de"],
                              "conta": nome, "assunto": m["assunto"]})


def _ja_tentou(con, de, t):
    """Já descadastrado, ou 3 falhas, ou falha nos últimos 7 dias."""
    linhas = con.execute("SELECT acao, quando FROM historico WHERE remetente = ? AND acao LIKE 'descadastr%'", (de,)).fetchall()
    if any(a == "descadastrado" for a, _ in linhas):
        return True
    falhas = [q for a, q in linhas if a == "descadastro_falhou"]
    return len(falhas) >= 3 or any(q >= (t - timedelta(days=7)).isoformat() for q in falhas)


def _plano(con, t):
    linhas = con.execute("SELECT remetente, motivo FROM historico WHERE acao = 'conta_errada' AND quando >= ?",
                         ((t - timedelta(days=7)).isoformat(),)).fetchall()
    grupos = defaultdict(list)
    for de, motivo in linhas:
        grupos[de].append(motivo)
    plano = []
    for de, motivos in sorted(grupos.items(), key=lambda g: -len(g[1])):
        nome, certa = motivos[-1].rsplit("|", 1)
        plano.append((nome, certa, len(motivos)))
    return plano


# ---------------------------------------------------------------- comandos

def comando(con, cmd, args):
    alvo = args[0].lower() if args else None
    if not alvo:
        print(USO)
        return 2
    if cmd == "protege":
        con.execute("INSERT OR IGNORE INTO protegidos VALUES (?)", (alvo,))
        print(f"🛡️ {alvo} protegido: os e-mails dele podem ser rotulados e arquivados, nunca apagados nem descadastrados.")
    elif cmd == "desprotege":
        con.execute("DELETE FROM protegidos WHERE remetente = ?", (alvo,))
        print(f"{alvo} não está mais protegido.")
    elif cmd == "veta":
        con.execute("INSERT OR IGNORE INTO vetos VALUES (?)", (alvo,))
        print(f"🚫 {alvo} não será descadastrado nem terá e-mails apagados.")
    elif cmd == "libera":
        if alvo == "descadastro" and len(args) > 1:
            alvo = args[1].lower()
        con.execute("DELETE FROM vetos WHERE remetente = ?", (alvo,))
        print(f"{alvo} pode voltar a ser descadastrado.")
    elif cmd == "regra":
        tipo = cl.normalizar_tipo(" ".join(args[1:]))
        if not tipo:
            print(f"Tipo inválido. Use um destes: {', '.join(cl.TIPOS)}.")
            return 2
        con.execute("INSERT OR REPLACE INTO regras VALUES (?, ?)", (alvo, tipo))
        print(f"Regra gravada: {alvo} → {tipo}.")
    elif cmd == "limpeza":
        nomes = [c["nome"] for c in ct.listar()]
        valor = args[1].lower() if len(args) > 1 else ""
        if alvo not in nomes or not (valor == "desliga" or (valor.isdigit() and int(valor) > 0)):
            print(f"Uso: limpeza <conta> <dias|desliga>. Contas: {', '.join(nomes)}.")
            return 2
        dias = None if valor == "desliga" else int(valor)
        con.execute("INSERT INTO contas(nome, limpeza_dias) VALUES (?, ?) "
                    "ON CONFLICT(nome) DO UPDATE SET limpeza_dias = excluded.limpeza_dias", (alvo, dias))
        print(f"Conta {alvo}: limpeza de antigos desligada." if dias is None else
              f"Conta {alvo}: promoções, newsletters e notificações com mais de {dias} dias vão para a lixeira "
              "a cada faxina (pessoal, compras, finanças, segurança, trabalho, outros e protegidos nunca).")
    elif cmd == "limpa":
        valor = args[1].lower() if len(args) > 1 else ""
        if not REMETENTE.fullmatch(alvo) or not (
                valor == "desliga" or (valor.isdigit() and int(valor) > 0)):
            print("Uso: limpa <remetente|domínio> <dias|desliga>. Ex.: limpa sheinemail.com 3")
            return 2
        if valor == "desliga":
            con.execute("DELETE FROM limpa_remetentes WHERE remetente = ?", (alvo,))
            print(f"{alvo}: lixeira por remetente desligada.")
        else:
            con.execute("INSERT OR REPLACE INTO limpa_remetentes VALUES (?, ?)", (alvo, int(valor)))
            print(f"🧹 {alvo}: promoções, newsletters e notificações com mais de {valor} dias vão para a lixeira "
                  "nas duas contas (bancos, protegidos e vetados nunca).")
    elif cmd in ("vip", "desvip"):
        if not REMETENTE.fullmatch(alvo):
            print(f"Uso: {cmd} <remetente|domínio>. Ex.: vip chefe@empresa.com")
            return 2
        if cmd == "vip":
            con.execute("INSERT OR IGNORE INTO vips VALUES (?)", (alvo,))
            print(f"⭐ {alvo} é VIP: e-mail dele gera aviso no Telegram em até 15 minutos.")
        else:
            con.execute("DELETE FROM vips WHERE remetente = ?", (alvo,))
            print(f"{alvo} não é mais VIP.")
    elif cmd == "papel":
        nomes = [c["nome"] for c in ct.listar()]
        if alvo not in nomes or len(args) < 2:
            print(f"Uso: papel <conta> <papel>. Contas: {', '.join(nomes)}.")
            return 2
        papel = " ".join(args[1:])
        con.execute("INSERT INTO contas(nome, papel) VALUES (?, ?) ON CONFLICT(nome) DO UPDATE SET papel = excluded.papel",
                    (alvo, papel))
        print(f"Conta {alvo}: papel \"{papel}\".")
    con.commit()
    return 0


def responder(con, t, codigo, texto):
    p = con.execute("SELECT conta, msgid, remetente, nome, assunto FROM pendentes WHERE id = ?",
                    (_numero(codigo, "E"),)).fetchone()
    if not p or not texto:
        print(f"Não achei o e-mail {codigo} (os códigos valem 30 dias). Uso: responder <código> <texto>.")
        return 1
    conta, msgid, para, nome, assunto = p
    assunto = assunto if assunto.lower().startswith("re:") else f"Re: {assunto}"
    cur = con.execute("INSERT INTO rascunhos(conta, msgid, para, assunto, texto, criado_em) VALUES (?,?,?,?,?,?)",
                      (conta, msgid, para, assunto, texto, t.isoformat()))
    con.commit()
    r = f"R{cur.lastrowid}"
    print(f"✍️ Rascunho {r} para {nome or para} <{para}> (conta {conta})\nAssunto: {assunto}\n\n{texto}\n\n"
          f"Nada foi enviado. Para enviar, mande \"envia {r}\".")
    return 0


def envia(con, t, codigo):
    r = con.execute("SELECT id, conta, msgid, para, assunto, texto, criado_em FROM rascunhos WHERE id = ?",
                    (_numero(codigo, "R"),)).fetchone()
    if not r or r[6] < (t - timedelta(days=30)).isoformat():
        print(f"O rascunho {codigo} não existe ou expirou (rascunhos valem 30 dias). Peça a resposta de novo.")
        return 1
    rid, nome, msgid, para, assunto, texto, _ = r
    conta = next((c for c in ct.listar() if c["nome"] == nome), None)
    if conta is None:
        print(f"A conta {nome} não está mais cadastrada.")
        return 1
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = conta["email"], para, assunto
    if msgid:
        msg["In-Reply-To"] = msg["References"] = msgid
    msg.set_content(texto)
    with ct.smtp(conta) as s:
        s.send_message(msg)
    con.execute("DELETE FROM rascunhos WHERE id = ?", (rid,))
    estado.registrar(con, t, nome, para, "enviado", assunto)
    con.commit()
    print(f"📤 Enviado para {para} pela conta {nome}.")
    return 0


def _numero(codigo, letra):
    c = codigo.strip().upper()
    return int(c[1:]) if c.startswith(letra) and c[1:].isdigit() else -1


def main(argv):
    if not argv:
        print(USO)
        return 2
    cmd, args = argv[0], argv[1:]
    t = agora()
    try:
        if cmd == "faxina":
            if args:  # faxina altera a caixa de verdade: argumento não reconhecido não roda nada
                print(f"faxina não aceita argumento ({' '.join(args)}). A primeira rodada já é "
                      f"ensaio automático; as seguintes são reais.\n{USO}")
                return 2
            return faxina(t)
        if cmd == "busca":
            return extras.busca(" ".join(args).strip())
        if cmd == "alerta":
            con = estado.abrir()
            try:
                return extras.alerta(con)
            finally:
                con.close()
        if cmd == "instalar":
            from src import instalar
            return instalar.instalar()
        if cmd == "conta" and args[:1] == ["adicionar"] and len(args) == 2:
            return ct.adicionar(args[1])
        con = estado.abrir()
        try:
            if cmd in ("protege", "desprotege", "veta", "libera", "regra", "papel", "limpeza", "limpa", "vip", "desvip"):
                return comando(con, cmd, args)
            if cmd == "desfaz":
                return extras.desfaz(con, t)
            if cmd == "responder" and args:
                return responder(con, t, args[0], " ".join(args[1:]).strip())
            if cmd == "envia" and args:
                return envia(con, t, args[0])
        finally:
            con.close()
    except Exception as e:
        print(f"❌ Secretário ({cmd}) falhou: {type(e).__name__}")
        return 1
    print(USO)
    return 2
