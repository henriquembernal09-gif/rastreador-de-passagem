#!/usr/bin/env python3
"""Gatilho de oportunidade. Roda logo depois da coleta, antes do relatorio.

Nao espera o parecer completo de proposito: o parecer depende da serie
historica do Google, que falha com frequencia, e uma queda de 45% nao precisa
de percentil para ser obvia.

Dispara quando, contra a leitura anterior do MESMO combo:
  - o preco caiu pelo menos `alerta.queda_pct` (padrao 15%), ou
  - o preco ficou abaixo de `alerta.piso`, se houver piso no config.

Anti-repeticao: depois de alertar um combo, so alerta de novo se o preco cair
mais `alerta.reforco_pct` abaixo do ultimo alertado, ou se passaram
`alerta.silencio_horas`. Sem isso, um preco baixo estavel viraria spam e voce
para de ler.
"""
import csv, json, os, sys
from datetime import datetime, timedelta

from canal import alertar as enviar
from comum import carregar_config, caminho, agora, dinheiro, simbolo

CFG = carregar_config()
SYM = simbolo(CFG)
A = CFG.get("alerta", {})
ATIVO = A.get("ativo", True)
QUEDA_PCT = float(A.get("queda_pct", 15))
REFORCO_PCT = float(A.get("reforco_pct", 5))
SILENCIO_H = float(A.get("silencio_horas", 12))
PISO = A.get("piso")
ROTULO = {c["id"]: c.get("rotulo", c["id"]) for c in CFG["combos"]}
ESTADO = caminho("alertas_enviados.json")


def ler_estado():
    try:
        with open(ESTADO, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def gravar_estado(e):
    with open(ESTADO, "w", encoding="utf-8") as fh:
        json.dump(e, fh, ensure_ascii=False, indent=1)


def leituras_por_combo():
    """Devolve {combo: [(ts, preco, linha), ...]} em ordem cronologica."""
    p = caminho("historico.csv")
    if not os.path.exists(p):
        return {}
    fora = {}
    with open(p, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if not r.get("preco_min_janela"):
                continue
            try:
                preco = int(r["preco_min_janela"])
            except ValueError:
                continue
            fora.setdefault(r["combo"], []).append((r["ts"], preco, r))
    for v in fora.values():
        v.sort(key=lambda x: x[0])
    return fora


def deve_alertar(cid, preco, anterior, estado):
    """Devolve (bool, motivo) — a regra inteira num lugar so."""
    if anterior is None:
        return False, "primeira leitura"

    queda = 100 * (anterior - preco) / anterior if anterior else 0
    gatilho = None
    if queda >= QUEDA_PCT:
        gatilho = f"caiu {queda:.0f}% desde a leitura anterior"
    elif PISO and preco <= float(PISO):
        gatilho = f"abaixo do piso de {dinheiro(PISO, SYM)}"
    if not gatilho:
        return False, f"variacao de {queda:.0f}%, abaixo do gatilho"

    ant = estado.get(cid)
    if ant:
        try:
            quando = datetime.fromisoformat(ant["ts"])
        except Exception:
            quando = None
        recente = quando and (agora() - quando) < timedelta(hours=SILENCIO_H)
        if recente and preco > ant["preco"] * (1 - REFORCO_PCT / 100):
            return False, "ja alertado ha pouco, sem queda adicional"
    return True, gatilho


def montar(alertas):
    linhas = ["<b>QUEDA DE PRECO</b>",
              f"{CFG.get('origem')}→{CFG.get('destino')} · {agora():%d/%m %H:%M}", ""]
    for a in alertas:
        l = a["linha"]
        linhas.append(f"<b>{dinheiro(a['preco'], SYM)}</b> — {ROTULO.get(a['combo'], a['combo'])}")
        linhas.append(f"era {dinheiro(a['anterior'], SYM)} · {a['motivo']}")
        detalhe = " · ".join(x for x in (
            l.get("melhor_cia"), l.get("melhor_rota"), l.get("melhor_escalas"),
            f"{l.get('melhor_partida','')}→{l.get('melhor_chegada','')}".strip("→"),
        ) if x)
        if detalhe:
            linhas.append(detalhe)
        linhas.append("")
    linhas.append("Preco de tarifa paga no Google Flights. Confira antes de emitir.")
    return "\n".join(linhas).strip()


def main():
    # "alerta": {"ativo": false} desliga so' a interrupcao, nao o rastreio: o
    # boletim por e-mail continua chegando. Serve para a rota ja' comprada, ou
    # para a rota tao estavel que o gatilho de queda nunca dispararia -- alarme
    # que nao toca treina voce a ignorar o que toca.
    if not ATIVO:
        print("alerta desligado no config.json (alerta.ativo = false)")
        return 0
    estado = ler_estado()
    alertas = []
    for cid, leituras in leituras_por_combo().items():
        if not leituras:
            continue
        ts, preco, linha = leituras[-1]
        anterior = leituras[-2][1] if len(leituras) > 1 else None
        ok, motivo = deve_alertar(cid, preco, anterior, estado)
        print(f"[{cid}] {preco} (antes {anterior}): {'ALERTA' if ok else 'silencio'}"
              f" — {motivo}", flush=True)
        if ok:
            alertas.append({"combo": cid, "preco": preco, "anterior": anterior,
                            "motivo": motivo, "linha": linha})

    if not alertas:
        return 0

    via = enviar(montar(alertas), f"Passagem {CFG.get('origem')}→{CFG.get('destino')}")
    if not via:
        print("ALERTA NAO ENTREGUE — nenhum canal respondeu", file=sys.stderr)
        return 1
    for a in alertas:
        estado[a["combo"]] = {"preco": a["preco"], "ts": agora().isoformat(timespec="seconds")}
    gravar_estado(estado)
    print(f"alerta de {len(alertas)} combo(s) enviado via {via}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
