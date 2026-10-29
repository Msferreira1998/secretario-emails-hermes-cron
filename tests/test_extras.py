from datetime import timedelta

from apoio import AGORA, Caso, comandos, na_caixa, na_lixeira, promo, rotulos
from src.imap import utf7

AMANHA = AGORA + timedelta(days=1)


def rotulado(srv, tipo, assunto, dias=2, de="Google <no-reply@accounts.google.com>"):
    m = srv.add(de, assunto, dias=dias)
    m.labels = {utf7(f"Secretário/{tipo}")}  # já rotulado e arquivado numa faxina anterior
    return m


def trocar(m, de, para, tirar=True):
    if tirar:
        m.labels.discard(utf7(f"Secretário/{de}"))
    m.labels.add(utf7(f"Secretário/{para}"))


class Vencimentos(Caso):
    # SPECSFY: US-008 FR-016 FR-005 AC-043
    def test_ac043_boleto_vence_amanha(self):
        self.srv["trabalho"].add("Banco Inter <cobranca@inter.co>", f"Seu boleto vence em {AMANHA:%d/%m}")
        self.pos_ensaio()
        _, saida = self.rodar("faxina")
        bloco = saida.split("💸 Vence amanhã", 1)[1]
        self.assertIn("boleto", bloco.splitlines()[1])

    # SPECSFY: US-008 FR-016 AC-044
    def test_ac044_vence_hoje_e_depois_some(self):
        t = self.srv["trabalho"]
        t.add("Banco Inter <cobranca@inter.co>", f"Seu boleto vence em {AGORA:%d/%m}")
        t.add("Nubank <todomundo@nubank.com.br>", "Fatura disponível", texto=f"Pague até o vencimento: {AGORA:%d/%m/%Y}")
        self.pos_ensaio()
        _, hoje = self.rodar("faxina")
        bloco = hoje.split("💸 Vence hoje", 1)[1]
        self.assertIn("boleto", bloco)
        self.assertIn("Fatura disponível", bloco)
        _, depois = self.rodar("faxina", agora=AMANHA)
        self.assertNotIn("💸", depois)

    # SPECSFY: US-008 FR-016 NFR-001 AC-045
    def test_ac045_so_financas_vira_vencimento(self):
        self.rodar("regra", "loja.com", "Promoções")
        t = self.srv["trabalho"]
        t.add("Loja <oi@loja.com>", f"Oferta vence em {AMANHA:%d/%m}")
        t.add("Banco Inter <cobranca@inter.co>", "Seu boleto chegou")
        self.pos_ensaio()
        _, saida = self.rodar("faxina")
        self.assertNotIn("💸", saida)


class Codigos(Caso):
    # SPECSFY: US-008 FR-017 FR-004 AC-046
    def test_ac046_codigo_vai_para_lixeira_em_1_dia(self):
        t = self.srv["trabalho"]
        codigo = rotulado(t, "Segurança", "Seu código de verificação é 123456")
        alerta = rotulado(t, "Segurança", "Alerta de segurança: novo login")
        self.pos_ensaio()
        self.rodar("faxina")
        self.assertTrue(na_lixeira(t, codigo))
        self.assertFalse(na_lixeira(t, alerta))

    # SPECSFY: US-008 FR-017 FR-004 AC-047
    def test_ac047_codigo_recente_e_protegido_ficam(self):
        self.rodar("protege", "banco.com")
        t = self.srv["trabalho"]
        hoje = rotulado(t, "Segurança", "Seu código de verificação é 123456", dias=0)
        protegido = rotulado(t, "Notificações", "Seu código de acesso: 9876", de="Banco <app@banco.com>")
        self.pos_ensaio()
        self.rodar("faxina")
        self.assertFalse(na_lixeira(t, hoje) or na_lixeira(t, protegido))

    # SPECSFY: US-008 FR-017 FR-007 AC-048
    def test_ac048_codigo_no_ensaio(self):
        t = self.srv["trabalho"]
        codigo = rotulado(t, "Segurança", "Your verification code is 554433")
        _, saida = self.rodar("faxina")
        self.assertEqual(comandos(t, "UID STORE", "UID COPY", "UID MOVE", "EXPUNGE"), [])
        self.assertFalse(na_lixeira(t, codigo))
        self.assertIn("trabalho: 1 antigos iriam para lixeira", saida)


