# Instruções para o Claude que operar este repositório

**O que é.** Rastreador do preço de uma viagem aérea específica (Google Flights via
Playwright). Coleta em intervalo fixo, grava série histórica, manda boletim 2x/dia e
alerta de queda. Quem usa **não programa**: você é a interface da ferramenta. Fale em
linguagem comum, sem jargão, e não peça para a pessoa editar JSON na mão — pergunte e
edite você.

**Estado do repo.** Recém-clonado não tem `config.json` nem `.venv`: os dois nascem na
instalação. Se `config.json` não existir, a pessoa ainda não instalou.

## Primeira conversa (se não existe config.json)

Entreviste, nesta ordem, uma pergunta por vez, e só então escreva o `config.json` a
partir do `config.exemplo.json`:

1. De onde e para onde. Converta cidade em IATA (São Paulo = `SAO`, ou `GRU` se ele quer
   só Guarulhos). Confirme em voz alta o que entendeu.
2. Datas. **Pergunte se é ida e volta na mesma reserva.** Se for, preencha `volta` e
   `janela_volta` e deixe `mesma_cia: true`. Nunca monte dois rastreadores de trecho para
   uma viagem de ida e volta: a unidade de decisão é a reserva que ele vai comprar.
3. Que voo ele aceita: horário de sair, horário de chegar, direto ou com escala,
   companhia preferida. Traduza isso para `janela_ida`/`janela_volta`/`max_escalas`.
   Se ele tem preferência de companhia, crie **dois combos com as mesmas datas** (com e
   sem o filtro `cias`): mostra quanto custa a preferência e não dobra o número de buscas.
4. Para qual e-mail mandar. Esse e-mail vai para `email_destino`.
5. Até quando vigiar (`rastreio_termina_em`).

Depois rode `./instalar.sh`, depois `./rodada.sh` uma vez na frente dele e mostre o
resultado de `ultimo_parecer.html`. Explique que nos primeiros dias o veredito ainda é
chute: o percentil precisa de histórico.

## Arquivos que importam

- `config.json` — tudo que a pessoa escolheu. É o único arquivo que se edita no uso normal.
- `coletar.py` — abre o Google, filtra pelas janelas, grava cada combo **na hora** no CSV.
  Em ida e volta, clica em cada ida da janela e lê a tela de voltas, onde o preço é o
  total da reserva.
- `alertar.py` + `canal.py` — a interrupção. Rodam **antes** do parecer, de propósito.
- `analisar.py` + `estatistica.py` — o parecer (percentil contra a própria série).
- `enviar.py` — o boletim, represado por horário (`boletim.horarios`).
- `antecedencia.py` — curva de antecedência da rota, no máximo 1x por semana.
- `rodada.sh` — orquestra tudo, com lock, teto de tempo e jitter.
- `instalar.sh` / `desinstalar.sh` — agendamento (launchd no Mac, cron no Linux).

## Decisões travadas (não reabra sem motivo forte)

- **Alerta e boletim nunca no mesmo canal.** Alerta é interrupção, boletim é boletim.
- **Alerta antes do parecer** no `rodada.sh`. Se o e-mail do boletim falhar, o alerta já saiu.
- **Cada combo grava no CSV na hora, com fsync.** Um combo lento não pode levar junto a
  leitura boa dos outros.
- `fast-flights` fixado em `==2.2`: a 3.x renomeou `FlightData` e quebra o import.
- Companhia ou duração ilegível **não** reprova o voo. Melhor um voo a mais na tabela do
  que um preço bom descartado por erro de leitura da página.
- Dois combos com as mesmas datas reaproveitam uma única busca no Google.

## Não mexer

- **Não misture séries de histórico.** Se você mudar o que está sendo medido (filtro de
  volta, janela, rota), o `historico.csv` antigo passa a medir outra coisa: arquive com
  outro nome e comece do zero, senão o percentil mente e sai "queda" que é só mudança de
  régua.
- **Segredo nunca em arquivo do repo.** Telegram vai no Keychain (Mac) ou em
  `~/.rastreio-passagem.env` com permissão 600 (Linux). Nada de token em `config.json`.
- Não troque o agendamento por um script que fica rodando em `while true`: o lock, o teto
  de tempo e o jitter existem por causa de um travamento real de 3h15.

## Como conferir se está vivo

```
tail -20 rodada.log            # última rodada
cat ultima_rodada_ok.txt       # carimbo da última rodada completa
crontab -l | grep rastreio     # Linux: agendamento
launchctl list | grep rastreio # Mac: agendamento
./rodada.sh && tail -40 rodada.log   # roda uma agora, na mão
```

Silêncio não é preço estável: se `ultima_rodada_ok.txt` está velho, o rastreador está
mudo e ninguém foi avisado.

## Camadas da documentação

`README.md` (para quem usa) · `docs/01-primeiro-dia.md` (instalação passo a passo) ·
`docs/02-calibragem.md` (como afinar) · `docs/03-como-funciona.md` (por dentro) ·
`docs/04-licoes.md` (as cicatrizes) · `docs/05-frases-prontas.md` (o que pedir ao Claude).
