#!/usr/bin/env bash
# Instalador. Roda UMA vez, depois de o config.json estar pronto.
# Descobre sozinho se esta num Mac (launchd) ou num Linux/VPS (cron).
set -e
BASE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$BASE"

echo "› Rastreador de passagem — instalacao"
echo

# --- 1. Python ---
command -v python3 >/dev/null || { echo "✗ python3 nao encontrado"; exit 1; }
echo "✓ python3 $(python3 -c 'import platform;print(platform.python_version())')"

# --- 2. Configuracao ---
[[ -f config.json ]] || { echo "✗ falta o config.json. Copie o config.exemplo.json e edite."; exit 1; }
python3 - <<'PY' || exit 1
import json, sys, re
try:
    cfg = json.load(open("config.json"))
except Exception as e:
    sys.exit(f"✗ config.json invalido: {e}")
cfg = {k: v for k, v in cfg.items() if not k.startswith("_")}
erros = []
if not re.fullmatch(r"[a-z0-9-]+", str(cfg.get("rotulo", ""))):
    erros.append("rotulo deve ter so letras minusculas, numeros e hifen")
for c in ("origem", "destino"):
    if not re.fullmatch(r"[A-Z]{3}", str(cfg.get(c, ""))):
        erros.append(f"{c} deve ser um codigo IATA de 3 letras maiusculas (GRU, SSA, MCO...)")
if not cfg.get("combos"):
    erros.append("nenhuma viagem em 'combos'")
for c in cfg.get("combos", []):
    for campo in ("id", "ida"):
        if not c.get(campo):
            erros.append(f"combo sem '{campo}'")
    for nome in ("janela_ida", "janela_volta"):
        j = c.get(nome) or {}
        for lado in ("partida", "chegada"):
            if j.get(lado, {}).get("modo") not in (None, "any", "after", "before", "between"):
                erros.append(f"{nome}.{lado}.modo invalido em {c.get('id')}")
    if c.get("volta") and not c.get("ida"):
        erros.append(f"combo {c.get('id')} tem volta sem ida")
for h in list(cfg.get("horarios", [])) + list((cfg.get("boletim") or {}).get("horarios", [])):
    if not re.fullmatch(r"([01]?\d|2[0-3]):[0-5]\d", str(h)):
        erros.append(f"horario invalido: {h}")
try:
    from zoneinfo import ZoneInfo
    ZoneInfo(cfg.get("fuso", "America/Sao_Paulo"))
except Exception:
    erros.append(f"fuso desconhecido: {cfg.get('fuso')}")
if erros:
    sys.exit("✗ config.json:\n  - " + "\n  - ".join(erros))
print(f"✓ config.json: {cfg['origem']} → {cfg['destino']}, "
      f"{len(cfg['combos'])} viagem(ns) vigiada(s)")
if not (cfg.get("email_destino") or "").strip():
    print("  (email_destino vazio: o relatorio so fica salvo em ultimo_parecer.html)")
PY

# --- 3. Ambiente Python ---
if [[ ! -x "$BASE/.venv/bin/python" ]]; then
  echo "› criando ambiente Python..."
  python3 -m venv .venv
fi
echo "› instalando dependencias..."
./.venv/bin/pip install -q --upgrade pip
./.venv/bin/pip install -q -r requirements.txt

# --- 4. Navegador ---
# E' o Chromium do proprio Playwright, nao o Chrome do usuario: roda escondido
# e nao depende de janela aberta.
if [[ "$(uname -s)" == "Linux" ]]; then
  EXTRA="--with-deps"   # no Linux faltam bibliotecas de sistema
else
  EXTRA=""
fi
if [[ -z "$(ls -d "$HOME/.cache/ms-playwright"/chromium-* "$HOME/Library/Caches/ms-playwright"/chromium-* 2>/dev/null)" ]]; then
  echo "› baixando o Chromium do Playwright (~150 MB, so' na primeira vez)..."
  ./.venv/bin/python -m playwright install $EXTRA chromium >/dev/null
else
  echo "✓ Chromium do Playwright ja instalado"
fi

ROTULO=$(./.venv/bin/python -c "from comum import carregar_config; print(carregar_config()['rotulo'])")

