-- Schema inicial do secretário de e-mails (aplicado por src/estado.py, PRAGMA user_version = 1).
CREATE TABLE IF NOT EXISTS contas (nome TEXT PRIMARY KEY, papel TEXT, ultimo_uid INTEGER NOT NULL DEFAULT 0, validade INTEGER);
CREATE TABLE IF NOT EXISTS regras (remetente TEXT PRIMARY KEY, tipo TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS protegidos (remetente TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS vetos (remetente TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS rascunhos (id INTEGER PRIMARY KEY AUTOINCREMENT, conta TEXT NOT NULL, msgid TEXT, para TEXT NOT NULL,
  assunto TEXT NOT NULL, texto TEXT NOT NULL, criado_em TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS pendentes (id INTEGER PRIMARY KEY AUTOINCREMENT, conta TEXT NOT NULL, msgid TEXT, remetente TEXT NOT NULL,
  nome TEXT, assunto TEXT NOT NULL, quando TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS historico (id INTEGER PRIMARY KEY AUTOINCREMENT, quando TEXT NOT NULL, conta TEXT, remetente TEXT,
  acao TEXT NOT NULL, motivo TEXT);
CREATE INDEX IF NOT EXISTS historico_quando ON historico (quando);
CREATE TABLE IF NOT EXISTS vistos (conta TEXT NOT NULL, remetente TEXT NOT NULL, uid INTEGER NOT NULL, quando TEXT NOT NULL,
  lido INTEGER NOT NULL, PRIMARY KEY (conta, uid));
CREATE INDEX IF NOT EXISTS vistos_remetente ON vistos (remetente, quando);
CREATE TABLE IF NOT EXISTS execucoes (id INTEGER PRIMARY KEY AUTOINCREMENT, dia TEXT NOT NULL, ensaio INTEGER NOT NULL, quando TEXT NOT NULL);
