#!/usr/bin/env python3
"""Curva de antecedencia da propria rota, medida hoje.

Por que existe: nao ha' fonte publica de tarifa internacional por DATA DE
COMPRA. O DB1B do US DOT e' so' itinerario domestico americano, trimestral e
sem data de compra; a tarifa media da StatCan e' agregada por grupo, sem par
de cidades. O equivalente do ANAC, que serve na rota domestica brasileira,
nao existe para Canada -> EUA.

O que da' para medir: o preco de HOJE para varias datas de voo, todas na mesma
rota, mesmo dia da semana e mesma janela de horario. A diferenca entre elas e'
o efeito de quantos dias faltam para o voo -- que e' a pergunta util aqui:
"comprar a 51 dias do voo e' cedo, tarde, ou no ponto?".

Ressalva, escrita tambem no relatorio: antecedencia e temporada andam juntas.
Uma sexta de dezembro nao e' so' mais distante, e' tambem mais cara por ser
dezembro. Por isso a grade fica curta e ancorada no mesmo dia da semana, e a
leitura e' do FORMATO da curva, nao previsao de preco.

Uso:  python antecedencia.py            -> coleta a grade e escreve o bloco
      python antecedencia.py --bloco    -> so' reescreve o bloco do CSV atual
"""
import csv, os, random, sys, time
import statistics as st
from datetime import date, datetime, timedelta

from playwright.sync_api import sync_playwright


from comum import carregar_config, caminho, agora, dinheiro, simbolo, descreve_janela
from coletar import coletar_um

CFG = carregar_config()
SYM = simbolo(CFG)
ALVO = CFG["combos"][0]          # ancora: a data que interessa, com a janela dela
MIN_ANTECEDENCIA = 8             # abaixo disso o preco e' de balcao, nao de curva

# Dois modos, porque sao duas perguntas diferentes:
#   semanas -> mesmo dia da semana, de N em N semanas. Mede ANTECEDENCIA.
#              So' vale em data sem temporada propria; num reveillon, a data
#              vizinha nao e' comparavel e a leitura sai enviesada.
#   dias    -> dias consecutivos em volta da data alvo. Mede o PREMIO DA DATA
#              dentro da mesma temporada: mudar de 26 para 28 economiza quanto?
CURVA = {"modo": "semanas", "passo": 2, "n_antes": 3, "n_depois": 3}
CURVA.update(CFG.get("curva") or {})

CSV_PATH = caminho("antecedencia.csv")
BLOCO = caminho("antecedencia_bloco.html")
CAMPOS = ["ts", "data_voo", "dias_antec", "preco_janela", "preco_geral",
          "n_voos_janela", "n_voos_total", "melhor_partida", "melhor_cia", "erro"]


def grade():
    alvo = date.fromisoformat(ALVO["ida"])
    hoje = agora().date()
    passo = int(CURVA["passo"])
    unidade = (lambda k: timedelta(weeks=passo * k)) if CURVA["modo"] == "semanas" \
        else (lambda k: timedelta(days=passo * k))
    datas = []
    for k in range(-int(CURVA["n_antes"]), int(CURVA["n_depois"]) + 1):
        d = alvo + unidade(k)
        if (d - hoje).days >= MIN_ANTECEDENCIA:
            datas.append(d)
    return datas


def coletar():
    hoje = agora().date()
    datas = grade()
    print(f"grade: {len(datas)} datas, de {datas[0]} a {datas[-1]}", flush=True)
    linhas = []
    with sync_playwright() as pw:
        for i, d in enumerate(datas):
            combo = {"id": d.isoformat(), "ida": d.isoformat(),
                     "janela_ida": ALVO["janela_ida"]}
            if ALVO.get("volta"):
                combo["volta"] = ALVO["volta"]      # volta fixa: isola o efeito da ida
            l, _ = coletar_um(pw, combo)
            if l["preco_min_janela"] == "" and not l["erro"].startswith("nenhum voo"):
                time.sleep(random.uniform(15, 30))
                l, _ = coletar_um(pw, combo)        # uma segunda chance, so' uma
            linhas.append({
                "ts": agora().isoformat(timespec="seconds"),
                "data_voo": d.isoformat(), "dias_antec": (d - hoje).days,
                "preco_janela": l["preco_min_janela"], "preco_geral": l["preco_min_geral"],
                "n_voos_janela": l["n_voos_janela"], "n_voos_total": l["n_voos_total"],
                "melhor_partida": l["melhor_partida"], "melhor_cia": l["melhor_cia"],
                "erro": l["erro"]})
            print(f"  {d} ({(d-hoje).days:>3}d): janela={l['preco_min_janela'] or '—'} "
                  f"geral={l['preco_min_geral'] or '—'} {l['erro'][:60]}", flush=True)
            if i < len(datas) - 1:
                time.sleep(random.uniform(6, 18))

    novo = not os.path.exists(CSV_PATH)
    with open(CSV_PATH, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CAMPOS)
        if novo:
            w.writeheader()
        w.writerows(linhas)
    return linhas


