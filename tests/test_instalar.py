import os

from apoio import Caso

TRIAGEM = {"id": "5b6dc84a405f", "name": "Triagem de e-mails", "schedule": "0 8 * * 1-5",
           "skills": ["himalaya", "email-inbox-triage"]}
REVISAO = {"id": "61db4f6c9839", "name": "Revisão semanal", "schedule": "15 8 * * 1",
           "skills": ["weekly-review-planning", "himalaya"]}


class Instalar(Caso):
    def secretarios(self):
        return [j for j in self.hermes_jobs() if j.get("name") == "Secretário de e-mails"]

    # SPECSFY: US-005 FR-011 AC-023
    def test_ac023_triagem_antiga_substituida(self):
        self.hermes_inicial([TRIAGEM, REVISAO])
        rc, saida = self.rodar("instalar")
        self.assertEqual(rc, 0, saida)
        nomes = [j["name"] for j in self.hermes_jobs()]
        self.assertNotIn("Triagem de e-mails", nomes)
        rev = next(j for j in self.hermes_jobs() if j["name"] == "Revisão semanal")
        self.assertEqual(rev["skills"], ["weekly-review-planning"])

    # SPECSFY: FR-005 FR-011 NFR-003 AC-024
    def test_ac024_cron_0730_sem_agente(self):
        self.hermes_inicial([])
        self.rodar("instalar")
        [j] = self.secretarios()
        self.assertEqual(j["schedule"], "30 7 * * *")
        self.assertTrue(j.get("no_agent"))
        self.assertEqual(j.get("deliver"), "telegram")
        self.assertEqual(j.get("script"), "secretario.sh")
        script = self.home / ".hermes/scripts/secretario.sh"
        self.assertTrue(os.access(script, os.X_OK))
        self.assertTrue((self.home / ".hermes/skills/productivity/secretario-emails/SKILL.md").exists())

    # SPECSFY: FR-011 AC-030
    def test_ac030_instalacao_idempotente(self):
        self.hermes_inicial([TRIAGEM, REVISAO])
        self.rodar("instalar")
        rc, saida = self.rodar("instalar")
        self.assertEqual(rc, 0, saida)
        self.assertEqual(len(self.secretarios()), 1)
