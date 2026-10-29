import re
import sqlite3
from datetime import timedelta

from apoio import Caso, ENVIADOS, IAFalsa


class Respostas(Caso):
    def preparar(self):
        self.joao = self.srv["trabalho"].add("João <joao@amigo.com>", "Reunião de terça?")
        self.ia = IAFalsa(tipo="Pessoal")
        self.pos_ensaio()
        _, saida = self.rodar("faxina")
        return re.search(r"\b(E\d+)\b[^\n]*João", saida).group(1)

    # SPECSFY: US-004 FR-009 NFR-001 AC-017
    def test_ac017_rascunho_nao_envia(self):
        codigo = self.preparar()
        rc, saida = self.rodar("responder", codigo, "Confirmo terça.")
        self.assertEqual(rc, 0)
        self.assertRegex(saida, r"\bR\d+\b")
        self.assertIn("Confirmo terça.", saida)
        self.assertEqual(ENVIADOS, [])

    # SPECSFY: US-004 FR-009 AC-018
    def test_ac018_envia_dispara_o_envio(self):
        codigo = self.preparar()
        _, saida = self.rodar("responder", codigo, "Confirmo terça.")
        r = re.search(r"\b(R\d+)\b", saida).group(1)
        rc, _ = self.rodar("envia", r)
        self.assertEqual(rc, 0)
        self.assertEqual(len(ENVIADOS), 1)
        host, de, para, msg = ENVIADOS[0]
        self.assertEqual((host, de), ("smtp.gmail.com", "trab@gmail.com"))
        self.assertIn("joao@amigo.com", para)
        self.assertEqual(msg["In-Reply-To"], f"<m{self.joao.uid}@teste>")
        self.assertTrue(msg["Subject"].startswith("Re: "))
        db = self.home / ".local/state/secretario-emails/secretario.db"
        acoes = [a for (a,) in sqlite3.connect(db).execute("SELECT acao FROM historico")]
        self.assertIn("enviado", acoes)

    # SPECSFY: US-004 FR-009 FR-012 AC-019
    def test_ac019_rascunho_esquecido_expira(self):
        codigo = self.preparar()
        _, saida = self.rodar("responder", codigo, "Confirmo.", agora=self.agora - timedelta(days=31))
        r = re.search(r"\b(R\d+)\b", saida).group(1)
        self.rodar("faxina")
        rc, saida = self.rodar("envia", r)
        self.assertIn("expirou", saida)
        self.assertEqual(ENVIADOS, [])