def ultima_leva():
    if not os.path.exists(CSV_PATH):
        return []
    linhas = list(csv.DictReader(open(CSV_PATH, encoding="utf-8")))
    if not linhas:
        return []
    dia = max(l["ts"][:10] for l in linhas)
    leva = [l for l in linhas if l["ts"][:10] == dia]
    vistos, out = set(), []
    for l in sorted(leva, key=lambda x: x["ts"], reverse=True):   # a mais recente por data
        if l["data_voo"] not in vistos:
            vistos.add(l["data_voo"])
            out.append(l)
    return sorted(out, key=lambda x: x["data_voo"])


def _semana():
    return CURVA["modo"] == "semanas"


def bloco_html():
    leva = ultima_leva()
    validas = [l for l in leva if str(l["preco_janela"]).isdigit()]
    if len(validas) < 3:
        return ""
    alvo_iso = ALVO["ida"]
    precos = {l["data_voo"]: int(l["preco_janela"]) for l in validas}
    p_alvo = precos.get(alvo_iso)
    barato = min(precos.values())
    data_barata = min(precos, key=lambda k: precos[k])

    def br(iso):
        return datetime.fromisoformat(iso).strftime("%d/%m")

    linhas = []
    for l in leva:
        iso = l["data_voo"]
        p = precos.get(iso)
        alvo = iso == alvo_iso
        if p is None:
            cel = (f'<td style="padding:6px 12px;color:#b3261e">— {l["erro"][:40]}</td>'
                   f'<td></td>')
        else:
            if not p_alvo or alvo:
                delta = ""
            else:
                pct = round(100 * (p - p_alvo) / p_alvo)
                delta = "igual" if pct == 0 else f'{"+" if pct > 0 else "−"}{abs(pct)}%'
            cor = "#1e7a3c" if p == barato else "#111"
            cel = (f'<td style="padding:6px 12px;color:{cor};font-weight:'
                   f'{"600" if p == barato else "400"}">{dinheiro(p, SYM)}</td>'
                   f'<td style="padding:6px 12px;color:#888">{delta}</td>')
        marca = ' style="background:#f4f7ff"' if alvo else ""
        rot = f'<b>{br(iso)} — sua data</b>' if alvo else br(iso)
        linhas.append(f'<tr{marca}><td style="padding:6px 12px">{rot}</td>'
                      f'<td style="padding:6px 12px;color:#666">{l["dias_antec"]} dias</td>{cel}</tr>')

    leitura = _leitura(precos, p_alvo, barato, data_barata, validas, br)

    if _semana():
        titulo = "Curva de antecedência da rota"
        dia_sem = datetime.fromisoformat(alvo_iso).strftime("%A")
        traducao = {"Monday": "segundas", "Tuesday": "terças", "Wednesday": "quartas",
                    "Thursday": "quintas", "Friday": "sextas", "Saturday": "sábados",
                    "Sunday": "domingos"}
        sub = (f'Preço de hoje para {traducao.get(dia_sem, "datas")}-feiras '
               if dia_sem in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")
               else f'Preço de hoje para {traducao.get(dia_sem, "datas")} ')
        sub = sub.replace("sábados-feiras", "sábados").replace("domingos-feiras", "domingos")
        col2 = "Antecedência"
        rodape = ('<b>Por que esta tabela existe.</b> Não há dado público de tarifa internacional '
                  'por data de compra — o DB1B do US DOT cobre só itinerário doméstico americano, '
                  'é trimestral e não registra quando o bilhete foi comprado; a tarifa média da '
                  'StatCan é agregada, sem par de cidades. Então em vez de histórico de compra, '
                  'mede-se o preço de hoje ao longo de várias datas de voo. '
                  '<b>Leia o formato, não a previsão:</b> antecedência e temporada andam juntas, '
                  'e uma data de dezembro é mais cara também por ser dezembro.')
    else:
        titulo = "Prêmio da data dentro da temporada"
        sub = "Preço de hoje para cada data de saída "
        col2 = "Dias até o voo"
        rodape = ('<b>Por que esta tabela existe.</b> Numa data de alta temporada não adianta '
                  'comparar com semanas vizinhas: 12/dez não é réveillon, e a diferença seria '
                  'temporada, não antecedência. A pergunta que sobra é a que dá para agir: '
                  '<b>mudar o dia da saída, dentro da mesma viagem, economiza quanto?</b> A volta '
                  'fica fixa em todas as linhas, então a diferença é só do trecho de ida.')

    volta = (f', volta fixa em {br(ALVO["volta"])}' if ALVO.get("volta") else "")
    return f'''
<h3 style="margin:26px 0 4px;font-weight:600;font-size:17px">{titulo}</h3>
<div style="color:#888;font-size:13px;margin-bottom:10px">{sub}{CFG["origem"]} → {CFG["destino"]},
mesma janela ({descreve_janela(ALVO["janela_ida"])}){volta}, mesmo perfil.
Medido em {datetime.fromisoformat(leva[0]["ts"]).strftime("%d/%m")}.</div>
<table style="border-collapse:collapse;width:100%;font-size:14px">
<tr style="text-align:left;color:#666;font-size:11px;letter-spacing:.06em;text-transform:uppercase">
<th style="padding:0 12px 6px">Data do voo</th><th style="padding:0 12px 6px">{col2}</th>
<th style="padding:0 12px 6px">Menor preço na janela</th><th style="padding:0 12px 6px">vs. sua data</th></tr>
{"".join(linhas)}
</table>
<div style="margin-top:10px;padding:12px 14px;background:#fafafa;border-left:3px solid #ddd;font-size:13px;color:#555;line-height:1.55">
{leitura}<br><br>{rodape}
</div>'''


