# Testes

<!-- specsfy:documentator:start -->
## Resumo

- Arquivos de teste: 12.
- Runner: não identificado.
- Scripts: não declarados.

| Arquivo |
| --- |
| tests/apoio.py |
| tests/test_classificar.py |
| tests/test_comandos.py |
| tests/test_contas.py |
| tests/test_descadastro.py |
| tests/test_estado.py |
| tests/test_extras.py |
| tests/test_faxina.py |
| tests/test_instalar.py |
| tests/test_limpeza.py |
| tests/test_respostas.py |
| tests/test_resumo.py |
<!-- specsfy:documentator:end -->

## Como testar (escrito à mão)

- `python3 -m unittest discover -s tests` — 34 casos, um ou mais por AC (marcador `SPECSFY:`).
- `tests/apoio.py` traz HOME temporário, IMAP falso (modelo de marcadores do Gmail e pastas no genérico), SMTP, HTTP, IA e `hermes` falsos. Nenhum teste toca contas reais.
