"""Dublês de teste: HOME temporário, servidores IMAP/SMTP falsos, HTTP e IA falsos.

O IMAP falso imita o modelo do Gmail (uma caixa só, pastas = marcadores) quando
`gmail=True`, e pastas independentes no IMAP genérico. Ele devolve respostas no
mesmo formato do imaplib, então src/imap.py é exercitado de verdade.
"""
import contextlib
import email.utils
import imaplib
import io
import json
import os
import re
import smtplib
import stat
import sys
import tempfile
import textwrap
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

AGORA = datetime(2026, 10, 28, 7, 30, tzinfo=timezone(timedelta(hours=-3)))  # quarta
SEGUNDA = datetime(2026, 11, 2, 7, 30, tzinfo=timezone(timedelta(hours=-3)))

GMAIL_PASTAS = {
    "INBOX": ("\\HasNoChildren", "\\Inbox"),
    "[Gmail]/Lixeira": ("\\HasNoChildren", "\\Trash"),
    "[Gmail]/E-mails enviados": ("\\HasNoChildren", "\\Sent"),
    "[Gmail]/Todos os e-mails": ("\\HasNoChildren", "\\All"),
}


class Msg:
    def __init__(self, uid, de, assunto, dias=0, lido=False, cabecalhos=None, texto="", para="eu@x.com"):
        self.uid = uid
        self.msgid = f"<m{uid}@teste>"  # fica igual quando o Gmail dá UID novo (restaurar da lixeira)
        self.de = de
        self.assunto = assunto
        self.data = AGORA - timedelta(days=dias)
        self.flags = {"\\Seen"} if lido else set()
        self.labels = {"\\Inbox"}
        self.cab = cabecalhos or {}
        self.texto = texto
        self.para = para

    def header(self):
        linhas = [f"From: {self.de}", f"To: {self.para}", f"Subject: {self.assunto}",
                  f"Date: {email.utils.format_datetime(self.data)}",
                  f"Message-ID: {self.msgid}"]
        linhas += [f"{k}: {v}" for k, v in self.cab.items()]
        return ("\r\n".join(linhas) + "\r\n\r\n").encode()


class ServidorIMAP:
    """Estado de uma conta. Registrado por (host, usuário)."""

    def __init__(self, usuario, senha, gmail=True, pastas=None, starttls=False):
        self.usuario, self.senha, self.gmail, self.exige_starttls = usuario, senha, gmail, starttls
        self.msgs = []           # Gmail: todas; genérico: dicionário por pasta em self.caixas
        self.caixas = {}
        self.pastas = dict(pastas or GMAIL_PASTAS)
        self.comandos = []       # log de comandos recebidos
        self.prox_uid = 1
        self.recusar = False

    def add(self, de, assunto, pasta="INBOX", **kw):
        m = Msg(self.prox_uid, de, assunto, **kw)
        self.prox_uid += 1
        if self.gmail:
            if pasta != "INBOX":
                m.labels = {"\\Sent"} if pasta == "[Gmail]/E-mails enviados" else {pasta}
            self.msgs.append(m)
        else:
            self.caixas.setdefault(pasta, []).append(m)
        return m

    def em(self, pasta):
        if not self.gmail:
            return self.caixas.setdefault(pasta, [])
        atrib = self.pastas.get(pasta, ())
        if "\\All" in atrib:
            return [m for m in self.msgs if "\\Trash" not in m.labels]
        if "\\Trash" in atrib:
            return [m for m in self.msgs if "\\Trash" in m.labels]
        if "\\Sent" in atrib:
            return [m for m in self.msgs if "\\Sent" in m.labels]
        if pasta == "INBOX":
            return [m for m in self.msgs if "\\Inbox" in m.labels and "\\Trash" not in m.labels]
        return [m for m in self.msgs if pasta in m.labels and "\\Trash" not in m.labels]

    def todas(self):
        if self.gmail:
            return list(self.msgs)
        return [m for c in self.caixas.values() for m in c]

    def onde(self, m):
        """Pastas em que a mensagem aparece."""
        return {p for p in set(self.pastas) | set(self.caixas) if m in self.em(p)}


