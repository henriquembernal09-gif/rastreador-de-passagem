#!/usr/bin/env python3
"""Coleta anonima de tarifas no Google Voos.

Anti-rastreio: cada busca roda num navegador efemero, criado do zero e
destruido no fim. Sem perfil, sem login, sem cookie herdado, sem storage_state.
A ordem das buscas e' embaralhada e ha' intervalo aleatorio entre elas.

Uso:  python coletar.py            -> todos os combos do config.json
      python coletar.py 26dez-03jan -> apenas esse combo
"""
import csv, json, os, random, re, sys, time

from fast_flights import FlightData, Passengers, create_filter
from playwright.sync_api import sync_playwright

from comum import BASE, carregar_config, caminho, agora, voo_aceito

CFG = carregar_config()
SO = set(sys.argv[1:])
MIN_VOOS_TOTAL = int(CFG.get("min_voos", 40))   # abaixo disto a lista quase
                                                # certamente nao terminou de expandir

CSV_PATH = caminho("historico.csv")
JSON_DIR = caminho("coletas")
os.makedirs(JSON_DIR, exist_ok=True)

CAMPOS = ["ts", "combo", "ida", "volta", "janela_ida",
          "preco_min_janela", "preco_min_geral", "n_voos_janela", "n_voos_total",
          "melhor_partida", "melhor_chegada", "melhor_cia", "melhor_duracao",
          "melhor_rota", "melhor_escalas",
          "volta_partida", "volta_chegada", "volta_cia", "volta_duracao",
          "volta_rota", "volta_escalas", "veredito_google",
          "faixa_tipica_min", "faixa_tipica_max", "n_pontos_hist", "erro"]


def build_url(combo):
    """Serve os dois formatos: combo com 'volta' e' ida e volta, sem 'volta' e'
    so ida. Manter um coletar.py unico e' de proposito -- em 06/09/2026 as duas
    copias divergiram sem ninguem notar e uma sobrescreveu a outra."""
    pernas = [FlightData(date=combo["ida"], from_airport=CFG["origem"],
                         to_airport=CFG["destino"])]
    if combo.get("volta"):
        pernas.append(FlightData(date=combo["volta"], from_airport=CFG["destino"],
                                 to_airport=CFG["origem"]))
    f = create_filter(
        flight_data=pernas,
        trip="round-trip" if len(pernas) == 2 else "one-way",
        seat=CFG.get("classe", "economy"),
        passengers=Passengers(adults=CFG.get("adultos", 1)),
        max_stops=CFG.get("max_escalas"),
    )
    return ("https://www.google.com/travel/flights?tfs=" + f.as_b64().decode("utf-8")
            + f"&curr={CFG.get('moeda','BRL')}&hl=pt-BR&gl=BR")


RE_HORA = re.compile(r"^\d{1,2}:\d{2}(\+\d)?$")
# aceita R$, US$, €, £, CA$, A$, ¥ ... e nao so' o real
MOEDA = r"(?:R\$|US\$|CA\$|A\$|NZ\$|HK\$|[€£¥₩₪₹]|\$)"
RE_PRECO = re.compile(MOEDA + r"\s*([\d.,]+)")


def para_int(txt):
    """'3.362' -> 3362 ; '1.234,50' -> 1234 ; '1,234' -> 1234"""
    txt = re.sub(r"[.,]\d{2}$", "", txt.strip())
    return int(re.sub(r"[^\d]", "", txt) or 0)
RE_ROTA = re.compile(r"\b([A-Z]{3})[–\-]([A-Z]{3})\b")