class Recorrentes(Caso):
    DIA1 = AGORA.replace(day=1)

    def recibos(self, dias):
        p = self.srv["pessoal"]
        for d in dias:
            rotulado(p, "Finanças", "Seu recibo do Spotify Premium", dias=d, de="Spotify <no-reply@spotify.com>")
        rotulado(p, "Compras", "Recibo da sua compra", dias=10, de="Loja <oi@lojaavulsa.com>")

    # SPECSFY: US-008 FR-018 FR-005 AC-049
    def test_ac049_recorrentes_no_dia_1(self):
        self.recibos([10, 40, 70])
        self.pos_ensaio()
        _, saida = self.rodar("faxina", agora=self.DIA1)
        bloco = saida.split("🔁 Cobranças recorrentes", 1)[1]
        self.assertIn("spotify.com", bloco)
        self.assertNotIn("lojaavulsa.com", bloco)

    # SPECSFY: US-008 FR-018 AC-050
    def test_ac050_recorrentes_so_no_dia_1(self):
        self.recibos([10, 40, 70])
        self.pos_ensaio()
        _, saida = self.rodar("faxina", agora=self.DIA1 + timedelta(days=1))
        self.assertNotIn("🔁", saida)

    # SPECSFY: US-008 FR-018 AC-051
    def test_ac051_sem_recorrentes_sem_secao(self):
        self.recibos([10])
        self.pos_ensaio()
        _, saida = self.rodar("faxina", agora=self.DIA1)
        self.assertNotIn("🔁", saida)


class Desfaz(Caso):
    # SPECSFY: US-009 FR-019 FR-008 AC-052
    def test_ac052_desfaz_devolve_a_lixeira(self):
        t = self.srv["trabalho"]
        msgs = [promo(t, de="Loja <oi@loja.com>", dias=40), promo(t, de="Outra <oi@outra.com>", dias=40)]
        self.pos_ensaio()
        self.rodar("faxina")
        self.assertTrue(all(na_lixeira(t, m) for m in msgs))
        rc, saida = self.rodar("desfaz")
        self.assertEqual(rc, 0)
        self.assertTrue(all(na_caixa(t, m) for m in msgs))
        self.assertIn("2", saida)
        self.assertIn("oi@loja.com", saida)
        self.assertIn("protege", saida)

    # SPECSFY: US-009 FR-019 FR-003 FR-004 AC-053
    def test_ac053_restaurado_nao_e_apagado_de_novo(self):
        t = self.srv["trabalho"]
        msgs = [promo(t, de="Loja <oi@loja.com>", dias=40 + i, one_click=True) for i in range(2)]
        self.pos_ensaio()
        self.rodar("faxina")
        self.rodar("desfaz")
        self.rodar("faxina", agora=AMANHA)
        self.assertFalse(any(na_lixeira(t, m) for m in msgs))
        self.assertTrue(all("Secretário/Promoções" in rotulos(m) for m in msgs))
        self.assertEqual(self.http.pedidos, [])

    # SPECSFY: US-009 FR-019 AC-054
    def test_ac054_nada_para_desfazer(self):
        t = self.srv["trabalho"]
        apagado = t.add("Fulano <f@x.com>", "apaguei eu mesmo")
        apagado.labels = {"\\Trash"}
        self.pos_ensaio()
        self.rodar("faxina")
        _, saida = self.rodar("desfaz")
        self.assertIn("Nada para desfazer", saida)
        self.assertTrue(na_lixeira(t, apagado))