SERVIDORES = {}


def _q(s):
    return s[1:-1] if s.startswith('"') and s.endswith('"') else s


class IMAPFalso:
    error, abort, readonly = imaplib.IMAP4.error, imaplib.IMAP4.abort, imaplib.IMAP4.readonly

    def __init__(self, host="", port=None, **kw):
        self.host, self.port = host, port
        self.srv = None
        self.sel = None
        self.literal = None
        self.tls = port == 993

    # imaplib.IMAP4 só
    def starttls(self, ssl_context=None):
        self.tls = True
        return "OK", [b"Begin TLS"]

    def login(self, usuario, senha):
        srv = SERVIDORES.get((self.host, usuario))
        if srv is None or srv.recusar or srv.senha != senha:
            raise imaplib.IMAP4.error("[AUTHENTICATIONFAILED] Invalid credentials")
        if srv.exige_starttls and not self.tls:
            raise imaplib.IMAP4.error("LOGINDISABLED")
        self.srv = srv
        srv.comandos.append(("LOGIN", "STARTTLS" if self.port == 143 and self.tls else "SSL"))
        return "OK", [b"ok"]

    def capability(self):
        return "OK", [b"IMAP4rev1 UIDPLUS MOVE" + (b" X-GM-EXT-1" if self.srv.gmail else b"")]

    def list(self, directory='""', pattern="*"):
        linhas = [f'({" ".join(a)}) "/" "{p}"'.encode() for p, a in self.srv.pastas.items()]
        return "OK", linhas

    def select(self, mailbox="INBOX", readonly=False):
        self.sel = _q(mailbox)
        self.srv.comandos.append(("SELECT", self.sel, readonly))
        return "OK", [str(len(self.srv.em(self.sel))).encode()]

    def create(self, mailbox):
        nome = _q(mailbox)
        self.srv.pastas.setdefault(nome, ("\\HasNoChildren",))
        self.srv.comandos.append(("CREATE", nome))
        return "OK", [b"ok"]

    def _sel(self):
        return sorted(self.srv.em(self.sel), key=lambda m: m.uid)

    def _conjunto(self, spec):
        uids = set()
        maior = max([m.uid for m in self.srv.todas()] or [0])
        for parte in spec.split(","):
            if ":" in parte:
                a, b = parte.split(":")
                b = maior if b == "*" else int(b)
                uids |= set(range(int(a), max(int(a), b) + 1))
            else:
                uids.add(int(parte))
        return [m for m in self._sel() if m.uid in uids]

    def _busca(self, args):
        msgs = self._sel()
        toks = []
        for a in args:
            toks += re.findall(r'"[^"]*"|\S+', a) if isinstance(a, str) else [a]
        i = 0
        while i < len(toks):
            t = toks[i].upper()
            if t == "ALL":
                pass
            elif t == "UID":
                i += 1
                ok = {m.uid for m in self._conjunto(toks[i])}
                msgs = [m for m in msgs if m.uid in ok]
            elif t == "SINCE":
                i += 1
                d = datetime.strptime(_q(toks[i]), "%d-%b-%Y").date()
                msgs = [m for m in msgs if m.data.date() >= d]
            elif t == "FROM":
                i += 1
                alvo = _q(toks[i]).lower()
                msgs = [m for m in msgs if alvo in m.de.lower()]
            elif t == "TO":
                i += 1
                alvo = _q(toks[i]).lower()
                msgs = [m for m in msgs if alvo in m.para.lower()]
            elif t == "SEEN":
                msgs = [m for m in msgs if "\\Seen" in m.flags]
            elif t == "UNSEEN":
                msgs = [m for m in msgs if "\\Seen" not in m.flags]
            elif t == "X-GM-RAW":  # o que o secretário usa: [-]label:, from:, older_than:, newer_than: e texto (via literal)
                for termo in self.literal.decode().split():
                    nao, termo = termo.startswith("-"), termo.lstrip("-")
                    chave, _, valor = termo.partition(":") if ":" in termo else ("", "", termo)
                    if chave == "label":
                        ok = lambda m, v=valor: v in {utf7(l) for l in m.labels}
                    elif chave == "from":
                        ok = lambda m, v=valor.lower(): v in m.de.lower()
                    elif chave == "older_than":
                        ok = lambda m, v=int(valor[:-1]): m.data <= AGORA - timedelta(days=v)
                    elif chave == "newer_than":
                        ok = lambda m, v=int(valor[:-1]): m.data > AGORA - timedelta(days=v)
                    else:
                        ok = lambda m, v=termo.lower(): v in m.assunto.lower() or v in m.texto.lower()
                    msgs = [m for m in msgs if ok(m) != nao]
            i += 1
        return msgs

    def uid(self, cmd, *args):
        cmd = cmd.upper()
        self.srv.comandos.append(("UID " + cmd, self.sel) + tuple(a for a in args if a is not None))
        if cmd == "SEARCH":
            achados = self._busca([a for a in args if a is not None and a.upper() not in ("CHARSET", "UTF-8")])
            return "OK", [" ".join(str(m.uid) for m in achados).encode()]
        if cmd == "FETCH":
            dados = []
            for n, m in enumerate(self._conjunto(args[0]), 1):
                hdr = m.header()
                txt = m.texto.encode()[:2000]
                flags = " ".join(sorted(m.flags))
                labels = " ".join(f'"{l}"' for l in sorted(m.labels))
                data = m.data.strftime("%d-%b-%Y %H:%M:%S %z")
                # mesma ordem que o Gmail real devolve: TEXT antes do HEADER
                pre = f'{n} (UID {m.uid} INTERNALDATE "{data}" FLAGS ({flags}) X-GM-LABELS ({labels}) BODY[TEXT]<0> {{{len(txt)}}}'
                dados.append((pre.encode(), txt))
                dados.append((f" BODY[HEADER] {{{len(hdr)}}}".encode(), hdr))
                dados.append(b")")
            return "OK", dados or [None]
        alvos = self._conjunto(args[0])
        if cmd == "STORE":
            op, valor = args[1].upper(), args[2]
            itens = set(re.findall(r'"[^"]*"|\S+', valor.strip("()")))
            itens = {_q(x) for x in itens}
            for m in alvos:
                if "X-GM-LABELS" in op:
                    if not op.startswith("+") and self.sel == "INBOX":
                        itens = itens - {"\\Inbox"}  # Gmail real ignora (visto em 2026-10-28): não arquiva assim
                    m.labels = (m.labels | itens) if op.startswith("+") else (m.labels - itens)
                else:
                    m.flags = (m.flags | itens) if op.startswith("+") else (m.flags - itens)
            return "OK", [b"ok"]
        if cmd in ("COPY", "MOVE"):
            destino = _q(args[1])
            for m in alvos:
                if self.srv.gmail:
                    atrib = self.srv.pastas.get(destino, ())
                    m.labels.add("\\Trash" if "\\Trash" in atrib else "\\Inbox" if destino == "INBOX" else destino)
                    if cmd == "MOVE" and "\\Trash" in self.srv.pastas.get(self.sel, ()):
                        m.labels.discard("\\Trash")
                        m.uid, self.srv.prox_uid = self.srv.prox_uid, self.srv.prox_uid + 1  # Gmail: UID novo na INBOX
                    elif cmd == "MOVE":
                        m.labels.discard("\\Inbox" if self.sel == "INBOX" else self.sel)
                else:
                    self.srv.caixas.setdefault(destino, []).append(m)
                    if cmd == "MOVE":
                        self.srv.caixas[self.sel].remove(m)
            return "OK", [b"ok"]
        raise AssertionError(f"comando IMAP não suportado no dublê: {cmd}")

    def expunge(self):
        self.srv.comandos.append(("EXPUNGE", self.sel))
        for m in [m for m in self._sel() if "\\Deleted" in m.flags]:
            m.flags.discard("\\Deleted")
            if self.srv.gmail:
                m.labels.discard("\\Inbox" if self.sel == "INBOX" else self.sel)
            else:
                self.srv.caixas[self.sel].remove(m)
        return "OK", [b"ok"]

    def close(self):
        return "OK", [b"ok"]

    def logout(self):
        return "BYE", [b"ok"]


