"""Estado em SQLite: último UID, regras, proteções, vetos, papéis, rascunhos e histórico."""
import os
import sqlite3
from datetime import timedelta
from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"


def caminho():
    return Path.home() / ".local/state/secretario-emails/secretario.db"


def abrir(arquivo=None):
    arquivo = Path(arquivo or caminho())
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    novo = not arquivo.exists()
    con = sqlite3.connect(arquivo)
    if novo:
        os.chmod(arquivo, 0o600)
    versao = con.execute("PRAGMA user_version").fetchone()[0]
    for n, sql in enumerate(sorted(MIGRATIONS.glob("*.sql")), 1):
        if n > versao:
            con.executescript(sql.read_text())
            con.execute(f"PRAGMA user_version = {n}")
    con.commit()
    return con


def casa(email, padrao):
    """`padrao` é um e-mail exato ou um domínio (vale para subdomínios)."""
    email, padrao = email.lower(), padrao.lower().lstrip("@")
    if "@" in padrao:
        return email == padrao
    dominio = email.rsplit("@", 1)[-1]
    return dominio == padrao or dominio.endswith("." + padrao)


def lista(con, tabela):
    return [r[0] for r in con.execute(f"SELECT remetente FROM {tabela}")]


def regras(con):
    return dict(con.execute("SELECT remetente, tipo FROM regras"))


def papeis(con):
    return {n: p for n, p in con.execute("SELECT nome, papel FROM contas WHERE papel IS NOT NULL")}


def ultimo_uid(con, conta):
    r = con.execute("SELECT ultimo_uid FROM contas WHERE nome = ?", (conta,)).fetchone()
    return r[0] if r else 0


def gravar_uid(con, conta, uid):
    con.execute("INSERT INTO contas(nome, ultimo_uid) VALUES (?, ?) "
                "ON CONFLICT(nome) DO UPDATE SET ultimo_uid = excluded.ultimo_uid", (conta, uid))


def registrar(con, agora, conta, remetente, acao, motivo=None):
    con.execute("INSERT INTO historico(quando, conta, remetente, acao, motivo) VALUES (?,?,?,?,?)",
                (agora.isoformat(), conta, remetente, acao, motivo))


def ja_ensaiou(con):
    return con.execute("SELECT 1 FROM execucoes LIMIT 1").fetchone() is not None


def limpar(con, agora):
    """Retenção: histórico, rascunhos, pendentes, lixeira e classificação 30 dias; lidos e pedidos 60; vencimentos 7 após."""
    limite = (agora - timedelta(days=30)).isoformat()
    con.execute("DELETE FROM historico WHERE quando < ?", (limite,))
    con.execute("DELETE FROM rascunhos WHERE criado_em < ?", (limite,))
    con.execute("DELETE FROM pendentes WHERE quando < ?", (limite,))
    con.execute("DELETE FROM vistos WHERE quando < ?", ((agora - timedelta(days=60)).isoformat(),))
    con.execute("DELETE FROM lixeira WHERE quando < ?", (limite,))
    con.execute("DELETE FROM classificados WHERE quando < ?", (limite,))
    con.execute("DELETE FROM vencimentos WHERE vence < ?", ((agora - timedelta(days=7)).date().isoformat(),))
    con.execute("DELETE FROM pedidos WHERE quando < ?", ((agora - timedelta(days=60)).isoformat(),))
