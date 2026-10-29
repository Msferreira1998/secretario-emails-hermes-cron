from apoio import Caso, SEGUNDA, promo, rotulos


def compra(srv):
    return srv.add("Mercado Livre <pedidos@mercadolivre.com>", "Seu pedido foi enviado")


class Resumo(Caso):
    # SPECSFY: US-002 FR-005 NFR-003 AC-010
    def test_ac010_resumo_com_duas_contas(self):
        promo(self.srv["trabalho"], dias=40)
        self.srv["pessoal"].add("Banco Inter <cobranca@inter.co>", "Seu boleto vence amanhã")
        self.pos_ensaio()
        _, saida = self.rodar("faxina")
        self.assertIn("Precisa de você", saida)
        for conta in ("trabalho", "pessoal"):
            linha = next(l for l in saida.splitlines() if l.strip().startswith(conta + ":"))
            for palavra in ("rotulad", "arquivad", "apagad", "descadastrad"):
                self.assertIn(palavra, linha)

    # SPECSFY: US-002 FR-006 AC-011
    def test_ac011_plano_de_troca_as_segundas(self):
        self.rodar("papel", "trabalho", "trabalho")
        self.rodar("papel", "pessoal", "pessoal e compras")
        for i in range(38):
            promo(self.srv["trabalho"], dias=i % 6)
        self.pos_ensaio()
        _, saida = self.rodar("faxina", agora=SEGUNDA)
        self.assertIn("Troque o cadastro da Shein para a conta pessoal (38 e-mails/semana)", saida)

    # SPECSFY: FR-002 FR-006 AC-012
    def test_ac012_rotulo_de_conta_errada(self):
        self.rodar("papel", "trabalho", "trabalho")
        self.rodar("papel", "pessoal", "pessoal e compras")
        m = compra(self.srv["trabalho"])
        self.pos_ensaio()
        self.rodar("faxina")
        self.assertIn("Secretário/Conta errada", rotulos(m))

    # SPECSFY: US-002 FR-006 FR-008 AC-013
    def test_ac013_papel_nao_definido(self):
        m = compra(self.srv["trabalho"])
        self.pos_ensaio()
        _, saida = self.rodar("faxina", agora=SEGUNDA)
        self.assertIn("defina o papel da conta trabalho", saida)
        self.assertIn("papel trabalho", saida)
        self.assertNotIn("Secretário/Conta errada", rotulos(m))

    # SPECSFY: FR-002 FR-006 AC-012
    def test_ac012_newsletter_e_seguranca_tambem_tem_conta_certa(self):
        self.rodar("papel", "trabalho", "trabalho, finanças e segurança")
        self.rodar("papel", "pessoal", "pessoal, compras, promoções e newsletters")
        news = self.srv["trabalho"].add("Substack <news@substack.com>", "Edição #12",
                                        cabecalhos={"List-Unsubscribe": "<https://substack.com/u>"})
        alerta = self.srv["pessoal"].add("Google <no-reply@accounts.google.com>", "Alerta de segurança")
        self.pos_ensaio()
        self.rodar("faxina")
        self.assertIn("Secretário/Conta errada", rotulos(news))
        self.assertIn("Secretário/Conta errada", rotulos(alerta))
