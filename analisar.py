#!/usr/bin/env python3
"""Le a ultima coleta e o historico proprio, e emite o parecer.

Todo numero do relatorio sai daqui. Nada e' estimado: os percentis vem da
serie diaria (~60 dias) que o proprio Google publica para cada pesquisa, e as
variacoes vem do CSV das coletas anteriores.
"""
import csv, glob, json, os, sys
from datetime import datetime

from comum import (BASE, carregar_config, caminho, agora, dinheiro, simbolo,
                   descreve_janela)
from estatistica import resumo as resumo_serie, decidir

CFG = carregar_config()
SYM = simbolo(CFG)
ROTULO = {c["id"]: c["rotulo"] for c in CFG["combos"]}
JANELA = {c["id"]: descreve_janela(c["janela_ida"]) for c in CFG["combos"]}
# so' faz sentido falar em "ida e volta" quando os combos tem trecho de volta
TOTAL_ROTULO = ("Total ida e volta" if any(c.get("volta") for c in CFG["combos"])
                else "Preço do trecho")


def _dias_ate(iso):
    try:
        return (datetime.fromisoformat(iso).date() - agora().date()).days
    except Exception:
        return None


DIAS_ATE_VOO = {c["id"]: _dias_ate(c["ida"]) for c in CFG["combos"]}


def percentil(serie, valor):
    if not serie:
        return None
    return round(100 * sum(1 for x in serie if x <= valor) / len(serie))


def ler_csv():
    p = caminho("historico.csv")
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as fh:
        return [r for r in csv.DictReader(fh) if r.get("preco_min_janela")]


def analisar():
    arq = sorted(glob.glob(caminho("coletas", "*.json")))
    if not arq:
        return None
    atual = json.load(open(arq[-1], encoding="utf-8"))
    csvr = ler_csv()
    itens = []

    for l in atual["resumo"]:
        cid = l["combo"]
        if not l.get("preco_min_janela"):
            itens.append({"combo": cid, "rotulo": ROTULO.get(cid, cid),
                          "erro": l.get("erro") or "sem dados"})
            continue
        preco = int(l["preco_min_janela"])
        # A serie historica do Google e' da pesquisa SEM o filtro de horario.
        # Comparar contra ela o preco ja' filtrado inflaria o desvio: parte da
        # diferenca e' o custo da restricao, nao o mercado. Entao a leitura de
        # mercado usa o minimo sem filtro, e o preco exibido e' o que ele paga.
        geral = int(l["preco_min_geral"]) if l.get("preco_min_geral") else preco
        premio = preco - geral
        serie = [h["preco"] for h in
                 sorted(atual["detalhe"].get(cid, {}).get("historico", []),
                        key=lambda h: -h["dias_atras"])]
        r = resumo_serie(serie, geral) if serie else None

        meus = [int(x["preco_min_janela"]) for x in csvr
                if x["combo"] == cid and x["ts"] < l["ts"]]
        delta = preco - meus[-1] if meus else None
        dias_voo = DIAS_ATE_VOO.get(cid)
        veredito, cor, porque = decidir(geral, r, dias_voo)
        if premio > 0:
            porque += (f" Sua janela de horário custa {dinheiro(premio, SYM)} a mais "
                       f"que o voo mais barato do dia.")

        itens.append({
            "combo": cid, "rotulo": ROTULO.get(cid, cid), "preco": preco,
            "veredito": veredito, "cor": cor, "porque": porque, "r": r,
            "geral": geral, "premio": premio,
            "pct": r["percentil_atual"] if r else None,
            "hist_n": r["n"] if r else 0,
            "delta": delta, "dias_voo": dias_voo,
            "meu_min": min(meus + [preco]), "n_leituras": len(meus) + 1,
            "voo": {k: l.get("melhor_" + k, "") for k in
                    ("partida", "chegada", "cia", "duracao", "rota", "escalas")},
            "aviso": l.get("erro", ""),
        })

    ok = [i for i in itens if "preco" in i]
    return {"ts": atual["ts"], "itens": sorted(itens, key=lambda i: i["combo"]),
            "melhor": min(ok, key=lambda i: i["preco"]) if ok else None,
            "n_rodadas": len({r["ts"][:13] for r in csvr})}


def bloco_antecedencia():
    """Escrito por antecedencia.py. Se nao existir, o relatorio sai sem ele."""
    try:
        return open(caminho("antecedencia_bloco.html"), encoding="utf-8").read()
    except Exception:
        return ""


