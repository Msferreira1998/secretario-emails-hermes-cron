#!/usr/bin/env bash
# Chamado a cada 15 min pelo cron do Hermes (sem agente); saída vazia = nenhuma mensagem no Telegram.
exec python3 "{{RAIZ}}/bin/secretario" alerta
