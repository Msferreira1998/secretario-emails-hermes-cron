"""IMAP: conexão, busca de novos por UID e ações (rótulo, arquivar, lido, lixeira).

Nunca faz EXPUNGE fora da caixa de origem nem esvazia a lixeira (PR-002, NFR-001).
"""
import base64
import email
import email.policy
import email.utils
import imaplib
import re
import ssl
import time
from datetime import datetime

LOTE = 500


def conectar(conta):
    host, porta, seg = conta["imap"]
    if seg == "ssl":
        M = imaplib.IMAP4_SSL(host, porta, timeout=60)
    else:
        M = imaplib.IMAP4(host, porta, timeout=60)
        M.starttls(ssl_context=ssl.create_default_context())
    M.login(conta["usuario"], conta["senha"])
    return M


def utf7(texto):
    """Codifica nome de pasta/rótulo em UTF-7 modificado (RFC 3501)."""
    saida, buf = [], []

    def esvaziar():
        if buf:
            b = base64.b64encode("".join(buf).encode("utf-16-be")).decode().rstrip("=").replace("/", ",")
            saida.append(f"&{b}-")
            buf.clear()
    for ch in texto:
        if 0x20 <= ord(ch) <= 0x7E:
            esvaziar()
            saida.append("&-" if ch == "&" else ch)
        else:
            buf.append(ch)
    esvaziar()
    return "".join(saida)


def _q(nome):
    return '"' + utf7(nome).replace("\\", "\\\\").replace('"', '\\"') + '"'


