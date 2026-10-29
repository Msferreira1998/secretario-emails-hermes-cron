import sqlite3
from datetime import timedelta

from apoio import Caso


class Estado(Caso):
    # SPECSFY: FR-012 AC-025
    def test_ac025_historico_de_30_dias(self):
        self.rodar("faxina")
        db = self.home / ".local/state/secretario-emails/secretario.db"
        self.assertEqual(self.modo(db), 0o600)
        con = sqlite3.connect(db)
        for dias, motivo in ((31, "velho"), (29, "novo")):
            con.execute("INSERT INTO historico(quando, conta, remetente, acao, motivo) VALUES (?,?,?,?,?)",
                        ((self.agora - timedelta(days=dias)).isoformat(), "trabalho", "x@y.com", "apagado", motivo))
        con.commit()
        self.rodar("faxina")
        motivos = {m for (m,) in sqlite3.connect(db).execute("SELECT motivo FROM historico")}
        self.assertIn("novo", motivos)
        self.assertNotIn("velho", motivos)