def _leitura(precos, p_alvo, barato, data_barata, validas, br):
    if p_alvo is None:
        return "A data alvo não coletou nesta leva."
    no_piso = [d for d, p in precos.items() if p == barato]
    economia = p_alvo - barato

    if _semana():
        if p_alvo == barato and len(no_piso) >= 3:
            faixa = sorted(int(l["dias_antec"]) for l in validas
                           if precos.get(l["data_voo"]) == barato)
            return (f'<b>Não é uma curva, é um platô.</b> {len(no_piso)} das {len(precos)} datas '
                    f'saem exatamente por {dinheiro(barato, SYM)}, de {faixa[0]} a {faixa[-1]} dias '
                    f'de antecedência. Esse é o piso tarifário publicado na rota, não uma promoção '
                    f'de um dia. Consequência prática: <b>comprar mais cedo não compra mais '
                    f'barato</b>, e esperar não é caro — o que muda o preço é o assento acabar '
                    f'nessa classe tarifária, o que aparece como salto, não como subida gradual.')
        if p_alvo == barato:
            return ('Sua data é <b>a mais barata da grade</b> — com mais ou menos antecedência o '
                    'preço não melhora. Nada indica ganho em esperar.')
        return (f'A data mais barata da grade é <b>{br(data_barata)}</b> a '
                f'{dinheiro(barato, SYM)}, {round(100*economia/barato)}% abaixo da sua. Isso é '
                f'prêmio da <b>data</b>, não da antecedência: serve para saber se a sua é cara '
                f'na rota, não para comprar mais barato.')

    # modo dias: premio da data dentro da mesma temporada
    if p_alvo == barato:
        return (f'<b>Sua data já é a mais barata da janela.</b> Nenhum dia vizinho de saída sai '
                f'por menos que {dinheiro(barato, SYM)} — mudar a viagem não economiza.')
    return (f'Sair em <b>{br(data_barata)}</b> custa {dinheiro(barato, SYM)}, '
            f'<b>{dinheiro(economia, SYM)} a menos</b> que a sua data '
            f'({round(100*economia/p_alvo)}%). Só vale se esse dia servir para você — é a '
            f'economia de mudar a viagem, não de esperar o preço cair.')


if __name__ == "__main__":
    if "--bloco" not in sys.argv:
        coletar()
    b = bloco_html()
    open(BLOCO, "w", encoding="utf-8").write(b)
    print(f"bloco: {len(b)} bytes -> {BLOCO}")