class Caixa:
    def __init__(self, conta):
        self.M = conectar(conta)
        self.gmail = b"X-GM-EXT-1" in b" ".join(self.M.capability()[1])
        self.move = b"MOVE" in b" ".join(self.M.capability()[1])
        self.especiais, self.sep = {}, "/"
        for linha in self.M.list()[1]:
            m = re.match(rb'\((.*?)\) (NIL|"(?:[^"\\]|\\.)*") (.*)$', linha or b"")
            if not m:
                continue
            nome = m.group(3).decode().strip('"')
            if m.group(2) != b"NIL":
                self.sep = m.group(2).decode().strip('"')
            for attr in ("\\Trash", "\\Sent", "\\All"):
                if attr.encode() in m.group(1):
                    self.especiais[attr] = nome
        self.criadas = set()

    def sair(self):
        try:
            self.M.logout()
        except Exception:
            pass

    # ---- leitura
    def novos(self, desde_uid, so_leitura):
        self.M.select("INBOX", readonly=so_leitura)
        crit = ("UID", f"{desde_uid + 1}:*") if desde_uid else ("ALL",)
        uids = [int(u) for u in self.M.uid("SEARCH", None, *crit)[1][0].split()]
        uids = [u for u in uids if u > desde_uid]  # "n:*" sempre devolve a última mensagem
        msgs = []
        for i in range(0, len(uids), LOTE):
            lote = ",".join(map(str, uids[i:i + LOTE]))
            dados = self.M.uid("FETCH", lote, "(UID FLAGS INTERNALDATE BODY.PEEK[HEADER] BODY.PEEK[TEXT]<0.2000>)")[1]
            msgs += _parse_fetch(dados)
        return msgs

    def ja_escreveu_para(self, endereco):
        pasta = self.especiais.get("\\Sent")
        if not pasta:
            return False
        if not endereco.isascii() or '"' in endereco:
            return True  # não dá para buscar no IMAP sem UTF-8; na dúvida, protege
        self.M.select(_q(pasta), readonly=True)
        return bool(self.M.uid("SEARCH", None, "TO", f'"{endereco}"')[1][0].split())

    def selecionar_inbox(self, so_leitura):
        self.M.select("INBOX", readonly=so_leitura)

    # ---- ações (sempre na INBOX selecionada para escrita)
    def _uids(self, uids):
        return ",".join(map(str, sorted(uids)))

    def rotular(self, uids, rotulo):
        if uids and self.gmail:
            self.M.uid("STORE", self._uids(uids), "+X-GM-LABELS", f"({_q(rotulo)})")

    def marcar_lido(self, uids):
        if uids:
            self.M.uid("STORE", self._uids(uids), "+FLAGS", "(\\Seen)")

    def arquivar(self, uids, rotulo):
        if not uids:
            return
        if self.gmail:
            self._mover(uids, self.especiais["\\All"])  # no Gmail, arquivar = mover para Todos os e-mails
        else:
            pasta = rotulo.replace("/", self.sep)
            if pasta not in self.criadas:
                self.M.create(_q(pasta))  # já existir não é erro que importe
                self.criadas.add(pasta)
            self._mover(uids, pasta)

    def lixeira(self, uids):
        """Devolve False quando a conta não tem lixeira (aí o e-mail só é arquivado)."""
        if not uids:
            return True
        if self.gmail:
            self.M.uid("STORE", self._uids(uids), "+X-GM-LABELS", "(\\Trash)")
            return True
        pasta = self.especiais.get("\\Trash")
        if not pasta:
            return False
        self._mover(uids, pasta)
        return True

    def buscar(self, consulta, pasta="\\All"):
        """UIDs da busca do Gmail (X-GM-RAW) na pasta especial ou na INBOX, só leitura."""
        self.M.select(_q(self.especiais[pasta]) if pasta in self.especiais else pasta, readonly=True)
        self.M.literal = consulta.encode()
        return self.M.uid("SEARCH", "CHARSET", "UTF-8", "X-GM-RAW")[1][0].split()

    def cabecalhos(self, uids):
        """De, nome, assunto, data e Message-ID dos UIDs da pasta selecionada, sem marcar como lido."""
        achados = []
        for i in range(0, len(uids), LOTE):
            lote = b",".join(u if isinstance(u, bytes) else str(u).encode() for u in uids[i:i + LOTE]).decode()
            dados = self.M.uid("FETCH", lote, "(UID BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE MESSAGE-ID)])")[1]
            uid = None
            for item in dados:
                if not isinstance(item, tuple):
                    continue
                achou = re.search(rb"UID (\d+)", item[0])
                uid = int(achou.group(1)) if achou else uid
                h = email.message_from_bytes(item[1], policy=email.policy.default)
                if uid is None or not h.get("From"):  # o parser junta o From dobrado em várias linhas
                    continue
                nome, de = email.utils.parseaddr(str(h.get("From")))
                try:
                    data = email.utils.parsedate_to_datetime(str(h.get("Date")))
                except (TypeError, ValueError):
                    data = None
                achados.append({"uid": uid, "de": de.lower(), "nome": nome, "assunto": str(h.get("Subject", "")),
                                "data": data, "msgid": str(h.get("Message-ID", ""))})
        return achados

    def antigos(self, tipos, dias, de=None):
        """E-mails rotulados pelo secretário com esses tipos e mais velhos que `dias`, fora da lixeira (só de `de`, se dado)."""
        if not self.gmail or "\\All" not in self.especiais:
            return []  # shortcut: só Gmail (busca por rótulo); IMAP genérico exigiria varrer as pastas Secretário/*
        achados = []
        filtro = f" from:{de}" if de else ""  # pré-filtro do Gmail; quem chama confere o remetente exato
        for tipo in tipos:
            uids = self.buscar(f"label:Secretário/{tipo}{filtro} older_than:{dias}d")
            achados += [dict(m, tipo=tipo) for m in self.cabecalhos(uids)]
        return achados

    def recentes(self, tipo, dias):
        """Rotulados com o tipo nos últimos `dias` (Gmail), com cabeçalhos."""
        if not self.gmail or "\\All" not in self.especiais:
            return []
        return [dict(m, tipo=tipo) for m in self.cabecalhos(self.buscar(f"label:Secretário/{tipo} newer_than:{dias}d"))]

    def restaurar(self, msgids):
        """Tira da lixeira de volta para a INBOX os e-mails com esses Message-IDs; devolve os restaurados."""
        pasta = self.especiais.get("\\Trash")
        if not pasta or not msgids:
            return []
        self.M.select(_q(pasta))
        uids = self.M.uid("SEARCH", None, "ALL")[1][0].split()
        volta = [m for m in self.cabecalhos(uids) if m["msgid"] in msgids]
        if volta:
            self.M.uid("MOVE", self._uids(m["uid"] for m in volta), "INBOX")  # visto no Gmail real em 2026-10-28
        return volta

    def maior_uid(self):
        self.M.select("INBOX", readonly=True)
        uids = self.M.uid("SEARCH", None, "ALL")[1][0].split()
        return max(map(int, uids), default=0)

    def lixeira_em_todos(self, uids):
        """Lixeira para UIDs da pasta Todos os e-mails devolvidos por `antigos` (Gmail)."""
        if uids:
            self.M.select(_q(self.especiais["\\All"]))  # a checagem de enviados troca a pasta selecionada
            self.M.uid("STORE", self._uids(uids), "+X-GM-LABELS", "(\\Trash)")

    def tirar_da_caixa(self, tipos, dias, ensaio):
        """Rotulados com mais de `dias` saem da INBOX; rótulo e lido ficam como estão (Gmail). Devolve quantos."""
        if not self.gmail or "\\All" not in self.especiais:
            return 0  # shortcut: só Gmail; no IMAP genérico o secretário já move para as pastas Secretário/*
        self.M.select("INBOX", readonly=ensaio)
        uids = set()
        for tipo in tipos:  # com a INBOX aberta, o X-GM-RAW só acha o que está nela (visto em 2026-10-28)
            self.M.literal = f"label:Secretário/{tipo} -label:Secretário/Suspeito older_than:{dias}d".encode()
            uids |= {int(u) for u in self.M.uid("SEARCH", "CHARSET", "UTF-8", "X-GM-RAW")[1][0].split()}
        if uids and not ensaio:
            self._mover(uids, self.especiais["\\All"])
        return len(uids)

    def _mover(self, uids, pasta):
        if self.move:
            self.M.uid("MOVE", self._uids(uids), _q(pasta))
        else:
            self.M.uid("COPY", self._uids(uids), _q(pasta))
            self.M.uid("STORE", self._uids(uids), "+FLAGS", "(\\Deleted)")
            self.M.expunge()  # na INBOX selecionada, nunca na lixeira


