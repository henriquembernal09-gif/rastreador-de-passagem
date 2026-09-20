#!/usr/bin/env python3
"""Canal de alerta urgente. Separado do relatorio por e-mail de proposito:

o relatorio e' boletim (chega sempre, voce le quando quiser); o alerta e'
interrupcao (chega raramente, voce age na hora). Misturar os dois foi o que
fez a queda de 06/09/2026 passar batida.

Ordem de tentativa:
1. Telegram -> token e chat_id no Keychain do macOS, nunca em arquivo.
2. E-mail marcado como URGENTE -> pelo conector do Claude Code. Chega no
   celular mesmo com o Mac fechado, que e' onde a notificacao do macOS falha
   justamente quando mais importa. Assunto separado do boletim de proposito,
   para dar para criar regra e som proprio no celular.
3. Notificacao do macOS -> so funciona com o Mac acordado, mas e' instantanea.
4. stderr -> ultimo recurso, para o log da rodada guardar o que nao saiu.

Telegram e e-mail sao tentados os DOIS: alerta de queda brusca nao pode
depender de um canal so'.

Para configurar o Telegram, rode: ./configurar-telegram.sh
"""
import json, os, re, shutil, subprocess, sys, urllib.parse, urllib.request

SERVICO = "rastreio-telegram"
PREFIXO_URGENTE = "[QUEDA DE PRECO]"


ENV = {"token": "RASTREIO_TELEGRAM_TOKEN", "chat_id": "RASTREIO_TELEGRAM_CHAT"}


def _segredo(conta):
    """Le um segredo. Nunca escreve, nunca ecoa, nunca cai em arquivo do repo.

    macOS  -> Keychain (o OneDrive sincroniza arquivo; o Keychain nao).
    Linux  -> variavel de ambiente, para o VPS injetar via systemd ou .env
              fora do repo, com permissao 600.
    """
    if os.environ.get(ENV[conta]):
        return os.environ[ENV[conta]].strip()
    exe = shutil.which("security")
    if not exe:
        return None
    try:
        r = subprocess.run([exe, "find-generic-password", "-s", SERVICO,
                            "-a", conta, "-w"],
                           capture_output=True, text=True, timeout=15)
    except Exception:
        return None
    return r.stdout.strip() or None if r.returncode == 0 else None


def via_telegram(texto):
    token, chat = _segredo("token"), _segredo("chat_id")
    if not (token and chat):
        return False
    dados = urllib.parse.urlencode({
        "chat_id": chat, "text": texto,
        "parse_mode": "HTML", "disable_web_page_preview": "true",
    }).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage", data=dados)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r).get("ok", False)
    except Exception as e:
        print(f"telegram falhou: {type(e).__name__}", file=sys.stderr)
        return False


def _destinos():
    """Para onde mandar o alerta urgente. E-mail nao e' segredo, entao pode vir
    de arquivo: RASTREIO_EMAIL_ALERTA no ambiente, senao o email_destino do
    config.json ao lado (o vigia nao tem config, so' o ambiente)."""
    env = os.environ.get("RASTREIO_EMAIL_ALERTA", "")
    if env.strip():
        bruto = env
    else:
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
        try:
            with open(p, encoding="utf-8") as fh:
                bruto = json.load(fh).get("email_destino") or ""
        except Exception:
            return []
    itens = bruto if isinstance(bruto, list) else re.split(r"[,;\s]+", str(bruto))
    return [e.strip() for e in itens if e.strip() and "@" in e]


def via_email(texto, titulo):
    """Usa o Claude Code, que ja' tem o conector de e-mail autenticado. Nenhuma
    senha em lugar nenhum -- mesmo caminho do relatorio, assunto diferente."""
    destinos = _destinos()
    exe = shutil.which("claude")
    if not (destinos and exe):
        return False
    limpo = texto
    for tag in ("<b>", "</b>", "<i>", "</i>"):
        limpo = limpo.replace(tag, "")
    assunto = f"{PREFIXO_URGENTE} {titulo}"
    prompt = (
        f"Envie um e-mail para {', '.join(destinos)} com o assunto exatamente "
        f"nesta linha: {assunto}\n"
        f"O corpo e' exatamente o texto entre as marcas, sem alterar nenhum "
        f"numero, sem reescrever e sem acrescentar comentario seu:\n"
        f"<<<INICIO>>>\n{limpo}\n<<<FIM>>>\n"
        f"Responda apenas ENVIADO, ou FALHOU seguido do motivo."
    )
    try:
        r = subprocess.run([exe, "-p", prompt, "--allowedTools",
                            "mcp__claude_ai_Gmail__send_message"],
                           capture_output=True, text=True, timeout=300)
    except Exception as e:
        print(f"e-mail de alerta falhou: {type(e).__name__}", file=sys.stderr)
        return False
    if "ENVIADO" in (r.stdout or "").upper():
        return True
    print(f"e-mail de alerta nao saiu: {(r.stdout or r.stderr or '')[:200]}",
          file=sys.stderr)
    return False


def via_notificacao(texto, titulo):
    exe = shutil.which("osascript")
    if not exe:
        return False
    limpo = texto.replace('"', "'").replace("\\", "")[:230]
    for tag in ("<b>", "</b>", "<i>", "</i>"):
        limpo = limpo.replace(tag, "")
    script = (f'display notification "{limpo}" with title "{titulo}" '
              f'sound name "Glass"')
    try:
        return subprocess.run([exe, "-e", script], capture_output=True,
                              timeout=20).returncode == 0
    except Exception:
        return False


def alertar(texto, titulo="Passagem"):
    """Devolve os canais que funcionaram, separados por '+', ou None.

    Todos os canais disponiveis sao tentados, nao o primeiro que responder: um
    alerta de queda brusca nao pode depender de um canal so'. Duplicar um
    alerta que dispara poucas vezes por mes custa menos do que perder um."""
    vias = []
    if via_telegram(texto):
        vias.append("telegram")
    if via_email(texto, titulo):
        vias.append("email")
    if via_notificacao(texto, titulo):
        vias.append("notificacao")
    if not vias:
        print(f"NENHUM CANAL DISPONIVEL. Alerta perdido:\n{texto}", file=sys.stderr)
        return None
    return "+".join(vias)


if __name__ == "__main__":
    msg = " ".join(sys.argv[1:]) or "teste de canal do rastreador de passagem"
    via = alertar(msg, "Rastreador — teste")
    print(f"enviado via {via}" if via else "nao enviado")
    sys.exit(0 if via else 1)
