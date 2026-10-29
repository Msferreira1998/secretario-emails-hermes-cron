from apoio import Caso, ONE_CLICK, na_caixa, promo


class Descadastro(Caso):
    # SPECSFY: US-001 FR-003 AC-004
    def test_ac004_descadastro_em_um_clique(self):
        t = self.srv["trabalho"]
        for i in range(4):
            t.add("News <n@loja-x.com>", f"Novidades {i}", dias=i * 10,
                  cabecalhos={"List-Unsubscribe": "<https://loja-x.com/u?t=1>, <mailto:sair@loja-x.com>",
                              "List-Unsubscribe-Post": ONE_CLICK})
        self.pos_ensaio()
        _, saida = self.rodar("faxina")
        self.assertEqual(len(self.http.pedidos), 1)
        req = self.http.pedidos[0]
        self.assertEqual(req.full_url, "https://loja-x.com/u?t=1")
        self.assertEqual(req.get_method(), "POST")
        self.assertEqual(req.data, ONE_CLICK.encode())
        self.assertIn("loja-x.com", saida.split("Descadastrados:", 1)[1])

    # SPECSFY: FR-003 NFR-001 AC-005
    def test_ac005_link_sem_one_click_nao_e_seguido(self):
        t = self.srv["trabalho"]
        msgs = [t.add("Blog <b@blog-y.com>", f"Post {i}", dias=i * 10,
                      cabecalhos={"List-Unsubscribe": "<https://blog-y.com/sair>"}) for i in range(4)]
        self.pos_ensaio()
        _, saida = self.rodar("faxina")
        self.assertEqual(self.http.pedidos, [])
        bloco = saida.lower().split("descadastre você mesmo", 1)[1]
        self.assertIn("blog-y.com", bloco)
        self.assertFalse(any(na_caixa(t, m) for m in msgs))

    # SPECSFY: US-001 FR-003 NFR-003 AC-004
    def test_ac004_contagem_por_conta_e_remetente_so_com_antigos(self):
        t, p = self.srv["trabalho"], self.srv["pessoal"]
        cab = {"List-Unsubscribe": "<https://loja-x.com/u?t=1>", "List-Unsubscribe-Post": ONE_CLICK}
        for i in range(4):
            t.add("News <n@loja-x.com>", f"Novidades {i}", dias=i, cabecalhos=cab)
        self.pos_ensaio()
        self.rodar("faxina")
        self.http.pedidos.clear()
        velho = p.add("News <n@loja-x.com>", "Antiga", dias=90, cabecalhos=cab)
        _, saida = self.rodar("faxina")
        self.assertIn("pessoal:", saida)
        self.assertNotIn("falhou", saida)
        self.assertEqual(self.http.pedidos, [])
        self.assertFalse(na_caixa(p, velho))