ENVIADOS = []   # (host, de, para, mensagem)


class SMTPFalso:
    def __init__(self, host="", port=None, **kw):
        self.host, self.port, self.usuario = host, port, None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def ehlo(self, *a):
        return 250, b"ok"

    def starttls(self, *a, **kw):
        return 220, b"ok"

    def login(self, usuario, senha):
        srv = SERVIDORES.get((self.host.replace("smtp", "imap"), usuario))
        if srv is None or srv.recusar or srv.senha != senha:
            raise smtplib.SMTPAuthenticationError(535, b"bad credentials")
        self.usuario = usuario
        return 235, b"ok"

    def send_message(self, msg, *a, **kw):
        ENVIADOS.append((self.host, self.usuario, msg["To"], msg))
        return {}

    def quit(self):
        return 221, b"bye"


class HTTPFalso:
    def __init__(self):
        self.pedidos = []
        self.status = 200

    def __call__(self, req, timeout=None, **kw):
        self.pedidos.append(req)
        resp = mock.MagicMock()
        resp.status = self.status
        resp.__enter__ = lambda s: s
        resp.__exit__ = lambda s, *a: False
        return resp


class IAFalsa:
    """Responde tipos para os ids recebidos; registra cada prompt."""

    def __init__(self, tipo="Outros", resposta=None):
        self.prompts = []
        self.tipo = tipo
        self.resposta = resposta

    def __call__(self, prompt):
        self.prompts.append(prompt)
        if self.resposta is not None:
            return self.resposta
        ids = re.findall(r'"id":\s*"(\d+)"', prompt)
        return json.dumps([{"id": i, "tipo": self.tipo} for i in ids])