def parse_card(texto):
    linhas = [l.strip() for l in texto.split("\n") if l.strip() and l.strip() != "–"]
    horas = [l for l in linhas if RE_HORA.match(l)]
    if len(horas) < 2:
        return None
    m = RE_PRECO.search(texto)
    if not m:
        return None
    d = {"partida": horas[0], "chegada": horas[1], "preco": para_int(m.group(1))}
    r = RE_ROTA.search(texto)
    d["rota"] = f"{r.group(1)}-{r.group(2)}" if r else ""
    if "Sem escalas" in texto:
        d["escalas"] = "direto"
    else:
        e = re.search(r"(\d+)\s+parada", texto)
        d["escalas"] = f"{e.group(1)} parada" if e else "?"
    dur = re.search(r"(\d+\s*h(?:\s*\d+\s*min)?|\d+\s*min)", texto)
    d["duracao"] = dur.group(1).strip() if dur else ""
    idx = linhas.index(horas[1]) if horas[1] in linhas else 1
    cia = ""
    for l in linhas[idx + 1:]:
        if RE_PRECO.search(l) or RE_ROTA.search(l):
            break
        if re.match(r"^\d+\s*h", l) or "min" in l or "CO2" in l:
            continue
        cia = l.split("Operado por")[0].strip()
        break
    d["cia"] = cia
    return d


def abrir_navegador(pw):
    """Usa o Google Chrome se existir; senao o Chromium baixado pelo Playwright."""
    args = ["--disable-blink-features=AutomationControlled"]
    try:
        return pw.chromium.launch(channel="chrome", headless=True, args=args)
    except Exception:
        return pw.chromium.launch(headless=True, args=args)



# Cache da rodada: url -> resultado bruto da busca.
# Dois combos com a mesma URL (mesmas datas, mesma rota) sao duas leituras da
# MESMA pagina -- muda so' o filtro local de janela/companhia. Buscar duas vezes
# nao traria informacao nova e dobraria a exposicao ao captcha, que e' o risco
# real de coletar de um IP de datacenter.
CACHE_BUSCA = {}


def so_horario(janela):
    """A janela sem o filtro de companhia. E' o que da' para aplicar durante a
    navegacao: a cia so' e' conferida depois, combo a combo, sobre o mesmo
    material -- senao cada combo exigiria a sua propria ida ao Google."""
    return {k: v for k, v in (janela or {}).items() if k != "cias"}


def ler_cards(pg):
    voos = []
    cards = pg.locator('li[class*="pIav2d"]')
    for i in range(cards.count()):
        try:
            v = parse_card(cards.nth(i).inner_text())
        except Exception:
            v = None
        if v:
            voos.append(v)
    return voos


def fechar_voltas(pg, idas, janela_volta, max_idas):
    """Numa reserva de ida e volta o Google lista as IDAS, e o preco so' fecha
    quando se escolhe a volta. Entao aqui se clica em cada ida candidata, le a
    tela de voltas -- onde o preco ja' e' o TOTAL da reserva -- e volta.

    E' o unico jeito de responder "ida a' tarde E volta de manha na mesma
    compra". Sem isto o numero do e-mail era o total minimo com qualquer volta,
    inclusive a que pousa de madrugada.
    """
    pares = []
    for n, ida in enumerate(idas[:max_idas]):
        try:
            alvo = pg.locator('li[class*="pIav2d"]').nth(ida["indice"])
            alvo.click(timeout=15000)
            pg.wait_for_timeout(4500)
            voltas = [v for v in ler_cards(pg) if voo_aceito(v, janela_volta)]
            if voltas:
                pares.append({"ida": ida, "voltas": voltas})
            pg.go_back(wait_until="domcontentloaded", timeout=45000)
            pg.wait_for_selector('li[class*="pIav2d"]', timeout=45000)
            pg.wait_for_timeout(2500)
        except Exception as e:
            print(f"  ! volta da ida {ida.get('partida')}: "
                  f"{type(e).__name__}", flush=True)
            try:
                pg.go_back(wait_until="domcontentloaded", timeout=45000)
                pg.wait_for_selector('li[class*="pIav2d"]', timeout=45000)
            except Exception:
                return pares   # perdeu a lista de idas: melhor sair com o que tem
    return pares