def html(a):
    ts = datetime.fromisoformat(a["ts"]).strftime("%d/%m às %Hh%M")
    fim = CFG.get("rastreio_termina_em", "")
    try:
        dias = max(0, (datetime.fromisoformat(fim).date() - agora().date()).days)
        restam = f" · termina em {datetime.fromisoformat(fim).strftime('%d/%m')} ({dias} dias)"
    except Exception:
        restam = ""
    m = a["melhor"]
    d = dinheiro

    linhas = []
    for i in a["itens"]:
        if "preco" not in i:
            linhas.append(
                f'<tr><td style="padding:10px 12px;border-bottom:1px solid #eee">{i["rotulo"]}</td>'
                f'<td colspan="4" style="padding:10px 12px;border-bottom:1px solid #eee;'
                f'color:#b3261e">falha na coleta: {i["erro"][:70]}</td></tr>')
            continue
        var = ""
        if i["delta"]:
            seta = "▲" if i["delta"] > 0 else "▼"
            cor = "#b3261e" if i["delta"] > 0 else "#0a7d32"
            var = f' <span style="color:{cor};font-size:12px">{seta} {d(abs(i["delta"]), SYM)}</span>'
        v = i["voo"]
        r = i.get("r")
        premio = (f'<br><span style="color:#777;font-size:12px">sem filtro de horário: '
                  f'{d(i["geral"], SYM)}</span>' if i.get("premio") else "")
        if r:
            patamar = (f'{d(r["min_recente"], SYM)} — {d(r["mediana_recente"], SYM)}'
                       f'<br><span style="color:#777;font-size:12px">últimos {r["dias_recentes"]} dias'
                       f' · gatilho {d(r["p25_recente"], SYM)}</span>')
            tm = r["tendencia_mes"]
            ct = "#b3261e" if tm > 90 else ("#0a7d32" if tm < -90 else "#777")
            seta = "▲" if tm > 90 else ("▼" if tm < -90 else "→")
            tend = (f'<span style="color:{ct}">{seta} {d(abs(tm), SYM)}/mês</span>'
                    f'<br><span style="color:#777;font-size:12px">p{r["percentil_atual"]} em {r["n"]} dias'
                    + (f' · {r["n_ruido"]} ruído' if r["n_ruido"] else "") + '</span>')
        else:
            patamar = tend = '<span style="color:#999">—</span>'
        av = (f'<br><span style="color:#b3261e;font-size:12px">⚠ {i["aviso"]}</span>'
              if i.get("aviso") else "")
        linhas.append(f'''<tr>
<td style="padding:11px 12px;border-bottom:1px solid #eee;vertical-align:top">{i["rotulo"]}<br>
  <span style="color:#777;font-size:12px">{v["cia"]} · {v["partida"]}→{v["chegada"]} · {v["rota"]} · {v["escalas"]} · {v["duracao"]}</span></td>
<td style="padding:11px 12px;border-bottom:1px solid #eee;font-size:19px;white-space:nowrap;vertical-align:top"><b>{d(i["preco"], SYM)}</b>{var}{premio}</td>
<td style="padding:11px 12px;border-bottom:1px solid #eee;font-size:13px;white-space:nowrap;vertical-align:top">{patamar}</td>
<td style="padding:11px 12px;border-bottom:1px solid #eee;font-size:13px;white-space:nowrap;vertical-align:top">{tend}</td>
<td style="padding:11px 12px;border-bottom:1px solid #eee;vertical-align:top;color:{i["cor"]};font-weight:600">{i["veredito"]}{av}
  <div style="color:#666;font-weight:400;font-size:12px;margin-top:3px;max-width:290px">{i.get("porque","")}</div></td>
</tr>''')

    if m:
        dv = m.get("dias_voo")
        antec = (f' Faltam <b>{dv} dias</b> para o voo.' if dv else "")
        cab = (f'<div style="font-size:15px;color:#333;line-height:1.5">Melhor opção agora: '
               f'<b>{m["rotulo"]}</b> por <b style="color:{m["cor"]}">{d(m["preco"], SYM)}</b> — '
               f'{m["veredito"].split("—")[0].strip().lower()}.{antec}</div>')
    else:
        cab = '<div style="color:#b3261e">Nenhuma combinação coletou nesta rodada.</div>'

    esc = {0: "somente voo direto", 1: "até 1 conexão"}.get(
        CFG.get("max_escalas"), "sem limite de conexões")
    janelas = " · ".join(sorted({j for j in JANELA.values() if j != "qualquer horário"}))

    return f'''<div style="font-family:-apple-system,Segoe UI,Helvetica,sans-serif;max-width:900px;color:#111">
<div style="font-size:12px;letter-spacing:.09em;text-transform:uppercase;color:#888">Rastreio {CFG["origem"]} → {CFG["destino"]}</div>
<h2 style="margin:4px 0 2px;font-weight:600;font-size:23px">Leitura de {ts}</h2>
<div style="color:#888;font-size:13px;margin-bottom:16px">{esc} · {CFG.get("adultos",1)} adulto(s), {CFG.get("classe","economy")}{" · ida " + janelas if janelas else ""}</div>
{cab}
<table style="border-collapse:collapse;width:100%;margin-top:18px;font-size:14px">
<tr style="text-align:left;color:#666;font-size:11px;letter-spacing:.06em;text-transform:uppercase">
<th style="padding:0 12px 8px">Combinação e melhor voo</th><th style="padding:0 12px 8px">{TOTAL_ROTULO}</th>
<th style="padding:0 12px 8px">Patamar recente</th><th style="padding:0 12px 8px">Tendência</th><th style="padding:0 12px 8px">Parecer</th></tr>
{"".join(linhas)}
</table>
<div style="margin-top:18px;padding:12px 14px;background:#fafafa;border-left:3px solid #ddd;font-size:13px;color:#555;line-height:1.55">
<b>Como ler.</b> Em alta temporada, esperar preço baixo é esperar pelo que não vem — então a régua
não pergunta "está barato?", e sim "este é um bom dia para comprar, dado que caro já está decidido?".
A referência é o <b>patamar das últimas semanas</b>, não o mínimo do período inteiro. O <b>gatilho</b> é o
quartil mais barato desse patamar: preço igual ou abaixo dele é dos melhores dias que a rota vem oferecendo.
A <b>tendência</b> diz quanto a série sobe ou cede por mês — é o custo real de esperar.
A leitura de mercado usa o voo mais barato do dia <i>sem</i> filtro de horário, porque é essa a base da
série do Google; o preço em destaque é o que você realmente pagaria dentro da sua janela.
Pontos isolados que destoam da vizinhança são descartados como ruído e contados na coluna Tendência.
</div>
{bloco_antecedencia()}
<div style="margin-top:10px;color:#999;font-size:12px">
Coleta anônima: navegador efêmero, sem login, sem cookie herdado, contexto destruído a cada busca.
Série histórica publicada pelo Google para cada pesquisa. Rodada {a["n_rodadas"]}{restam}.</div>
</div>'''