HERMES_FALSO = r'''#!/usr/bin/env python3
import json, os, sys
f = os.environ["HERMES_FALSO_ESTADO"]
st = json.load(open(f)) if os.path.exists(f) else {"jobs": [], "log": []}
st["log"].append(sys.argv[1:])
a = sys.argv[1:]
if a[:2] == ["cron", "list"]:
    print("Scheduled Jobs\n")
    for j in st["jobs"]:
        print(f"  {j['id']} [active]\n    Name:      {j['name']}\n    Schedule:  {j['schedule']}")
        if j.get("skills"):
            print("    Skills:    " + ", ".join(j["skills"]))
        if j.get("script"):
            print("    Script:    " + j["script"])
        print()
elif a[:2] == ["cron", "create"]:
    j = {"id": "%012x" % (len(st["log"]) + 100), "schedule": a[2], "skills": [], "args": a[3:]}
    it = iter(a[3:])
    for x in it:
        if x == "--name": j["name"] = next(it)
        elif x == "--script": j["script"] = next(it)
        elif x == "--deliver": j["deliver"] = next(it)
        elif x == "--no-agent": j["no_agent"] = True
    st["jobs"].append(j)
    print("Created job " + j["id"])
elif a[:2] == ["cron", "remove"]:
    st["jobs"] = [j for j in st["jobs"] if j["id"] != a[2]]
elif a[:2] == ["cron", "edit"]:
    j = next(j for j in st["jobs"] if j["id"] == a[2])
    it = iter(a[3:])
    for x in it:
        if x == "--remove-skill":
            s = next(it)
            j["skills"] = [k for k in j["skills"] if k != s]
json.dump(st, open(f, "w"))
'''