# --- 5. Agendamento ---
if [[ "$(uname -s)" == "Darwin" ]]; then
  # ---------- Mac: launchd ----------
  LABEL="com.rastreiopassagem.$ROTULO"
  PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
  mkdir -p "$HOME/Library/LaunchAgents"
  ./.venv/bin/python - "$BASE" "$LABEL" "$PLIST" <<'PY'
import sys, plistlib
from comum import carregar_config
base, label, destino = sys.argv[1], sys.argv[2], sys.argv[3]
cfg = carregar_config()
plist = {
    "Label": label,
    "ProgramArguments": ["/bin/bash", "-lc", f"{base}/rodada.sh"],
    "RunAtLoad": False,
    "StandardOutPath": f"{base}/launchd.out",
    "StandardErrorPath": f"{base}/launchd.err",
}
# intervalo_minutos e' preferido a horario fixo: com o Mac que dorme, horario
# fixo vira rajada -- ao acordar, o launchd dispara de uma vez tudo que perdeu.
minutos = cfg.get("intervalo_minutos")
if minutos:
    plist["StartInterval"] = int(minutos) * 60
    quantas = f"a cada {int(minutos)} min"
else:
    intervalos = []
    for h in cfg.get("horarios", ["09:07"]):
        hh, mm = h.split(":")
        intervalos.append({"Hour": int(hh), "Minute": int(mm)})
    plist["StartCalendarInterval"] = intervalos
    quantas = f"{len(intervalos)} leitura(s)/dia"
with open(destino, "wb") as fh:
    plistlib.dump(plist, fh)
print(f"✓ agendamento gravado ({quantas})")
PY
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$PLIST"
  echo "✓ agendamento ativo no Mac: $LABEL"
  echo "  Atencao: Mac que dorme nao coleta. Em teste real perderam-se 3 de cada"
  echo "  4 leituras. Ver docs/04-licoes.md."
else
  # ---------- Linux/VPS: cron ----------
  MARCA="# rastreio-passagem:$ROTULO"
  LINHAS=$(./.venv/bin/python - "$BASE" "$MARCA" <<'PY'
import sys, zlib
from datetime import datetime
from zoneinfo import ZoneInfo
from comum import carregar_config
base, marca = sys.argv[1], sys.argv[2]
cfg = carregar_config()
cmd = f"cd {base} && ./rodada.sh"
# Minuto derivado do rotulo, nao fixo: dois rastreadores caindo no mesmo minuto
# e' o cenario que ja travou a coleta por horas.
base_min = zlib.crc32(cfg["rotulo"].encode()) % 60
linhas = []
minutos = cfg.get("intervalo_minutos")
if minutos:
    m = int(minutos)
    if m < 60 and 60 % m == 0:
        linhas.append(f"{base_min % m}-59/{m} * * * * {cmd}")
    else:
        linhas.append(f"{base_min} */{max(1, m // 60)} * * * {cmd}")
else:
    # O cron le a agenda no fuso do SISTEMA (numa VPS, quase sempre UTC) e nao
    # costuma honrar CRON_TZ. Entao a conversao e' feita aqui: o config continua
    # escrito no fuso de casa, que e' o que a pessoa pensa.
    casa = ZoneInfo(cfg.get("fuso", "America/Sao_Paulo"))
    hoje = datetime.now(casa).date()
    for h in cfg.get("horarios", ["09:07"]):
        hh, mm = h.split(":")
        local = datetime(hoje.year, hoje.month, hoje.day, int(hh), int(mm), tzinfo=casa)
        # astimezone() sem argumento = fuso do sistema, que e' o do cron
        no_sistema = local.astimezone()
        linhas.append(f"{no_sistema.minute} {no_sistema.hour} * * * {cmd}")
print("\n".join(f"{l}  {marca}" for l in linhas))
PY
)
  ATUAL=$(crontab -l 2>/dev/null | grep -v "$MARCA" || true)
  {
    echo "$ATUAL" | sed '/^$/d'
    echo 'MAILTO=""'
    echo "$LINHAS"
  } | awk '!/^(MAILTO=|CRON_TZ=)/ || !seen[$0]++' | crontab -
  echo "✓ agendamento no cron:"
  crontab -l | grep "$MARCA" | sed 's/^/    /'
fi

echo
echo "Pronto. Para testar agora, sem esperar o horario:"
echo "    ./rodada.sh && tail -40 rodada.log"
echo "Para desligar tudo:"
echo "    ./desinstalar.sh"
