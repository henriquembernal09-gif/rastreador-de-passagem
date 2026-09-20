#!/usr/bin/env python3
"""Envia o relatorio por e-mail nos horarios agendados. Tres caminhos:

1. Claude Code (`claude` no PATH) -> usa o conector de e-mail ja autenticado.
   Nao ha senha para guardar em lugar nenhum. E' o caminho preferido.
2. SMTP -> usa RASTREIO_SMTP_USER e RASTREIO_SMTP_PASS do ambiente.
   A senha nunca fica em arquivo.
3. Nenhum dos dois -> so avisa. O relatorio segue salvo em ultimo_parecer.html.

Boletim nao e' alerta. A coleta roda a cada 20-40 min para nao perder uma queda
brusca, mas isso nao e' motivo para 70 e-mails por dia -- em 06/09/2026 foram
15 boletins em tres horas e a caixa do Dr. Henrique e do Breno virou ruido.
Desde entao o e-mail so' sai nos horarios de `boletim.horarios` do config.json.
O alerta de queda (alertar.py + canal.py) continua saindo na hora, sempre.

A regra e' por SLOT, nao por "esta na hora agora": vale o ultimo horario
agendado que ja' passou. Mac que dormiu das 11h as 15h acorda e manda um
boletim so' -- o das 12h --, nao a rajada das rodadas perdidas.
"""
import os, re, shutil, smtplib, subprocess, sys
from datetime import datetime, timedelta
from email.message import EmailMessage

from comum import carregar_config, caminho, agora

CFG = carregar_config()
MARCA = "ultimo_boletim.txt"


def ler(nome):
    p = caminho(nome)
    if not os.path.exists(p):
        raise SystemExit(f"FALHOU: {nome} nao existe. Rode analisar.py antes.")
    return open(p, encoding="utf-8").read().strip()


def slot_devido(horarios, ref):
    """Marca do ultimo horario agendado que ja' passou, olhando ontem se ainda
    nao passou nenhum hoje."""
    pontos = []
    for h in horarios:
        hh, mm = str(h).split(":")
        pontos.append(ref.replace(hour=int(hh), minute=int(mm),
                                  second=0, microsecond=0))
    passados = [p for p in pontos if p <= ref]
    return max(passados) if passados else max(pontos) - timedelta(days=1)


def na_hora(ref=None):
    """(enviar?, motivo). Sem `boletim.horarios` no config, envia toda rodada
    -- e' o comportamento antigo, para nao quebrar rastreador nao migrado."""
    bol = CFG.get("boletim") or {}
    # boletim.ativo: false -> este repo nao manda e-mail proprio; quem manda e' o
    # consolidador em ~/Dev/boletim-passagens, que junta todos os rastreadores num
    # e-mail so'. Tres rastreadores x 2 boletins/dia eram 6 e-mails por dia.
    # O ALERTA de queda continua saindo daqui, na hora, por outro canal.
    if bol.get("ativo") is False:
        return False, "boletim proprio desligado: quem envia e' o consolidador"
    horarios = bol.get("horarios") or []
    if not horarios:
        return True, "sem agenda de boletim no config: envia a cada rodada"
    ref = ref or agora()
    slot = slot_devido(horarios, ref)
    ultimo = ler_marca()
    if ultimo and ultimo >= slot:
        return False, (f"boletim das {slot:%d/%m %H:%M} ja' saiu "
                       f"({ultimo:%d/%m %H:%M}); proximo horario: "
                       + ", ".join(horarios))
    return True, f"boletim das {slot:%d/%m %H:%M}"