class Busca(Caso):
    def faturas(self):
        for i in range(12):
            srv = self.srv["trabalho" if i % 2 else "pessoal"]
            srv.add(f"Loja {i} <l{i}@loja.com>", f"Sua fatura {i:02d}", dias=i)

    # SPECSFY: US-009 FR-020 FR-008 AC-055
    def test_ac055_busca_nas_duas_contas(self):
        self.faturas()
        rc, saida = self.rodar("busca", "fatura")
        self.assertEqual(rc, 0)
        linhas = [l for l in saida.splitlines() if "fatura" in l]
        self.assertEqual(len(linhas), 10)
        self.assertIn("fatura 00", linhas[0])
        self.assertIn("pessoal", linhas[0])
        self.assertIn("trabalho", linhas[1])
        self.assertIn("fatura 09", linhas[-1])

    # SPECSFY: US-009 FR-020 AC-056
    def test_ac056_busca_sem_resultado(self):
        self.faturas()
        _, saida = self.rodar("busca", "xyzzy")
        self.assertIn("Nada encontrado para xyzzy", saida)

    # SPECSFY: US-009 FR-020 NFR-001 AC-057
    def test_ac057_busca_nao_altera_nada(self):
        self.faturas()
        self.rodar("busca", "fatura")
        rc, saida = self.rodar("busca")
        self.assertEqual(rc, 2)
        self.assertIn("busca", saida)
        for srv in self.srv.values():
            self.assertEqual(comandos(srv, "UID STORE", "UID COPY", "UID MOVE", "EXPUNGE"), [])


class Alerta(Caso):
    # SPECSFY: US-009 FR-021 AC-058
    def test_ac058_alerta_de_seguranca_na_hora(self):
        self.rodar("alerta")
        self.srv["trabalho"].add("Google <no-reply@accounts.google.com>", "Alerta de segurança: novo login")
        rc, saida = self.rodar("alerta")
        self.assertEqual(rc, 0)
        self.assertIn("🚨", saida)
        self.assertIn("trabalho", saida)
        self.assertIn("novo login", saida)
        _, de_novo = self.rodar("alerta")
        self.assertEqual(de_novo.strip(), "")

    # SPECSFY: US-009 FR-021 NFR-001 NFR-003 AC-059
    def test_ac059_alerta_silencioso_e_so_leitura(self):
        p = self.srv["pessoal"]
        for i in range(5):
            p.add(f"Pessoa {i} <p{i}@x.com>", f"Oi {i}", dias=i)
        _, primeira = self.rodar("alerta")
        comum = p.add("Ana <ana@amigos.com>", "Almoço amanhã?")
        _, segunda = self.rodar("alerta")
        self.assertEqual(primeira.strip() + segunda.strip(), "")
        for srv in self.srv.values():
            self.assertEqual(comandos(srv, "UID STORE", "UID COPY", "UID MOVE", "EXPUNGE"), [])
        self.pos_ensaio()
        self.rodar("faxina")
        self.assertTrue(any(r.startswith("Secretário/") for r in rotulos(comum)))

    # SPECSFY: US-009 FR-021 FR-008 FR-011 AC-060
    def test_ac060_vip_e_instalacao(self):
        rc, saida = self.rodar("vip", "chefe@empresa.com")
        self.assertEqual(rc, 0)
        self.rodar("alerta")
        self.srv["trabalho"].add("Chefe <chefe@empresa.com>", "Preciso de você agora")
        _, alerta = self.rodar("alerta")
        self.assertIn("⭐", alerta)
        self.assertIn("Preciso de você agora", alerta)
        self.hermes_inicial([])
        self.rodar("instalar")
        self.rodar("instalar")
        jobs = [j for j in self.hermes_jobs() if j.get("name") == "Alerta de e-mails"]
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["schedule"], "*/15 * * * *")
        self.assertTrue(jobs[0].get("no_agent"))
        self.assertTrue((self.home / ".hermes/scripts" / jobs[0]["script"]).exists())


class Aprende(Caso):
    def loja(self, srv, assunto="50% OFF só hoje"):
        return srv.add("Loja <loja@lojinha.com>", assunto, dias=1,
                       cabecalhos={"List-Unsubscribe": "<https://lojinha.com/u>"})

    # SPECSFY: US-010 FR-022 FR-001 AC-061
    def test_ac061_aprende_com_troca_de_marcador(self):
        p = self.srv["pessoal"]
        m = self.loja(p)
        self.pos_ensaio()
        self.rodar("faxina")
        self.assertIn("Secretário/Promoções", rotulos(m))
        trocar(m, "Promoções", "Pessoal")
        novo = self.loja(p, "Mais 30% OFF")
        _, saida = self.rodar("faxina", agora=AMANHA)
        self.assertIn("🧠 Aprendi", saida)
        self.assertIn("loja@lojinha.com", saida)
        self.assertIn("Secretário/Pessoal", rotulos(novo))

    # SPECSFY: US-010 FR-022 AC-062
    def test_ac062_sem_troca_sem_regra(self):
        self.loja(self.srv["pessoal"])
        self.pos_ensaio()
        self.rodar("faxina")
        _, saida = self.rodar("faxina", agora=AMANHA)
        self.assertNotIn("🧠", saida)

    # SPECSFY: US-010 FR-022 AC-063
    def test_ac063_marcador_duplo_nao_vira_regra(self):
        p = self.srv["pessoal"]
        m = self.loja(p)
        self.pos_ensaio()
        self.rodar("faxina")
        trocar(m, "Promoções", "Pessoal", tirar=False)
        novo = self.loja(p, "Mais 30% OFF")
        _, saida = self.rodar("faxina", agora=AMANHA)
        self.assertNotIn("🧠", saida)
        self.assertIn("Secretário/Promoções", rotulos(novo))


