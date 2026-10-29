"""Contas: lidas do config do Himalaya (fonte única) e cadastradas a partir de um arquivo de credenciais."""
import imaplib
import json
import os
import smtplib
import tomllib
from pathlib import Path
from urllib.parse import urlsplit

from src import imap

# provedor: (imap host, porta, segurança, smtp host, porta, segurança)
PRESETS = {
    "gmail": ("imap.gmail.com", 993, "ssl", "smtp.gmail.com", 465, "ssl"),
    "outlook": ("outlook.office365.com", 993, "ssl", "smtp.office365.com", 587, "starttls"),
    "hotmail": ("outlook.office365.com", 993, "ssl", "smtp.office365.com", 587, "starttls"),
    "hostgator": ("imap.titan.email", 993, "ssl", "smtp.titan.email", 465, "ssl"),
    "titan": ("imap.titan.email", 993, "ssl", "smtp.titan.email", 465, "ssl"),
}
ESQUEMA = {("imap", "ssl"): "imaps", ("imap", "starttls"): "imap", ("smtp", "ssl"): "smtps", ("smtp", "starttls"): "smtp"}


def himalaya():
    return Path.home() / ".config/himalaya/config.toml"


def credenciais():
    return Path.home() / ".config/secretario-emails/contas.toml"


def _servidor(url):
    u = urlsplit(url)
    return u.hostname, u.port, "ssl" if u.scheme.endswith("s") else "starttls"


def listar():
    if not himalaya().exists():
        return []
    contas = []
    for nome, a in tomllib.loads(himalaya().read_text()).get("accounts", {}).items():
        ih, ip, iseg = _servidor(a["imap"]["server"])
        sh, sp, sseg = _servidor(a["smtp"]["server"])
        contas.append({
            "nome": nome, "email": a["email"],
            "imap": (ih, ip, iseg), "smtp": (sh, sp, sseg),
            "usuario": a["imap"]["sasl"]["plain"]["username"],
            "senha": a["imap"]["sasl"]["plain"]["password"]["raw"],
            "smtp_usuario": a["smtp"]["sasl"]["plain"]["username"],
            "smtp_senha": a["smtp"]["sasl"]["plain"]["password"]["raw"],
        })
    return contas


def smtp(conta):
    host, porta, seg = conta["smtp"]
    if seg == "ssl":
        s = smtplib.SMTP_SSL(host, porta, timeout=60)
    else:
        s = smtplib.SMTP(host, porta, timeout=60)
        s.starttls()
    s.login(conta["smtp_usuario"], conta["smtp_senha"])
    return s


def _microsoft(c):
    return c.get("provedor") in ("outlook", "hotmail") or c["email"].split("@")[-1] in (
        "outlook.com", "hotmail.com", "live.com", "msn.com")


def adicionar(nome):
    arquivo = credenciais()
    if not arquivo.exists():
        print(f"Crie {arquivo} (permissão 600) com a seção [{nome}]: provedor, email e senha.")
        return 1
    c = tomllib.loads(arquivo.read_text()).get(nome)
    if c is None:
        print(f"Não achei a seção [{nome}] em {arquivo}.")
        return 1
    if any(x["nome"] == nome for x in listar()):
        print(f"A conta {nome} já está cadastrada.")
        return 0
    p = PRESETS.get(c.get("provedor", ""), (None, 993, "ssl", None, 465, "ssl"))
    ih, ip, iseg = c.get("imap_servidor", p[0]), c.get("imap_porta", p[1]), c.get("imap_seguranca", p[2])
    sh, sp, sseg = c.get("smtp_servidor", p[3]), c.get("smtp_porta", p[4]), c.get("smtp_seguranca", p[5])
    if not ih or not sh:
        print("Provedor sem preset: informe imap_servidor e smtp_servidor (e portas/segurança).")
        return 1
    conta = {"nome": nome, "email": c["email"], "imap": (ih, ip, iseg), "smtp": (sh, sp, sseg),
             "usuario": c.get("usuario", c["email"]), "senha": c["senha"],
             "smtp_usuario": c.get("usuario", c["email"]), "smtp_senha": c["senha"]}
    try:
        imap.conectar(conta).logout()
        smtp(conta).quit()
    except (imaplib.IMAP4.error, smtplib.SMTPException, OSError) as e:
        print(f"Login recusado em {nome} ({type(e).__name__}). A conta não foi gravada.")
        if _microsoft(c):
            print("A Microsoft não aceita mais senha comum nem de aplicativo em IMAP para contas pessoais: "
                  "é preciso o login OAuth da Microsoft, que ainda não está disponível neste secretário.")
        else:
            print("Confira a senha (no Gmail, use uma senha de aplicativo) e se o IMAP está ligado no provedor.")
        return 1
    q = json.dumps
    bloco = (f"\n[accounts.{nome}]\ndefault = false\nemail = {q(c['email'])}\n"
             f"imap.server = {q(f'{ESQUEMA[('imap', iseg)]}://{ih}:{ip}')}\n"
             f"imap.sasl.plain.username = {q(conta['usuario'])}\n"
             f"imap.sasl.plain.password.raw = {q(c['senha'])}\n"
             f"smtp.server = {q(f'{ESQUEMA[('smtp', sseg)]}://{sh}:{sp}')}\n"
             f"smtp.sasl.plain.username = {q(conta['smtp_usuario'])}\n"
             f"smtp.sasl.plain.password.raw = {q(c['senha'])}\n")
    himalaya().parent.mkdir(parents=True, exist_ok=True)
    with open(himalaya(), "a") as f:
        f.write(bloco)
    os.chmod(himalaya(), 0o600)
    print(f"Conta {nome} ({c['email']}) cadastrada. Ela entra na próxima faxina.")
    return 0