def buscar(pw, url, janela_ida=None, janela_volta=None, max_idas=8):
    """Uma ida ao Google Voos. Devolve o bruto, sem saber de companhia nenhuma."""
    out = {"voos": [], "hist": [], "pares": [], "veredito": "", "faixa_min": "",
           "faixa_max": "", "erro": ""}
    browser = abrir_navegador(pw)
    try:
        ctx = browser.new_context(locale="pt-BR", timezone_id="America/Sao_Paulo",
                                  viewport={"width": 1500, "height": 1600},
                                  storage_state=None)
        ctx.clear_cookies()
        pg = ctx.new_page()
        pg.goto(url, wait_until="domcontentloaded", timeout=90000)
        pg.wait_for_selector('li[class*="pIav2d"]', timeout=60000)

        # a pagina mostra um preco provisorio antes de terminar: espera estabilizar
        anterior, estavel = None, 0
        for _ in range(20):
            pg.wait_for_timeout(1500)
            try:
                atual = pg.locator('li[class*="pIav2d"]').first.inner_text()
            except Exception:
                atual = None
            if atual and atual == anterior:
                estavel += 1
                if estavel >= 2:
                    break
            else:
                estavel = 0
            anterior = atual

        for _ in range(10):
            try:
                btn = pg.get_by_role("button", name="Mostrar mais voos")
                if btn.count():
                    btn.first.click(timeout=6000)
                    pg.wait_for_timeout(2500)
                else:
                    break
            except Exception:
                break

        for i, v in enumerate(ler_cards(pg)):
            v["indice"] = i
            out["voos"].append(v)

        # painel "Informacoes de preco": veredito, faixa tipica e serie diaria.
        # Sem ele nao ha percentil, e sem percentil o parecer perde a regua --
        # entao vale insistir algumas vezes.
        for _ in range(3):
            try:
                if pg.get_by_text("Histórico de preços para essa pesquisa",
                                  exact=False).count():
                    break
                alvo = pg.get_by_text("Ver histórico de preços", exact=False)
                if alvo.count():
                    alvo.first.click(timeout=8000)
                pg.wait_for_selector("text=Histórico de preços para essa pesquisa",
                                     timeout=15000)
                break
            except Exception:
                pg.wait_for_timeout(3000)
        pg.wait_for_timeout(3000)
        body = pg.inner_text("body")
        vg = (re.search(r"Os preços da pesquisa estão ([^\n]+)", body)
              or re.search(r"Os preços estão ([^\n]+)", body))
        out["veredito"] = vg.group(1).strip().rstrip(".") if vg else ""
        faixa = re.search(r"geralmente custam " + MOEDA + r"\s*([\d.,]+)\s*a\s*([\d.,]+)", body)
        if faixa:
            out["faixa_min"] = para_int(faixa.group(1))
            out["faixa_max"] = para_int(faixa.group(2))
        try:
            serie = pg.evaluate("""() => {
              const out = [];
              document.querySelectorAll('[aria-label]').forEach(e => {
                const m = (e.getAttribute('aria-label')||'')
                  .match(/^H[aá] (\\d+) dias? - \\D{0,4}\\s*([\\d.,]+)$/);
                if (m) out.push([parseInt(m[1]),
                                 parseInt(m[2].replace(/[.,]\\d{2}$/,'').replace(/\\D/g,''))]);
              });
              return out;
            }""")
        except Exception:
            serie = []
        vistos_h = set()
        for dias, preco in sorted(serie, reverse=True):
            if dias not in vistos_h:
                vistos_h.add(dias)
                out["hist"].append({"dias_atras": dias, "preco": preco})
        if janela_volta:
            candidatas = sorted((v for v in out["voos"]
                                 if voo_aceito(v, so_horario(janela_ida))),
                                key=lambda v: (v["preco"], v["partida"]))
            out["pares"] = fechar_voltas(pg, candidatas, so_horario(janela_volta),
                                         max_idas)
        ctx.clear_cookies()
        ctx.close()
    except Exception as e:
        out["erro"] = f"{type(e).__name__}: {e}"[:300]
    finally:
        browser.close()
    return out


def peso_busca(b):
    return (1 if b["hist"] else 0, len(b["voos"]))