class Golpe(Caso):
    # SPECSFY: US-010 FR-023 FR-005 AC-064
    def test_ac064_possivel_golpe(self):
        t = self.srv["trabalho"]
        m = t.add("Nubank <alerta@nubank-seguro.xyz>", "Sua conta foi bloqueada")
        self.pos_ensaio()
        _, saida = self.rodar("faxina")
        self.assertIn("Secretário/Suspeito", rotulos(m))
        self.assertTrue(na_caixa(t, m))
        self.assertNotIn("\\Seen", m.flags)
        bloco = saida.split("⚠️ Possível golpe", 1)[1]
        self.assertIn("nubank-seguro.xyz", bloco)

    # SPECSFY: US-010 FR-023 AC-065
    def test_ac065_banco_de_verdade_nao_e_golpe(self):
        t = self.srv["trabalho"]
        m = t.add("Nubank <todomundo@nubank.com.br>", "Sua fatura fechou")
        self.pos_ensaio()
        _, saida = self.rodar("faxina")
        self.assertNotIn("Secretário/Suspeito", rotulos(m))
        self.assertNotIn("Possível golpe", saida)

    # SPECSFY: US-010 FR-023 NFR-001 AC-066
    def test_ac066_suspeito_nunca_apagado_nem_descadastrado(self):
        t = self.srv["trabalho"]
        msgs = [promo(t, de="Banco do Brasil <promo@bb-ofertas.top>", dias=40 + i, one_click=True) for i in range(4)]
        self.pos_ensaio()
        self.rodar("faxina")
        self.assertFalse(any(na_lixeira(t, m) for m in msgs))
        self.assertTrue(all(na_caixa(t, m) for m in msgs))
        self.assertEqual(self.http.pedidos, [])


class Pedidos(Caso):
    PEDIDO = "8207320391722152"

    # SPECSFY: US-010 FR-024 FR-005 AC-067
    def test_ac067_pedido_a_caminho(self):
        self.srv["pessoal"].add("AliExpress <transaction@notice.aliexpress.com>",
                                f"1 pedido(s) confirmado(s): {self.PEDIDO}")
        self.pos_ensaio()
        _, saida = self.rodar("faxina")
        bloco = saida.split("📦 A caminho", 1)[1]
        self.assertIn(self.PEDIDO, bloco)

    # SPECSFY: US-010 FR-024 AC-068
    def test_ac068_entregue_sai_da_lista(self):
        p = self.srv["pessoal"]
        p.add("AliExpress <transaction@notice.aliexpress.com>", f"1 pedido(s) confirmado(s): {self.PEDIDO}", dias=5)
        self.pos_ensaio()
        self.rodar("faxina")
        p.add("AliExpress <transaction@notice.aliexpress.com>", f"Seu pedido {self.PEDIDO} foi entregue")
        _, saida = self.rodar("faxina", agora=AMANHA)
        self.assertNotIn(self.PEDIDO, saida)

    # SPECSFY: US-010 FR-024 AC-069
    def test_ac069_pedido_parado_e_nao_compra(self):
        self.rodar("regra", "news.com", "Newsletters")
        p = self.srv["pessoal"]
        p.add("Loja <pedidos@loja.com>", "Pedido 555555 confirmado", dias=61)
        p.add("News <n@news.com>", "Seu pedido 123456 de leitura chegou")
        self.pos_ensaio()
        _, saida = self.rodar("faxina")
        self.assertNotIn("555555", saida)
        self.assertNotIn("123456", saida)
