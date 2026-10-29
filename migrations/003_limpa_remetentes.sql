-- Lixeira por remetente (US-007, FR-015): remetente ou domínio → dias após os quais Promoções/Newsletters/Notificações dele vão para a lixeira.
CREATE TABLE limpa_remetentes (remetente TEXT PRIMARY KEY, dias INTEGER NOT NULL);
