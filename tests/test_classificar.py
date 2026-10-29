from apoio import Caso, IAFalsa, na_caixa, na_lixeira, rotulos


class Classificar(Caso):
    # SPECSFY: FR-001 NFR-001 NFR-002 AC-009
    def test_ac009_ia_so_na_duvida_com_saida_fechada(self):
        t = self.srv["trabalho"]
        texto = "a" * 300 + "SEGREDO" * 50
        m = t.add("Carlos <carlos@empresa-x.com>", "Proposta de parceria", texto=texto)
        self.ia = IAFalsa(tipo="Spam perigoso")
        self.pos_ensaio()
        self.ia.prompts.clear()
        self.rodar("faxina")
        self.assertEqual(len(self.ia.prompts), 1)
        p = self.ia.prompts[0]
        self.assertIn("carlos@empresa-x.com", p)
        self.assertIn("Proposta de parceria", p)
        self.assertIn("a" * 50, p)
        self.assertNotIn("SEGREDO", p)
        self.assertIn("Secretário/Outros", rotulos(m))
        self.assertTrue(na_caixa(t, m))
        self.assertFalse(na_lixeira(t, m))

    # SPECSFY: FR-001 NFR-002 AC-029
    def test_ac029_regra_do_usuario_vence_a_ia(self):
        t = self.srv["trabalho"]
        m = t.add("Nomad <contato@nomadglobal.com>", "Novidades do mês")
        self.rodar("regra", "nomadglobal.com", "Finanças")
        self.pos_ensaio()
        self.ia.prompts.clear()
        self.rodar("faxina")
        self.assertEqual(self.ia.prompts, [])
        self.assertIn("Secretário/Finanças", rotulos(m))

    # SPECSFY: FR-001 FR-004 AC-003
    def test_ac003_marketing_de_banco_e_arquivado_mas_nunca_apagado(self):
        t = self.srv["trabalho"]
        lista = {"List-Unsubscribe": "<https://nubank.com.br/sair>", "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"}
        mkt = [t.add("Nubank <news@nubank.com.br>", "Suba de nível em NuCoin", dias=40 + i, cabecalhos=lista) for i in range(4)]
        pix = t.add("Wise <noreply@wise.com>", "Dinheiro recebido de ATERA", cabecalhos={"List-Unsubscribe": "<https://wise.com/u>"})
        sub = t.add("Nubank <todomundo@novidades.nubank.com.br>", "Cartão de crédito PJ sem burocracia")
        ci = t.add("Matheus <notifications@github.com>", "[Exemplo/ultra] PR run failed: pausa para a cobrança",
                   cabecalhos={"List-Id": "<ultra.Exemplo.github.com>"})
        self.pos_ensaio()
        _, saida = self.rodar("faxina")
        for m in mkt:
            self.assertIn("Secretário/Promoções", rotulos(m))
            self.assertFalse(na_caixa(t, m))
            self.assertFalse(na_lixeira(t, m))
        self.assertEqual(self.http.pedidos, [])
        self.assertIn("Secretário/Finanças", rotulos(pix))
        self.assertTrue(na_caixa(t, pix))
        self.assertNotIn("NuCoin", saida.split("Precisa de você", 1)[1])
        self.assertIn("Secretário/Promoções", rotulos(sub))
        self.assertIn("Secretário/Notificações", rotulos(ci))