def coletar_um(pw, combo, usar_cache=True):
    linha = {c: "" for c in CAMPOS}
    linha.update({"ts": agora().isoformat(timespec="seconds"), "combo": combo["id"],
                  "ida": combo["ida"], "volta": combo.get("volta", ""),
                  "janela_ida": json.dumps(combo["janela_ida"], ensure_ascii=False)})
    url = build_url(combo)
    janela_volta = combo.get("janela_volta") or {}
    chave = (url,
             json.dumps(so_horario(combo["janela_ida"]), sort_keys=True),
             json.dumps(so_horario(janela_volta), sort_keys=True))
    bruto = CACHE_BUSCA.get(chave) if usar_cache else None
    if bruto is None:
        bruto = buscar(pw, url, combo["janela_ida"], janela_volta,
                       int(CFG.get("max_idas_testadas", 8)))
        # so' guarda busca boa, e so' substitui a guardada por uma melhor:
        # senao o combo seguinte herda o fracasso do primeiro e a rodada
        # inteira morre por causa de um timeout que era passageiro.
        if not bruto["erro"] and bruto["voos"]:
            guardado = CACHE_BUSCA.get(chave)
            if guardado is None or peso_busca(bruto) > peso_busca(guardado):
                CACHE_BUSCA[chave] = bruto
    else:
        print(f"  . {combo['id']}: reaproveitando a busca ja' feita nesta rodada",
              flush=True)
    voos, hist = bruto["voos"], bruto["hist"]
    linha["veredito_google"] = bruto["veredito"]
    linha["faixa_tipica_min"] = bruto["faixa_min"]
    linha["faixa_tipica_max"] = bruto["faixa_max"]
    linha["n_pontos_hist"] = len(hist)
    linha["erro"] = bruto["erro"]

    vistos, unicos = set(), []
    for v in voos:
        k = (v["partida"], v["chegada"], v["cia"], v["preco"], v["rota"])
        if k not in vistos:
            vistos.add(k)
            unicos.append(v)
    janela = [v for v in unicos if voo_aceito(v, combo["janela_ida"])]
    linha["n_voos_total"] = len(unicos)
    linha["n_voos_janela"] = len(janela)
    if unicos:
        linha["preco_min_geral"] = min(v["preco"] for v in unicos)

    if combo.get("janela_volta"):
        # Viagem fechada: o preco e' o da tela de voltas, que ja' e' o TOTAL da
        # reserva. `mesma_cia` existe porque uma reserva com ida Gol e volta Azul
        # e' duas passagens com cara de uma -- ele pediu ida e volta pela mesma
        # companhia, e o Google mistura sem avisar.
        exige_mesma = bool(combo.get("mesma_cia"))
        viagens = []
        for par in bruto.get("pares", []):
            ida = par["ida"]
            if not voo_aceito(ida, combo["janela_ida"]):
                continue
            for volta in par["voltas"]:
                if not voo_aceito(volta, combo.get("janela_volta")):
                    continue
                if exige_mesma:
                    a, b = (ida.get("cia") or "").upper(), (volta.get("cia") or "").upper()
                    if a and b and a.split()[0] != b.split()[0]:
                        continue
                viagens.append((volta["preco"], ida, volta))
        if viagens:
            preco, ida, volta = min(viagens, key=lambda x: (x[0], x[1]["partida"]))
            linha["preco_min_janela"] = preco
            for k in ("partida", "chegada", "cia", "duracao", "rota", "escalas"):
                linha["melhor_" + k] = ida[k]
                linha["volta_" + k] = volta[k]
            detalhe = {"voos": [dict(v, preco=p) for p, _, v in
                                sorted(viagens, key=lambda x: x[0])[:12]],
                       "viagens": [{"ida": i, "volta": v, "total": p}
                                   for p, i, v in sorted(viagens, key=lambda x: x[0])[:12]],
                       "historico": hist}
            return linha, detalhe
        if not linha["erro"]:
            linha["erro"] = "nenhuma combinacao ida+volta atende as duas janelas"
        return linha, {"voos": [], "viagens": [], "historico": hist}

    if janela:
        melhor = min(janela, key=lambda v: (v["preco"], v["partida"]))
        linha["preco_min_janela"] = melhor["preco"]
        for k in ("partida", "chegada", "cia", "duracao", "rota", "escalas"):
            linha["melhor_" + k] = melhor[k]
    elif not linha["erro"]:
        linha["erro"] = "nenhum voo atende a janela de horario"
    return linha, {"voos": sorted(janela, key=lambda v: v["preco"])[:12], "historico": hist}


