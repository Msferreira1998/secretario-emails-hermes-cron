from datetime import timedelta

from apoio import Caso, comandos, na_caixa, na_lixeira, promo, rotulos
from src.imap import utf7


def antigo(srv, tipo, dias=70, de="News <n@revista.com>"):
    m = srv.add(de, f"{tipo} antigo", dias=dias)
    m.labels = {utf7(f"Secretário/{tipo}")}  # já rotulado e arquivado numa faxina anterior
    return m


class Limpeza(Caso):
    # SPECSFY: US-006 FR-013 AC-034
    def test_ac034_antigo_da_pessoal_vai_para_lixeira(self):
        self.rodar("limpeza", "pessoal", "60")
        p = antigo(self.srv["pessoal"], "Newsletters")
        t = antigo(self.srv["trabalho"], "Newsletters")
        novo = antigo(self.srv["pessoal"], "Newsletters", dias=10)
        self.pos_ensaio()
        self.rodar("faxina")
        self.assertTrue(na_lixeira(self.srv["pessoal"], p))
        self.assertFalse(na_lixeira(self.srv["trabalho"], t))
        self.assertFalse(na_lixeira(self.srv["pessoal"], novo))

    # SPECSFY: US-006 FR-013 FR-004 AC-035
    def test_ac035_pessoal_compras_financas_e_protegidos_ficam(self):
        self.rodar("limpeza", "pessoal", "60")
        self.rodar("protege", "amigos.com")
        p = self.srv["pessoal"]
        ficam = [antigo(p, tipo, dias=90) for tipo in ("Pessoal", "Compras", "Finanças", "Segurança", "Trabalho")]
        ficam.append(antigo(p, "Newsletters", dias=90, de="Clube <oi@amigos.com>"))
        ficam.append(antigo(p, "Promoções", dias=90, de="Eu <trab@gmail.com>"))
        ficam.append(antigo(p, "Notificações", dias=90, de="Nubank <news@nubank.com.br>"))
        ficam.append(antigo(p, "Outros", dias=90))  # dúvida da IA nunca vira ação destrutiva (NFR-001)
        sai = antigo(p, "Notificações", dias=90)
        self.pos_ensaio()
        self.rodar("faxina")
        self.assertEqual([m.assunto for m in ficam if na_lixeira(p, m)], [])
        self.assertTrue(na_lixeira(p, sai))

    # SPECSFY: US-006 FR-013 FR-008 AC-036
    def test_ac036_ligar_desligar_e_resumo(self):
        rc, saida = self.rodar("limpeza", "pessoal", "60")
        self.assertEqual(rc, 0)
        self.assertIn("60", saida)
        p = self.srv["pessoal"]
        antigo(p, "Notificações")
        antigo(p, "Promoções")
        self.pos_ensaio()
        _, resumo = self.rodar("faxina")
        self.assertIn("pessoal: 2 antigos na lixeira", resumo)
        self.rodar("limpeza", "pessoal", "desliga")
        depois = antigo(p, "Newsletters")
        self.rodar("faxina", agora=self.agora + timedelta(days=1))
        self.assertFalse(na_lixeira(p, depois))

    # SPECSFY: US-006 FR-013 FR-004 AC-035
    def test_ac035_remetente_com_acento_e_tratado_como_protegido(self):
        self.rodar("limpeza", "pessoal", "60")
        p = self.srv["pessoal"]
        m = antigo(p, "Newsletters", dias=90, de="Café <café@padaria.com>")
        self.pos_ensaio()
        _, saida = self.rodar("faxina")
        self.assertNotIn("falhou", saida)
        self.assertFalse(na_lixeira(p, m))

    # SPECSFY: US-006 FR-013 FR-004 AC-035
    def test_ac035_from_dobrado_em_duas_linhas_respeita_protecao(self):
        self.rodar("limpeza", "pessoal", "60")
        self.rodar("protege", "amigos.com")
        p = self.srv["pessoal"]
        m = antigo(p, "Newsletters", dias=90, de="Clube dos Amigos (Boletim Semanal)\r\n <oi@amigos.com>")
        self.pos_ensaio()
        self.rodar("faxina")
        self.assertFalse(na_lixeira(p, m))