def _texto(raw):
    # shortcut: trecho cru do corpo, sem decodificar MIME; basta para a IA decidir o tipo.
    t = raw.decode("utf-8", "ignore")
    t = "\n".join(l for l in t.splitlines() if not l.startswith(("--", "Content-")))
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _parse_fetch(dados):
    # O servidor escolhe a ordem das partes (o Gmail manda o TEXT antes do HEADER).
    brutos = []
    for item in dados:
        if not isinstance(item, tuple):
            continue
        pre = item[0].decode("utf-8", "ignore")
        if re.match(r"\d+ \(", pre):
            brutos.append({"pre": item[0], "uid": int(re.search(r"UID (\d+)", pre).group(1)),
                           "flags": (re.search(r"FLAGS \(([^)]*)\)", pre) or [None, ""])[1]})
        if not brutos:
            continue
        if "BODY[HEADER]" in pre:
            brutos[-1]["header"] = item[1]
        elif "BODY[TEXT]" in pre:
            brutos[-1]["texto"] = item[1]
    return [_mensagem(b) for b in brutos if "header" in b]


def _mensagem(b):
    h = email.message_from_bytes(b["header"], policy=email.policy.default)
    nome, end = email.utils.parseaddr(str(h.get("From", "")))
    try:
        data = email.utils.parsedate_to_datetime(str(h.get("Date")))
    except (TypeError, ValueError):
        data = None
    if data is None or data.tzinfo is None:
        t = imaplib.Internaldate2tuple(b["pre"])
        data = datetime.fromtimestamp(time.mktime(t)).astimezone() if t else datetime.now().astimezone()
    return {
        "uid": b["uid"], "de": end.lower(), "nome": nome, "assunto": str(h.get("Subject", "")),
        "data": data, "lido": "\\Seen" in b["flags"],
        "msgid": str(h.get("Message-ID", "")), "texto": _texto(b.get("texto", b"")),
        "unsub": str(h.get("List-Unsubscribe", "")),
        "unsub_post": str(h.get("List-Unsubscribe-Post", "")),
        "lista": bool(h.get("List-Id")) or str(h.get("Precedence", "")).lower() in ("bulk", "list"),
    }
