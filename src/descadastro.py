"""Descadastro só por One-Click (RFC 8058, POST HTTPS) ou mailto: do cabeçalho; nunca abre página."""
import re
import urllib.parse
import urllib.request
from email.message import EmailMessage

ONE_CLICK = "List-Unsubscribe=One-Click"


def opcoes(cabecalho):
    links = re.findall(r"<([^>]+)>", cabecalho)
    https = next((l for l in links if l.lower().startswith("https://")), None)
    mailto = next((l for l in links if l.lower().startswith("mailto:")), None)
    return https, mailto


def como(m):
    """'one-click', 'mailto' ou None (aí o usuário descadastra sozinho)."""
    https, mailto = opcoes(m["unsub"])
    if https and ONE_CLICK.lower() in m["unsub_post"].lower():
        return "one-click"
    if mailto:
        return "mailto"
    return None


def descadastrar(m, conta, abrir_smtp):
    """Devolve True quando o pedido foi aceito."""
    https, mailto = opcoes(m["unsub"])
    if como(m) == "one-click":
        # shortcut: urlopen segue redirecionamento; trocar por opener sem redirect se algum remetente abusar.
        req = urllib.request.Request(https, data=ONE_CLICK.encode(), method="POST",
                                     headers={"Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return 200 <= getattr(r, "status", 200) < 300
    endereco, _, query = mailto[len("mailto:"):].partition("?")
    assunto = re.search(r"subject=([^&]+)", query, re.I)
    msg = EmailMessage()
    msg["From"], msg["To"] = conta["email"], endereco
    msg["Subject"] = urllib.parse.unquote(assunto.group(1)) if assunto else "unsubscribe"
    msg.set_content("unsubscribe")
    with abrir_smtp(conta) as s:
        s.send_message(msg)
    return True
