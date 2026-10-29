from apoio import Caso, na_lixeira, promo


class Comandos(Caso):
    # SPECSFY: US-003 FR-004 FR-008 AC-007
    def test_ac007_protege_remetente(self):
        t = self.srv["trabalho"]
        msgs = [promo(t, de="Samsung <promo@samsung.com>", dias=40 + i, one_click=True) for i in range(4)]
        codigo, saida = self.rodar("protege", "samsung.com")
        self.assertEqual(codigo, 0)
        self.assertIn("samsung.com", saida)
        self.pos_ensaio()
        self.rodar("faxina")
        self.assertFalse(any(na_lixeira(t, m) for m in msgs))
        self.assertEqual(self.http.pedidos, [])

    # SPECSFY: US-003 FR-008 AC-031
    def test_ac031_desfazer_protecao_e_veto(self):
        t = self.srv["trabalho"]
        loja = promo(t, de="Loja <ofertas@loja.com>", dias=40)
        for i in range(4):
            promo(t, de="News <n@newsletter.com>", dias=i, one_click=True)
        self.rodar("protege", "loja.com")
        self.rodar("veta", "newsletter.com")
        c1, s1 = self.rodar("desprotege", "loja.com")
        c2, s2 = self.rodar("libera", "newsletter.com")
        self.assertEqual((c1, c2), (0, 0))
        self.assertIn("loja.com", s1)
        self.assertIn("newsletter.com", s2)
        self.pos_ensaio()
        self.rodar("faxina")
        self.assertTrue(na_lixeira(t, loja))
        self.assertEqual([r.full_url for r in self.http.pedidos], ["https://newsletter.com/u?t=1"])