HORAS_DADO_VELHO = 2


def assunto(a):
    quando = datetime.fromisoformat(a["ts"])
    ts = quando.strftime("%d/%m %Hh")
    # Se a coleta falhou, o parecer cai na coleta anterior sem avisar. Em
    # 06/09/2026 isso mandou "BOM DIA" com preco que ja nao existia mais.
    # Dado velho tem que se identificar como velho na linha de assunto.
    horas = (agora() - quando).total_seconds() / 3600
    velho = f"DADO DE {horas:.0f}h ATRÁS — " if horas >= HORAS_DADO_VELHO else ""
    m = a["melhor"]
    if not m:
        return f"{CFG['origem']}→{CFG['destino']} {ts} — falha na coleta"
    return (f"{velho}{CFG['origem']}→{CFG['destino']} {ts} — {dinheiro(m['preco'], SYM)} "
            f"({m['rotulo']}) · {m['veredito'].split('—')[0].strip()}")


if __name__ == "__main__":
    a = analisar()
    if not a:
        print("SEM DADOS: rode coletar.py primeiro"); sys.exit(1)
    open(caminho("ultimo_parecer.html"), "w", encoding="utf-8").write(html(a))
    open(caminho("ultimo_assunto.txt"), "w", encoding="utf-8").write(assunto(a) + "\n")
    # O mesmo resumo que vai para o log tambem fica em arquivo: o boletim
    # consolidado precisa do veredito COMBO A COMBO, e ate' 18/09/2026 ele
    # tinha que adivinhar pelo assunto -- que traz so' o do melhor combo, e
    # por isso carimbava "COMPRE" em linha que nao era.
    resumo = {"assunto": assunto(a), "ts": a["ts"],
              "resumo": [{"combo": i["combo"], "preco": i.get("preco"),
                          "pct": i.get("pct"),
                          "veredito": i.get("veredito", i.get("erro"))}
                         for i in a["itens"]]}
    open(caminho("ultimo_parecer.json"), "w", encoding="utf-8").write(
        json.dumps(resumo, ensure_ascii=False, indent=1))
    print(json.dumps(resumo, ensure_ascii=False, indent=1))
