#!/usr/bin/env bash
# Chamado pelo cron do Hermes (sem agente); o stdout vai direto para o Telegram.
exec python3 "{{RAIZ}}/bin/secretario" faxina