class Caso(unittest.TestCase):
    """HOME temporário com as duas contas Gmail no config do Himalaya."""

    contas = (("trabalho", "trab@gmail.com"), ("pessoal", "pes@gmail.com"))

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        SERVIDORES.clear()
        ENVIADOS.clear()
        self.srv = {}
        cfg = []
        for nome, mail in self.contas:
            self.srv[nome] = SERVIDORES[("imap.gmail.com", mail)] = ServidorIMAP(mail, "senha-" + nome)
            cfg.append(textwrap.dedent(f'''
                [accounts.{nome}]
                email = "{mail}"
                imap.server = "imaps://imap.gmail.com:993"
                imap.sasl.plain.username = "{mail}"
                imap.sasl.plain.password.raw = "senha-{nome}"
                smtp.server = "smtps://smtp.gmail.com:465"
                smtp.sasl.plain.username = "{mail}"
                smtp.sasl.plain.password.raw = "senha-{nome}"
            '''))
        h = self.home / ".config/himalaya/config.toml"
        h.parent.mkdir(parents=True)
        h.write_text("".join(cfg))
        h.chmod(0o600)
        self.http = HTTPFalso()
        self.ia = IAFalsa()
        bindir = self.home / "bin"
        bindir.mkdir()
        hermes = bindir / "hermes"
        hermes.write_text(HERMES_FALSO)
        hermes.chmod(0o755)
        self.hermes_estado = self.home / "hermes.json"
        self.agora = AGORA
        env = {"HOME": str(self.home), "PATH": f"{bindir}:{os.environ['PATH']}",
               "HERMES_FALSO_ESTADO": str(self.hermes_estado)}
        self.patches = [
            mock.patch.dict(os.environ, env),
            mock.patch("imaplib.IMAP4_SSL", IMAPFalso),
            mock.patch("imaplib.IMAP4", IMAPFalso),
            mock.patch("smtplib.SMTP_SSL", SMTPFalso),
            mock.patch("smtplib.SMTP", SMTPFalso),
            mock.patch("urllib.request.urlopen", self.http),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def rodar(self, *argv, agora=None):
        """Roda o CLI em processo; devolve (código, stdout)."""
        from src import cli, ia
        saida = io.StringIO()
        with mock.patch.object(ia, "perguntar", self.ia), \
                mock.patch.object(cli, "agora", lambda: agora or self.agora), \
                contextlib.redirect_stdout(saida):
            codigo = cli.main(list(argv))
        return codigo, saida.getvalue()

    def pos_ensaio(self):
        """Roda o ensaio da véspera para que a próxima faxina seja real."""
        self.rodar("faxina", agora=self.agora - timedelta(days=1))

    def hermes_jobs(self):
        return json.loads(self.hermes_estado.read_text())["jobs"] if self.hermes_estado.exists() else []

    def hermes_inicial(self, jobs):
        self.hermes_estado.write_text(json.dumps({"jobs": jobs, "log": []}))

    def modo(self, caminho):
        return stat.S_IMODE(Path(caminho).stat().st_mode)


def utf7(s):
    """Decodifica UTF-7 modificado do IMAP (RFC 3501) — rótulos com acento."""
    import base64

    def dec(m):
        if m.group(1) == "":
            return "&"
        b = m.group(1).replace(",", "/")
        return base64.b64decode(b + "=" * (-len(b) % 4)).decode("utf-16-be")
    return re.sub(r"&([^-]*)-", dec, s)


def rotulos(m):
    return {utf7(l) for l in m.labels}


def na_caixa(srv, m):
    return m in srv.em("INBOX")


def na_lixeira(srv, m):
    return any(m in srv.em(p) for p, a in srv.pastas.items() if "\\Trash" in a)


ONE_CLICK = "List-Unsubscribe=One-Click"


def promo(srv, de="Shein <news@shein.com>", dias=40, one_click=None, **kw):
    cab = {"List-Unsubscribe": f"<https://{de.split('@')[1].rstrip('>')}/u?t=1>"}
    if one_click:
        cab["List-Unsubscribe-Post"] = ONE_CLICK
    return srv.add(de, "50% OFF em tudo, oferta relâmpago", dias=dias, cabecalhos=cab, **kw)


def comandos(srv, *nomes):
    return [c for c in srv.comandos if c[0] in nomes]
