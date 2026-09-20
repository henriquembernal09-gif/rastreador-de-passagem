#!/usr/bin/env bash
# Tira o agendamento. NAO apaga nada do historico ja coletado.
set -e
BASE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$BASE"
ROTULO=$(./.venv/bin/python -c "from comum import carregar_config; print(carregar_config()['rotulo'])" 2>/dev/null || echo "")
[[ -z "$ROTULO" ]] && { echo "nao consegui ler o rotulo do config.json"; exit 1; }

if [[ "$(uname -s)" == "Darwin" ]]; then
  LABEL="com.rastreiopassagem.$ROTULO"
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
  rm -f "$HOME/Library/LaunchAgents/$LABEL.plist"
  echo "✓ agendamento removido do Mac: $LABEL"
else
  MARCA="# rastreio-passagem:$ROTULO"
  if crontab -l 2>/dev/null | grep -q "$MARCA"; then
    crontab -l 2>/dev/null | grep -v "$MARCA" | crontab -
    echo "✓ agendamento removido do cron: $ROTULO"
  else
    echo "nada agendado para $ROTULO"
  fi
fi
echo "Historico preservado em $BASE/historico.csv"
