#!/usr/bin/env bash
# OPCIONAL. So faz sentido se voce quiser o alerta tambem no Telegram.
# O alerta por e-mail ja funciona sem isto.
#
# Antes de rodar, crie o bot: no Telegram, fale com @BotFather -> /newbot.
# Depois mande qualquer mensagem para o seu bot, para ele saber quem voce e'.
#
# Onde o segredo fica guardado:
#   Mac   -> Keychain (arquivo em pasta sincronizada vaza para a nuvem)
#   Linux -> ~/.rastreio-passagem.env, com permissao 600, fora do repo
set -e
SERVICO="rastreio-telegram"

printf "Token do bot (BotFather): "
read -r TOKEN
[[ -z "$TOKEN" ]] && { echo "sem token, nada a fazer"; exit 1; }

echo "› procurando a sua conversa com o bot..."
CHAT=$(python3 - "$TOKEN" <<'PY'
import json, sys, urllib.request
token = sys.argv[1]
try:
    with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/getUpdates", timeout=30) as r:
        d = json.load(r)
except Exception as e:
    sys.exit(f"falhou: {type(e).__name__}")
for item in reversed(d.get("result", [])):
    msg = item.get("message") or item.get("channel_post") or {}
    chat = (msg.get("chat") or {}).get("id")
    if chat:
        print(chat); break
PY
)
[[ -z "$CHAT" ]] && { echo "✗ nao achei conversa. Mande uma mensagem para o bot e rode de novo."; exit 1; }
echo "✓ conversa encontrada: $CHAT"

if [[ "$(uname -s)" == "Darwin" ]]; then
  security add-generic-password -U -s "$SERVICO" -a token   -w "$TOKEN" >/dev/null
  security add-generic-password -U -s "$SERVICO" -a chat_id -w "$CHAT"  >/dev/null
  echo "✓ guardado no Keychain do Mac."
else
  ENV="$HOME/.rastreio-passagem.env"
  touch "$ENV"; chmod 600 "$ENV"
  grep -v -E '^(export )?RASTREIO_TELEGRAM_' "$ENV" > "$ENV.tmp" 2>/dev/null || true
  mv "$ENV.tmp" "$ENV"; chmod 600 "$ENV"
  { echo "export RASTREIO_TELEGRAM_TOKEN=\"$TOKEN\""
    echo "export RASTREIO_TELEGRAM_CHAT=\"$CHAT\""; } >> "$ENV"
  echo "✓ guardado em $ENV (permissao 600, fora do repo)."
fi
echo "Teste: ./.venv/bin/python -c \"import canal; canal.alertar('teste do rastreador','Teste')\""
