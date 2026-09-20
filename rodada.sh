#!/usr/bin/env bash
# Uma rodada: coleta -> alerta urgente -> parecer -> e-mail.
#
# Roda igual no Mac (launchd) e no Linux (cron). Tres protecoes que existem por
# causa de um incidente real, em que uma rodada ficou 3h15 pendurada e engoliu
# a leitura de uma queda de 45%:
#   LOCK    - dois rastreadores nunca rodam juntos. Dois Chrome headless
#             brigando transformam 3 minutos de coleta em horas.
#   LIMITE  - cada etapa tem teto de tempo. Etapa travada nao leva a rodada.
#   ALERTA  - sai logo apos a coleta, ANTES do parecer e do e-mail. Se o resto
#             falhar, o aviso de queda ja foi.
BASE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$BASE" || exit 1
LOG="$BASE/rodada.log"
PY="$BASE/.venv/bin/python"

# Fuso: a maquina pode rodar em UTC (VPS quase sempre roda). Sem isto, a janela
# de horario do voo e o slot do boletim seriam comparados com relogio errado.
FUSO=$("$PY" -c "from comum import carregar_config; print(carregar_config().get('fuso','America/Sao_Paulo'))" 2>/dev/null || echo "America/Sao_Paulo")
export TZ="$FUSO"

# PATH no topo, nao so antes do e-mail: o alertar.py tambem manda e-mail pelo
# `claude`, e ele roda ANTES do enviar.py. Sem isto o alerta sai calado.
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

# Segredos opcionais (Telegram) ficam fora do repo, em arquivo 600.
[[ -f "$HOME/.rastreio-passagem.env" ]] && . "$HOME/.rastreio-passagem.env"

LOCK="/tmp/rastreio-passagem.lock"
LIMITE_COLETA=900      # 15 min
LIMITE_ALERTA=420      # o alerta tambem sai por e-mail, que leva ~1 min
LIMITE_PARECER=180
LIMITE_EMAIL=600
ESPERA_LOCK=720        # espera ate 12 min pela vez

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG"; }

liberar() { rm -rf "$LOCK" 2>/dev/null; }

pegar_lock() {
  local fim=$((SECONDS + ESPERA_LOCK)) dono
  while ! mkdir "$LOCK" 2>/dev/null; do
    dono=$(cat "$LOCK/pid" 2>/dev/null)
    if [[ -n "$dono" ]] && ! kill -0 "$dono" 2>/dev/null; then
      log "lock orfao do pid $dono, removendo"
      rm -rf "$LOCK"
      continue
    fi
    (( SECONDS >= fim )) && return 1
    sleep 20
  done
  echo $$ > "$LOCK/pid"
  trap liberar EXIT INT TERM
  return 0
}

# Teto de tempo por etapa. No Linux existe `timeout` (mata o processo sem
# depender de process group); no Mac, nao existe por padrao, entao vai o
# cao de guarda em bash.
if command -v timeout >/dev/null 2>&1; then
  com_limite() { local seg=$1; shift; timeout -k 10 "$seg" "$@" >> "$LOG" 2>&1; }
else
  com_limite() {
    local seg=$1; shift
    "$@" >> "$LOG" 2>&1 &
    local alvo=$!
    ( sleep "$seg"; kill -TERM -"$alvo" 2>/dev/null || kill -TERM "$alvo" 2>/dev/null
      sleep 10; kill -KILL "$alvo" 2>/dev/null ) &
    local cao=$!
    wait "$alvo"; local st=$?
    kill "$cao" 2>/dev/null
    return $st
  }
fi

echo "=== $(date '+%Y-%m-%d %H:%M:%S') inicio ===" >> "$LOG"

# Encerramento automatico depois de rastreio_termina_em: rastreador de viagem
# comprada e' lixo que continua mandando e-mail.
FIM=$("$PY" -c "from comum import carregar_config; print(carregar_config().get('rastreio_termina_em','') or '')" 2>/dev/null | tr -d '-')
if [[ -n "$FIM" && "$(date +%Y%m%d)" -gt "$FIM" ]]; then
  log "periodo encerrado, desinstalando"
  "$BASE/desinstalar.sh" >> "$LOG" 2>&1
  exit 0
fi

if ! pegar_lock; then
  log "outro rastreador ocupou os $((ESPERA_LOCK/60)) min de espera; pulando esta rodada"
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') fim (sem vez) ===" >> "$LOG"
  exit 0
fi

# Jitter: o agendador dispara no minuto cheio e o Google nota padrao. Espalha.
sleep $((RANDOM % 180))

com_limite $LIMITE_COLETA "$PY" coletar.py \
  || log "coleta terminou mal (timeout ou erro) — seguindo com o que gravou"

# alerta primeiro: e' o que nao pode depender do resto dar certo
com_limite $LIMITE_ALERTA "$PY" alertar.py

# curva de antecedencia da rota: pesada, entao no maximo uma vez por semana
if [[ ! -f "$BASE/antecedencia.csv" ]] || [[ -n "$(find "$BASE" -maxdepth 1 -name antecedencia.csv -mtime +6)" ]]; then
  com_limite $LIMITE_COLETA "$PY" antecedencia.py
fi

com_limite $LIMITE_PARECER "$PY" analisar.py || { log "analise falhou"; exit 1; }

com_limite $LIMITE_EMAIL "$PY" enviar.py

date '+%Y-%m-%dT%H:%M:%S%z' > "$BASE/ultima_rodada_ok.txt"
echo "=== $(date '+%Y-%m-%d %H:%M:%S') fim ===" >> "$LOG"
