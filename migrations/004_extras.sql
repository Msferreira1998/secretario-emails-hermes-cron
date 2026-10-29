-- US-008–US-010 (FR-016–FR-024): vencimentos, registro da lixeira e restaurados (desfaz), VIPs e ponteiro do alerta,
-- classificação original (aprende com a troca de marcador) e pedidos a caminho.
ALTER TABLE contas ADD COLUMN alerta_uid INTEGER;
CREATE TABLE vencimentos (conta TEXT NOT NULL, msgid TEXT NOT NULL, remetente TEXT, nome TEXT, assunto TEXT,
  vence TEXT NOT NULL, PRIMARY KEY (conta, msgid));
CREATE TABLE lixeira (conta TEXT NOT NULL, msgid TEXT NOT NULL, remetente TEXT, quando TEXT NOT NULL);
CREATE INDEX lixeira_quando ON lixeira(quando);
CREATE TABLE restaurados (msgid TEXT PRIMARY KEY, quando TEXT NOT NULL);
CREATE TABLE vips (remetente TEXT PRIMARY KEY);
CREATE TABLE classificados (conta TEXT NOT NULL, msgid TEXT NOT NULL, remetente TEXT NOT NULL, tipo TEXT NOT NULL,
  quando TEXT NOT NULL, PRIMARY KEY (conta, msgid));
CREATE TABLE pedidos (conta TEXT NOT NULL, chave TEXT NOT NULL, loja TEXT, assunto TEXT, quando TEXT NOT NULL,
  PRIMARY KEY (conta, chave));
