-- Limpeza de antigos por conta (US-006, FR-013): dias após os quais Promoções/Newsletters/Notificações/Outros vão para a lixeira.
ALTER TABLE contas ADD COLUMN limpeza_dias INTEGER;