class CaixaCurta(Caso):
    # SPECSFY: US-007 FR-014 FR-004 AC-037
    def test_ac037_rotulados_com_mais_de_3_dias_saem_da_caixa(self):
        t = self.srv["trabalho"]
        boleto = t.add("Banco Inter <cobranca@inter.co>", "Seu boleto vence amanhã", dias=4)
        recente = t.add("Ana <ana@amigos.com>", "Oi, tudo bem?", dias=1)
        self.pos_ensaio()
        self.rodar("faxina")
        self.assertFalse(na_caixa(t, boleto))
        self.assertIn("Secretário/Finanças", rotulos(boleto))
        self.assertNotIn("\\Seen", boleto.flags)
        self.assertTrue(na_caixa(t, recente))
        self.assertFalse(na_lixeira(t, boleto) or na_lixeira(t, recente))

    # SPECSFY: US-007 FR-002 FR-004 AC-038
    def test_ac038_promocoes_vao_para_lixeira_com_7_dias(self):
        sai, fica = [], []
        for srv in self.srv.values():
            sai += [(srv, promo(srv, de="Loja <oi@loja.com>", dias=8)),
                    (srv, antigo(srv, "Promoções", dias=10, de="Loja <oi@loja.com>"))]
            fica += [(srv, antigo(srv, "Promoções", dias=10, de="Inter <promo@comunicacao.inter.co>")),
                     (srv, promo(srv, de="Loja <oi@loja.com>", dias=5))]
        self.pos_ensaio()
        self.rodar("faxina")
        self.assertTrue(all(na_lixeira(s, m) for s, m in sai))
        self.assertEqual([m.assunto for s, m in fica if na_lixeira(s, m)], [])

    # SPECSFY: US-007 FR-015 FR-008 FR-004 AC-039
    def test_ac039_limpa_por_remetente(self):
        rc, saida = self.rodar("limpa", "sheinemail.com", "3")
        self.assertEqual(rc, 0)
        self.assertIn("sheinemail.com", saida)
        p = self.srv["pessoal"]
        shein = antigo(p, "Newsletters", dias=4, de="Shein <a@edm.br.sheinemail.com>")
        pedido = antigo(p, "Compras", dias=4, de="Shein <a@edm.br.sheinemail.com>")
        outro = antigo(p, "Newsletters", dias=4)
        self.pos_ensaio()
        _, resumo = self.rodar("faxina")
        self.assertTrue(na_lixeira(p, shein))
        self.assertFalse(na_lixeira(p, pedido) or na_lixeira(p, outro))
        self.assertIn("pessoal: 1 antigos na lixeira", resumo)
        self.rodar("limpa", "sheinemail.com", "desliga")
        depois = antigo(p, "Newsletters", dias=4, de="Shein <a@edm.br.sheinemail.com>")
        self.rodar("faxina", agora=self.agora + timedelta(days=1))
        self.assertFalse(na_lixeira(p, depois))

    # SPECSFY: US-007 FR-014 FR-015 FR-007 AC-040
    def test_ac040_ensaio_nao_arquiva_nem_apaga(self):
        self.rodar("limpa", "sheinemail.com", "3")
        p = self.srv["pessoal"]
        shein = antigo(p, "Newsletters", dias=4, de="Shein <a@edm.br.sheinemail.com>")
        boleto = p.add("Banco Inter <cobranca@inter.co>", "Seu boleto vence amanhã", dias=4)
        boleto.labels.add(utf7("Secretário/Finanças"))
        _, saida = self.rodar("faxina")
        self.assertEqual(comandos(p, "UID STORE", "UID COPY", "UID MOVE", "EXPUNGE"), [])
        self.assertTrue(na_caixa(p, boleto) and not na_lixeira(p, shein))
        self.assertIn("pessoal: 1 antigos iriam para lixeira", saida)

    # SPECSFY: US-007 FR-015 FR-004 AC-041
    def test_ac041_limpa_respeita_bancos_vetos_e_protegidos(self):
        self.rodar("limpa", "linkedin.com", "3")
        self.rodar("limpa", "inter.co", "3")
        self.rodar("veta", "messages-noreply@linkedin.com")
        p = self.srv["pessoal"]
        vetado = antigo(p, "Newsletters", dias=5, de="LinkedIn <messages-noreply@linkedin.com>")
        sai = antigo(p, "Newsletters", dias=5, de="LinkedIn <news@linkedin.com>")
        banco = antigo(p, "Promoções", dias=5, de="Inter <promo@comunicacao.inter.co>")
        self.pos_ensaio()
        self.rodar("faxina")
        self.assertTrue(na_lixeira(p, sai))
        self.assertFalse(na_lixeira(p, vetado) or na_lixeira(p, banco))
        rc, saida = self.rodar("limpa", "linkedin.com", "zero")
        self.assertEqual(rc, 2)
        self.assertIn("Uso: limpa", saida)

    # SPECSFY: US-007 FR-014 NFR-003 AC-042
    def test_ac042_arquivar_e_idempotente_e_so_rotulados(self):
        p = self.srv["pessoal"]
        rotulado = p.add("Ana <ana@amigos.com>", "Fotos da viagem", dias=5)
        sem = p.add("Bia <bia@amigos.com>", "Antigo sem rótulo", dias=5)
        self.pos_ensaio()
        self.rodar("faxina")
        sem.labels = {"\\Inbox"}  # como um e-mail que nunca passou pelo secretário
        self.rodar("faxina")
        moves = [c for c in comandos(p, "UID MOVE") if str(rotulado.uid) in c[2].split(",")]
        self.assertEqual(len(moves), 1)
        self.assertFalse(na_caixa(p, rotulado))
        self.assertTrue(na_caixa(p, sem))
