"""Estatistica da serie de precos: limpeza de ruido, tendencia e gatilho de compra.

Separado do resto de proposito: e' aqui que mora todo o julgamento numerico,
entao e' aqui que se olha quando se desconfia de um parecer.
"""
import statistics as st


def limpar_ruido(serie, tolerancia=0.35, janela=5):
    """Remove pontos isolados que destoam da vizinhanca.

    O grafico do Google traz, de vez em quando, um ponto solitario 60% ou 70%
    abaixo dos vizinhos, que volta ao patamar no dia seguinte. Nao e' tarifa
    que alguem conseguiu comprar: e' ruido. Mantido na serie, ele rebaixa o
    minimo e distorce o percentil, fazendo parecer que existe um piso que
    nunca esteve la'.

    Devolve (serie_limpa, indices_removidos).
    """
    if len(serie) < janela:
        return list(serie), []
    limpa, removidos = [], []
    for i, v in enumerate(serie):
        ini, fim = max(0, i - janela // 2), min(len(serie), i + janela // 2 + 1)
        vizinhos = [serie[j] for j in range(ini, fim) if j != i]
        if not vizinhos:
            limpa.append(v)
            continue
        med = st.median(vizinhos)
        if med and abs(v - med) / med > tolerancia:
            removidos.append(i)
        else:
            limpa.append(v)
    return limpa, removidos


def tendencia(serie):
    """Inclinacao da reta de minimos quadrados, em unidade de moeda por dia."""
    n = len(serie)
    if n < 3:
        return 0.0
    xs = list(range(n))
    mx, my = sum(xs) / n, sum(serie) / n
    den = sum((x - mx) ** 2 for x in xs)
    return (sum((x - mx) * (y - my) for x, y in zip(xs, serie)) / den) if den else 0.0


def percentil(serie, q):
    if not serie:
        return None
    s = sorted(serie)
    if len(s) == 1:
        return s[0]
    pos = (len(s) - 1) * q / 100
    baixo, alto = int(pos), min(int(pos) + 1, len(s) - 1)
    return s[baixo] + (s[alto] - s[baixo]) * (pos - baixo)


def ajuste_linear(serie):
    """Reta de minimos quadrados + qualidade do ajuste.

    Devolve (intercepto, inclinacao, desvio dos residuos, r2). O r2 diz o
    quanto da variacao a tendencia explica: perto de 0, o que manda e' o ruido
    do dia a dia, e a tendencia nao deve ser levada a serio como previsao.
    """
    n = len(serie)
    if n < 3:
        return (serie[0] if serie else 0), 0.0, 0.0, 0.0
    xs = list(range(n))
    mx, my = sum(xs) / n, sum(serie) / n
    den = sum((x - mx) ** 2 for x in xs)
    b = (sum((x - mx) * (y - my) for x, y in zip(xs, serie)) / den) if den else 0.0
    a = my - b * mx
    res = [y - (a + b * x) for x, y in zip(xs, serie)]
    ss_res, ss_tot = sum(e * e for e in res), sum((y - my) ** 2 for y in serie)
    r2 = (1 - ss_res / ss_tot) if ss_tot else 0.0
    return a, b, (st.pstdev(res) if n > 1 else 0.0), r2


def resumo(serie_bruta, preco_atual, dias_recentes=21):
    """Tudo que a decisao precisa, a partir da serie historica do Google."""
    serie, ruido = limpar_ruido(serie_bruta)
    if not serie:
        return None
    recente = serie[-dias_recentes:]
    inc = tendencia(serie)
    a, b, sigma, r2 = ajuste_linear(serie)
    previsto = a + b * (len(serie) - 1)
    # z: quantos desvios o preco de hoje esta' ABAIXO do que a tendencia previa.
    # E' esta a medida que funciona numa serie que sobe -- comparar com o
    # patamar bruto das ultimas semanas faz a regua nunca disparar.
    z = (preco_atual - previsto) / sigma if sigma else 0.0
    return {
        "previsto": previsto, "z": z, "sigma": sigma, "r2": r2,
        "n": len(serie), "n_ruido": len(ruido),
        "mediana": st.median(serie),
        "min_real": min(serie),          # ja' sem os pontos de ruido
        "max": max(serie),
        "p25_recente": percentil(recente, 25),
        "mediana_recente": st.median(recente),
        "min_recente": min(recente),
        "dias_recentes": len(recente),
        "percentil_atual": round(100 * sum(1 for x in serie if x <= preco_atual) / len(serie)),
        "tendencia_dia": inc,
        "tendencia_mes": inc * 30,
        "tendencia_recente_dia": tendencia(recente),
        "volatilidade": st.pstdev(serie) if len(serie) > 1 else 0,
        "e_minimo_recente": preco_atual <= min(recente),
    }


def _num(v):
    """Formata inteiro no padrao pt-BR sem estragar a pontuacao da frase."""
    return f"{abs(v):,.0f}".replace(",", ".")


def decidir(preco, r, dias_ate_voo):
    """Regua calibrada para alta temporada, quando esperar preco baixo e' ilusao.

    A pergunta deixa de ser "esta barato?" e passa a ser "hoje esta' barato
    PARA O MOMENTO?". A referencia e' o desvio em relacao a propria tendencia
    da serie, e nao o patamar absoluto: numa rota que sobe 450 por mes,
    qualquer regra ancorada no passado recente simplesmente nunca dispara.
    """
    if not r:
        return "sem base histórica", "#8a8a8a", "Não há série para comparar."

    z, tm, r2 = r["z"], r["tendencia_mes"], r["r2"]
    sobe, cai = tm > 90, tm < -90
    conf = "clara" if r2 >= 0.4 else ("fraca" if r2 >= 0.15 else "sem tendência definida")

    if z <= -0.8:
        cor, v = "#0a7d32", "COMPRE — dia bem abaixo do esperado"
        p = f"Está {_num(r['previsto'] - preco)} abaixo do que a série vinha praticando."
        if r["e_minimo_recente"]:
            p += f" É o menor valor dos últimos {r['dias_recentes']} dias."
    elif z <= -0.25:
        cor, v = "#2e7d32", "BOM DIA — abaixo do esperado"
        p = (f"Cerca de {_num(r['previsto'] - preco)} abaixo do esperado para hoje. "
             f"Não é o fundo, mas é um dos dias melhores.")
    elif z <= 0.8:
        cor, v = "#8a6d00", "DIA COMUM — nem bom nem ruim"
        p = "Preço na média do que a série vem praticando. Vale esperar um dia melhor."
    else:
        cor, v = "#b3261e", "DIA RUIM — acima do esperado"
        p = f"Cerca de {_num(preco - r['previsto'])} acima do esperado para hoje."

    if sobe:
        p += (f" A série sobe cerca de {_num(tm)} por mês (tendência {conf}), "
              f"então esperar tem custo.")
    elif cai:
        p += f" A série vem cedendo {_num(tm)} por mês (tendência {conf})."
    else:
        p += " A série está estável no período."

    if dias_ate_voo is not None and dias_ate_voo <= 45 and sobe:
        p += (f" Faltam {dias_ate_voo} dias para o voo: nesta faixa a tarifa costuma "
              f"acelerar, e a margem para esperar é pequena.")
    return v, cor, p
