# Por dentro

Para quem vai mexer no código (ou para o Claude, antes de mexer).

## O caminho de uma rodada

`rodada.sh` é o maestro. Em ordem, com teto de tempo em cada etapa:

1. **Encerramento** — se passou de `rastreio_termina_em`, chama o `desinstalar.sh` e sai.
2. **Lock** — `/tmp/rastreio-passagem.lock`, compartilhado por todos os rastreadores da
   máquina. Espera até 12 minutos pela vez; se não conseguir, pula a rodada. Lock órfão
   (dono morto) é removido sozinho.
3. **Jitter** — espera aleatória de até 3 minutos.
4. **`coletar.py`** — abre o Google Flights num Chromium escondido, lê os cards, aplica as
   janelas, grava **cada combo na hora** no `historico.csv` (com `fsync`).
5. **`alertar.py`** — compara com a leitura anterior e, se caiu além do gatilho, manda o
   alerta pelos canais de `canal.py`. Roda **antes** do parecer de propósito.
6. **`antecedencia.py`** — só se o `antecedencia.csv` tiver mais de 6 dias.
7. **`analisar.py`** — monta o parecer (`ultimo_parecer.html` / `.json`).
8. **`enviar.py`** — manda o boletim, se for a hora do slot.
9. Carimba `ultima_rodada_ok.txt`.

## Como o preço é lido

- Um combo de **só ida**: lê a lista de voos, filtra pela `janela_ida`, guarda o mínimo da
  janela e também o mínimo geral (para você ver o que está abrindo mão).
- Um combo de **ida e volta**: a primeira tela lista as idas. Para cada ida dentro da
  janela (até `max_idas_testadas`), o coletor entra, lê a tela de voltas — onde o preço já
  é o total da reserva —, aplica a `janela_volta` e o `mesma_cia`, e volta com `go_back`.
- A chave de cache da rodada inclui rota, datas e janelas de horário, mas **não** a
  companhia. É isso que faz dois combos com as mesmas datas (com e sem filtro de cia)
  custarem uma única ida ao Google.
- O horário lido de cada card já é local de cada ponta, e o `+1` do card vira `offset_dia`.
  Não se calcula fuso na mão em lugar nenhum.

## As colunas do `historico.csv`

`ts, combo, ida, volta, janela_ida, preco_min_janela, preco_min_geral, n_voos_janela,
n_voos_total, melhor_* (partida, chegada, cia, duracao, rota, escalas), volta_* (idem
para a perna de volta), veredito_google, faixa_tipica_min, faixa_tipica_max,
n_pontos_hist, erro`

`preco_min_janela` é o número que importa: o mais barato **dentro do que você aceita**.
`preco_min_geral` é o mais barato da busca inteira, e serve de contraste.

## O parecer

`estatistica.py` calcula o percentil do preço de hoje dentro da série do próprio
rastreador e a tendência recente; `analisar.py` transforma isso em HTML e num assunto de
e-mail que já diz o essencial na linha do assunto. Se a coleta falhou e o parecer caiu na
leitura anterior, o texto é prefixado com **"DADO DE Xh ATRÁS"** — senão o e-mail diz "bom
dia" com um preço que já não existe.

## Canais

- **Boletim** (`enviar.py`): e-mail pelo `claude -p` usando o conector de Gmail já
  autenticado; se não houver `claude` no PATH, cai para SMTP (precisa de senha, por isso é
  o plano B).
- **Alerta** (`canal.py`): Telegram **e** e-mail com assunto `[QUEDA DE PRECO]`, os dois,
  mais notificação de sistema no Mac. Último recurso: `stderr`, para pelo menos ficar no
  log o que não saiu.

## Agendamento

- **Mac**: launchd, `~/Library/LaunchAgents/com.rastreiopassagem.<rotulo>.plist`,
  preferindo `StartInterval` a horário fixo.
- **Linux**: cron. O minuto é derivado do rótulo (`crc32 % 60`) para dois rastreadores não
  caírem no mesmo minuto. Horários fixos são convertidos do fuso de casa para o fuso do
  sistema na hora de escrever a linha, porque o cron lê a agenda no fuso da máquina (numa
  VPS, quase sempre UTC) e costuma ignorar `CRON_TZ`.
- Cuidado com `%` em linha de cron: sem escapar, ele trunca o comando ali.

## Dependências

`playwright` (o navegador escondido) e `fast-flights==2.2`. O teto da versão é de
propósito: a 3.x renomeou `FlightData` para `FlightQuery` e quebra o import do
`coletar.py`. Quem soltar o teto ajusta o `build_url` junto.
