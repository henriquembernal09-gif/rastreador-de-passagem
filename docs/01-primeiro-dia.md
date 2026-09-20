# Primeiro dia

O caminho curto é abrir a pasta no Claude Code e dizer: *"Leia o CLAUDE.md e me ajude a
configurar o rastreador para a minha viagem."* O que segue é o mesmo caminho, na mão.

## 1. Baixar

```bash
git clone <endereço-do-repositório> rastreador-de-passagem
cd rastreador-de-passagem
```

## 2. Criar a sua configuração

```bash
cp config.exemplo.json config.json
```

Abra o `config.json` e mude, no mínimo: `rotulo`, `origem`, `destino`, as datas dentro de
`combos`, `email_destino` e `rastreio_termina_em`. Todo campo que começa com `_` é
explicação e pode ficar onde está.

## 3. Instalar

```bash
./instalar.sh
```

O instalador confere o `config.json`, cria o ambiente Python, baixa o navegador que ele
usa por dentro (~150 MB, só na primeira vez) e agenda a coleta: **launchd** no Mac,
**cron** no Linux. Ele avisa o que agendou.

## 4. Ver funcionando antes de confiar

```bash
./rodada.sh && tail -40 rodada.log
```

Isso faz uma coleta completa na hora. Leva de 3 a 5 minutos. No fim, abra o
`ultimo_parecer.html` no navegador: é exatamente o que vai chegar por e-mail.

Se o e-mail não chegou, é quase sempre uma destas duas coisas: o `claude` não está no
PATH de quem roda o agendamento, ou o conector de Gmail ainda não foi autorizado. Teste
com `claude -p "diga apenas OK"` e depois mande um e-mail de teste por ele.

## 5. Opcional: alerta também no Telegram

```bash
./configurar-telegram.sh
```

Crie o bot antes, falando com o @BotFather no Telegram, e mande uma mensagem para o seu
próprio bot. O alerta por e-mail funciona sem isso; o Telegram é o segundo caminho, para
o caso de o e-mail atrasar.

## 6. Desligar

```bash
./desinstalar.sh
```

Tira o agendamento e preserva o histórico coletado. O rastreador também se desinstala
sozinho na data `rastreio_termina_em`.

## Quando alguma coisa não vai

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| `rodada.log` parado há horas | máquina dormiu, ou agendamento não entrou | conferir `crontab -l` / `launchctl list`; ver a nota sobre máquina que dorme no README |
| "0 voos na janela" | filtro apertado demais, ou não existe voo direto nessa rota | afrouxar a janela de horário, ou aceitar 1 escala |
| erro de import `FlightData` | `fast-flights` subiu para 3.x | `./.venv/bin/pip install "fast-flights==2.2"` |
| e-mail nenhum, nem boletim | `email_destino` vazio, ou `claude` fora do PATH | conferir os dois; `which claude` |
| boletim demais | coleta frequente com boletim a cada rodada | usar `boletim.horarios`, 2x por dia basta |