def ler_marca():
    """Marca ilegivel conta como "nunca enviado" -- na duvida o boletim sai, e'
    menos ruim do que ficar mudo. Aceita o offset com e sem dois pontos: ate' o
    Python 3.10 o fromisoformat nao le o -0300 que o `date` do shell escreve."""
    try:
        with open(caminho(MARCA), encoding="utf-8") as fh:
            txt = fh.read().strip()
    except Exception:
        return None
    for candidato in (txt, re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", txt)):
        try:
            return datetime.fromisoformat(candidato)
        except ValueError:
            continue
    return None


def marcar_enviado(ref=None):
    with open(caminho(MARCA), "w", encoding="utf-8") as fh:
        fh.write((ref or agora()).isoformat(timespec="seconds"))


def destinos():
    """email_destino aceita um endereco, varios separados por virgula, ou uma
    lista JSON. Todos recebem a mesma copia visivel -- nada de Cco, porque quem
    recebe precisa poder responder para os outros."""
    bruto = CFG.get("email_destino") or ""
    itens = bruto if isinstance(bruto, list) else re.split(r"[,;\s]+", str(bruto))
    return [e.strip() for e in itens if e.strip() and "@" in e]


def via_claude(destino, assunto):
    exe = shutil.which("claude")
    if not exe:
        return False
    prompt = (
        f"Leia o arquivo {caminho('ultimo_parecer.html')} e envie o conteudo HTML "
        f"exatamente como esta, sem alterar nenhum numero e sem reescrever o texto, "
        f"por e-mail para {destino}. Use como assunto exatamente esta linha: {assunto}\n"
        f"Nao acrescente comentarios seus ao corpo. Responda apenas ENVIADO, "
        f"ou FALHOU seguido do motivo."
    )
    try:
        r = subprocess.run(
            [exe, "-p", prompt, "--allowedTools", "Read",
             "mcp__claude_ai_Gmail__send_message"],
            capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        print("claude: tempo esgotado", file=sys.stderr)
        return False
    saida = (r.stdout or "").strip()
    if "ENVIADO" in saida.upper():
        print("enviado via Claude Code")
        return True
    print(f"claude nao enviou: {saida[:200] or (r.stderr or '')[:200]}", file=sys.stderr)
    return False


def via_smtp(destino, assunto, corpo):
    user = os.environ.get("RASTREIO_SMTP_USER")
    senha = os.environ.get("RASTREIO_SMTP_PASS")
    if not (user and senha):
        return False
    smtp = CFG.get("smtp", {})
    msg = EmailMessage()
    msg["Subject"] = assunto
    msg["From"] = smtp.get("remetente") or user
    msg["To"] = destino
    msg.set_content("Seu leitor de e-mail nao suporta HTML. "
                    "O relatorio esta em ultimo_parecer.html.")
    msg.add_alternative(corpo, subtype="html")
    try:
        with smtplib.SMTP(smtp.get("host", "smtp.gmail.com"),
                          int(smtp.get("porta", 587)), timeout=60) as s:
            s.starttls()
            s.login(user, senha)
            s.send_message(msg)
    except Exception as e:
        print(f"FALHOU no SMTP: {type(e).__name__}: {e}", file=sys.stderr)
        return False
    print("enviado via SMTP")
    return True


def main():
    forcar = "--forcar" in sys.argv
    ok, motivo = na_hora()
    if not (ok or forcar):
        print(f"boletim represado: {motivo}")
        return 0
    print(f"boletim: {motivo}" + (" (forcado na mao)" if forcar and not ok else ""))
    lista = destinos()
    if not lista:
        print("email_destino vazio no config.json — relatorio salvo em "
              + caminho("ultimo_parecer.html"))
        return 0
    destino = ", ".join(lista)
    corpo, assunto = ler("ultimo_parecer.html"), ler("ultimo_assunto.txt")
    if via_claude(destino, assunto) or via_smtp(destino, assunto, corpo):
        marcar_enviado()
        return 0
    print("Nenhum caminho de envio disponivel. Instale o Claude Code ou defina "
          "RASTREIO_SMTP_USER e RASTREIO_SMTP_PASS. O relatorio esta salvo em "
          + caminho("ultimo_parecer.html"), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
