import textwrap
from datetime import timedelta

from apoio import Caso, SERVIDORES, ServidorIMAP, comandos, promo

GENERICAS = {"INBOX": ("\\HasNoChildren",), "Deleted Items": ("\\HasNoChildren", "\\Trash"),
             "Sent Items": ("\\HasNoChildren", "\\Sent")}


class Contas(Caso):
    def credenciais(self, texto):
        f = self.home / ".config/secretario-emails/contas.toml"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(textwrap.dedent(texto))
        f.chmod(0o600)

    def config(self):
        return (self.home / ".config/himalaya/config.toml").read_text()

    # SPECSFY: US-005 FR-010 AC-020
    def test_ac020_conta_nova_entra_na_faxina(self):
        SERVIDORES[("imap.titan.email", "eu@meudominio.com.br")] = ServidorIMAP(
            "eu@meudominio.com.br", "s3nha", gmail=False, pastas=GENERICAS)
        self.credenciais('''
            [hostgator]
            provedor = "hostgator"
            email = "eu@meudominio.com.br"
            senha = "s3nha"
        ''')
        rc, saida = self.rodar("conta", "adicionar", "hostgator")
        self.assertEqual(rc, 0, saida)
        self.assertIn("[accounts.hostgator]", self.config())
        self.assertIn("imaps://imap.titan.email:993", self.config())
        self.assertEqual(self.modo(self.home / ".config/himalaya/config.toml"), 0o600)
        self.assertNotIn("s3nha", saida)
        _, faxina = self.rodar("faxina")
        self.assertIn("hostgator:", faxina)

    # SPECSFY: US-005 FR-010 NFR-003 NFR-001 AC-021
    def test_ac021_conta_com_falha_nao_para_as_outras(self):
        m = promo(self.srv["trabalho"], dias=40)
        self.pos_ensaio()
        self.srv["pessoal"].recusar = True
        rc, saida = self.rodar("faxina")
        self.assertIn(m, self.srv["trabalho"].em("[Gmail]/Lixeira"))
        self.assertIn("pessoal: login recusado", saida)
        self.assertNotIn("senha-pessoal", saida)

    # SPECSFY: US-005 FR-010 AC-022
    def test_ac022_microsoft_sem_senha_de_aplicativo(self):
        self.credenciais('''
            [hotmail]
            provedor = "outlook"
            email = "eu@outlook.com"
            senha = "normal"
        ''')
        rc, saida = self.rodar("conta", "adicionar", "hotmail")
        self.assertNotEqual(rc, 0)
        self.assertNotIn("hotmail", self.config())
        self.assertIn("OAuth", saida)

    # SPECSFY: US-005 FR-010 AC-033
    def test_ac033_conta_com_starttls_e_lixeira_por_atributo(self):
        srv = SERVIDORES[("imap.empresa.com", "eu@empresa.com")] = ServidorIMAP(
            "eu@empresa.com", "pw", gmail=False, pastas=GENERICAS, starttls=True)
        self.credenciais('''
            [empresa]
            provedor = "imap"
            email = "eu@empresa.com"
            senha = "pw"
            imap_servidor = "imap.empresa.com"
            imap_porta = 143
            imap_seguranca = "starttls"
            smtp_servidor = "smtp.empresa.com"
            smtp_porta = 587
            smtp_seguranca = "starttls"
        ''')
        rc, saida = self.rodar("conta", "adicionar", "empresa")
        self.assertEqual(rc, 0, saida)
        self.assertIn("imap://imap.empresa.com:143", self.config())
        self.assertIn(("LOGIN", "STARTTLS"), srv.comandos)
        m = promo(srv, dias=40)
        self.pos_ensaio()
        self.rodar("faxina")
        self.assertIn(m, srv.caixas["Deleted Items"])