def coletar_com_retry(pw, combo, tentativas=3):
    melhor = None
    for t in range(1, tentativas + 1):
        linha, top = coletar_um(pw, combo, usar_cache=(t == 1))
        completo = (linha["preco_min_janela"] != ""
                    and linha["n_voos_total"] >= MIN_VOOS_TOTAL
                    and linha["n_pontos_hist"])
        # prefere a tentativa que trouxe historico; depois, a que viu mais voos
        def peso(l):
            return (1 if l["n_pontos_hist"] else 0, l["n_voos_total"])
        if melhor is None or peso(linha) > peso(melhor[0]):
            melhor = (linha, top)
        if completo:
            return linha, top
        motivo = (linha["erro"] or ("sem serie historica" if not linha["n_pontos_hist"]
                  else f"lista incompleta ({linha['n_voos_total']} voos)"))
        print(f"  ! {combo['id']} tentativa {t}/{tentativas}: {motivo[:90]}", flush=True)
        if t < tentativas:
            time.sleep(random.uniform(20, 45))
    l = melhor[0]
    if l["preco_min_janela"] != "":
        if l["n_voos_total"] < MIN_VOOS_TOTAL:
            l["erro"] = f"lista possivelmente incompleta ({l['n_voos_total']} voos)"
        elif not l["n_pontos_hist"]:
            l["erro"] = "sem série histórica: parecer sem percentil"
    return melhor


def gravar_linha(l):
    """Grava UMA leitura no CSV, na hora. Em 06/09/2026 uma rodada travou no
    segundo combo e levou junto a leitura do primeiro, que ja tinha visto o
    preco cair 45%. Nada de segurar dado bom esperando o resto da rodada."""
    novo = not os.path.exists(CSV_PATH)
    with open(CSV_PATH, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CAMPOS)
        if novo:
            w.writeheader()
        w.writerow(l)
        fh.flush()
        os.fsync(fh.fileno())


def gravar_json(stamp, linhas, detalhe):
    """Reescrito a cada combo, para o parecer sempre achar a coleta parcial."""
    caminho_json = os.path.join(JSON_DIR, f"{stamp}.json")
    tmp = caminho_json + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"ts": agora().isoformat(timespec="seconds"),
                   "resumo": sorted(linhas, key=lambda l: l["combo"]),
                   "detalhe": detalhe}, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, caminho_json)


def main():
    combos = [c for c in CFG["combos"] if not SO or c["id"] in SO]
    if not combos:
        raise SystemExit(f"nenhum combo bate com {sorted(SO)}")
    random.shuffle(combos)
    linhas, detalhe = [], {}
    stamp = agora().strftime("%Y%m%d-%H%M")
    with sync_playwright() as pw:
        for c in combos:
            l, top = coletar_com_retry(pw, c)
            linhas.append(l)
            detalhe[c["id"]] = top
            print(f"[{l['combo']}] min_janela={l['preco_min_janela']} "
                  f"voos={l['n_voos_janela']}/{l['n_voos_total']} "
                  f"google='{l['veredito_google']}' erro={l['erro']}", flush=True)
            gravar_linha(l)
            gravar_json(stamp, linhas, detalhe)
            if c is not combos[-1]:
                time.sleep(random.uniform(6, 18))

    print("OK ->", CSV_PATH)
    return 0 if any(l["preco_min_janela"] != "" for l in linhas) else 1


if __name__ == "__main__":
    sys.exit(main())
