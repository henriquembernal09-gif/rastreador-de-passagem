"""Configuracao e utilitarios compartilhados."""
import json, os, re
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
TZ = datetime.now().astimezone().tzinfo

SIMBOLOS = {"BRL": "R$", "USD": "US$", "EUR": "€", "GBP": "£",
            "ARS": "$", "CLP": "$", "MXN": "$", "JPY": "¥", "CAD": "CA$", "AUD": "A$"}


def carregar_config():
    with open(os.path.join(BASE, "config.json"), encoding="utf-8") as fh:
        cfg = json.load(fh)
    cfg = {k: v for k, v in cfg.items() if not k.startswith("_")}
    faltando = [c for c in ("origem", "destino", "combos") if not cfg.get(c)]
    if faltando:
        raise SystemExit(f"config.json incompleto: falta {', '.join(faltando)}")
    for c in cfg["combos"]:
        c.setdefault("rotulo", c["id"])
        c["janela_ida"] = normalizar_janela(c.get("janela_ida"))
        if c.get("janela_volta"):
            c["janela_volta"] = normalizar_janela(c.get("janela_volta"))
    return cfg


def normalizar_janela(j):
    """Aceita o formato novo {partida:{...}, chegada:{...}} e tambem o antigo,
    em que a regra solta na raiz valia para a partida."""
    if not j:
        return {}
    if ("partida" in j or "chegada" in j or "duracao_max_horas" in j
            or "cias" in j):
        out = {}
        if j.get("partida"):
            out["partida"] = j["partida"]
        if j.get("chegada"):
            ch = dict(j["chegada"])
            ch.setdefault("offset_dia", 0)   # por padrao, chegar no mesmo dia
            out["chegada"] = ch
        if j.get("duracao_max_horas"):
            out["duracao_max_horas"] = float(j["duracao_max_horas"])
        if j.get("cias"):
            out["cias"] = [str(c).strip().upper() for c in j["cias"] if str(c).strip()]
        return out
    return {"partida": j} if j.get("modo", "any") != "any" else {}


def caminho(*partes):
    return os.path.join(BASE, *partes)


def agora():
    return datetime.now(TZ)


def simbolo(cfg):
    return SIMBOLOS.get(cfg.get("moeda", "BRL"), cfg.get("moeda", "BRL"))


def dinheiro(v, sym="R$"):
    """Formata no padrao pt-BR, que e' o locale forcado na pagina."""
    if v is None or v == "":
        return "—"
    return f"{sym} {int(v):,}".replace(",", ".")


def _partes(hora):
    """'00:45+1' -> (45 minutos do dia, 1 dia depois)"""
    m = re.match(r"^(\d{1,2}):(\d{2})(?:\+(\d))?$", hora.strip())
    if not m:
        raise ValueError(f"horario nao reconhecido: {hora}")
    return int(m.group(1)) * 60 + int(m.group(2)), int(m.group(3) or 0)


def _min(txt):
    a, b = txt.split(":")
    return int(a) * 60 + int(b)


RE_DUR = re.compile(r"(?:(\d+)\s*h)?(?:\s*(\d+)\s*min)?")


def duracao_min(txt):
    """'6 h 15 min' -> 375 ; '50 min' -> 50 ; ilegivel -> None.

    Existe para separar escala curta de escala que come a tarde inteira: a
    janela de chegada sozinha aceita um voo que sai as 6h, para 7h em Denver
    e pousa dentro do horario pedido."""
    if not txt:
        return None
    m = RE_DUR.search(txt.strip())
    if not m or not (m.group(1) or m.group(2)):
        return None
    return int(m.group(1) or 0) * 60 + int(m.group(2) or 0)


def _hora_ok(minutos, regra):
    modo = regra.get("modo", "any")
    if modo == "any":
        return True
    if modo == "after":
        return minutos >= _min(regra["hora"])
    if modo == "before":
        return minutos <= _min(regra["hora"])
    if modo == "between":
        return _min(regra["hora_min"]) <= minutos <= _min(regra["hora_max"])
    raise SystemExit(f"modo de janela desconhecido: {modo}")


def voo_aceito(voo, janela):
    """janela: {'partida': {...}, 'chegada': {..., 'offset_dia': N}}

    O offset_dia da chegada e' o que separa um voo que pousa as 10:45 do mesmo
    dia de um que pousa as 10:45 do dia seguinte, depois de 20h de viagem.
    """
    if not janela:
        return True
    if janela.get("partida"):
        minutos, _ = _partes(voo["partida"])
        if not _hora_ok(minutos, janela["partida"]):
            return False
    if janela.get("chegada"):
        regra = janela["chegada"]
        minutos, offset = _partes(voo["chegada"])
        if offset != int(regra.get("offset_dia", 0)):
            return False
        if not _hora_ok(minutos, regra):
            return False
    if janela.get("duracao_max_horas"):
        d = duracao_min(voo.get("duracao", ""))
        # duracao ilegivel nao reprova o voo: melhor um voo a mais no relatorio
        # do que um preco bom descartado por causa do parser.
        if d is not None and d > janela["duracao_max_horas"] * 60:
            return False
    if janela.get("cias"):
        # Mesma filosofia da duracao: cia ilegivel NAO reprova o voo. O nome
        # vem de um <li> do Google e as vezes sai vazio ou como "Varios".
        # Preferir um voo a mais na tabela a perder um preco por causa do parser.
        cia = (voo.get("cia") or "").upper()
        if cia and not any(c in cia for c in janela["cias"]):
            return False
    return True


def _descreve_regra(r):
    modo = r.get("modo", "any")
    return {"any": "qualquer horário",
            "after": f"a partir de {r.get('hora','')}",
            "before": f"até {r.get('hora','')}",
            "between": f"entre {r.get('hora_min','')} e {r.get('hora_max','')}"}.get(modo, modo)


def descreve_janela(j):
    if not j:
        return "qualquer horário"
    partes = []
    if j.get("partida"):
        partes.append(f"sai {_descreve_regra(j['partida'])}")
    if j.get("chegada"):
        off = int(j["chegada"].get("offset_dia", 0))
        dia = {0: " no mesmo dia", 1: " no dia seguinte"}.get(off, f" {off} dias depois")
        partes.append(f"chega {_descreve_regra(j['chegada'])}{dia}")
    if j.get("duracao_max_horas"):
        h = j["duracao_max_horas"]
        partes.append(f"em no máximo {h:g}h de viagem")
    if j.get("cias"):
        partes.append("pela " + "/".join(j["cias"]).title())
    return " e ".join(partes) or "qualquer horário"
