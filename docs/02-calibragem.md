# Calibragem

Calibrar é responder uma pergunta só: **qual é exatamente a viagem cujo preço eu quero
vigiar?** Tudo o mais é consequência. Um rastreador mal calibrado não erra pouco: ele
mede outra coisa e ainda assim te manda um número com cara de certo.

## 1. Filtre o voo que você compraria de verdade

O preço mais barato da tela quase nunca é o preço do voo que você tomaria. Se você não
pega voo que sai às 5h da manhã, o preço desse voo não é informação.

```json
"janela_ida": {
  "partida": { "modo": "between", "hora_min": "12:00", "hora_max": "19:00" },
  "chegada": { "modo": "before", "hora": "23:00", "offset_dia": 0 },
  "duracao_max_horas": 9,
  "cias": ["LATAM"]
}
```

- `modo`: `any`, `after` (`hora`), `before` (`hora`) ou `between` (`hora_min`/`hora_max`).
- `offset_dia` na chegada: `0` chega no mesmo dia, `1` chega no dia seguinte. É o que
  separa um voo que pousa às 10:45 de hoje de um que pousa às 10:45 de amanhã, depois de
  vinte horas de viagem.
- `duracao_max_horas`: **não pule este quando aceitar escala.** A janela de chegada
  sozinha não distingue um voo direto de um que para sete horas no meio do caminho e
  pousa no mesmo horário.
- `cias`: lista de companhias aceitas. Sem o campo, aceita qualquer uma.
- `max_escalas: 0` é voo direto. Use zero quando direto existir na rota: escala não muda
  só o preço, muda a viagem.

Regra que parece detalhe e não é: **companhia ou duração que a página não deixou ler não
reprova o voo.** É melhor um voo a mais na tabela do que um preço bom descartado porque o
Google mudou o nome de uma classe de CSS.

## 2. Ida e volta é uma coisa só

Se a compra vai ser uma reserva de ida e volta, vigie a reserva, não os trechos.

```json
"ida": "2027-01-16",
"volta": "2027-01-20",
"mesma_cia": true,
"janela_volta": { "partida": { "modo": "between", "hora_min": "05:00", "hora_max": "12:00" } }
```

Numa busca de ida e volta o Google mostra as **idas**, e o preço só fecha quando você
escolhe a volta. O coletor abre cada ida da sua janela, lê a tela de voltas (onde o preço
já é o total da reserva) e volta. `max_idas_testadas` limita quantas ele abre.

`mesma_cia: true` rejeita o par com ida de uma companhia e volta de outra: isso são duas
passagens com cara de uma, e as regras de bagagem e remarcação não são as mesmas.

Somar dois trechos avulsos para estimar a reserva dá errado com frequência. Medido numa
rota doméstica: a mesma viagem custava R$ 1.104 pela soma dos trechos e R$ 1.202 na
reserva real do mesmo dia.

## 3. Meça quanto custa a sua preferência

Crie **dois combos com as mesmas datas**, um com `cias` e outro sem. As duas versões
contam como uma única busca (o coletor reaproveita a leitura), e o boletim passa a
responder: "a preferência pela LATAM custa R$ 326 nesta viagem". Aí a preferência vira
decisão, não hábito.

## 4. Cadência: de quanto em quanto tempo olhar

- `intervalo_minutos: 30` é o padrão bom. Pega queda relâmpago sem martelar o Google.
- Abaixo de 15 minutos você ganha pouco e aumenta o risco de captcha.
- `horarios` fixos (em vez de `intervalo_minutos`) só valem em máquina que não dorme. Em
  laptop, horário fixo vira rajada: ao acordar, o agendador dispara de uma vez tudo que
  perdeu, e duas coletas simultâneas travam uma na outra.
- O programa já espera um tempo aleatório de até 3 minutos antes de coletar. É de
  propósito: agendador dispara no minuto cheio, e minuto cheio todo dia tem cara de robô.

## 5. Boletim: duas vezes por dia, não a cada leitura

```json
"boletim": { "ativo": true, "horarios": ["08:45", "18:45"] }
```

Coletar de 30 em 30 minutos e mandar e-mail a cada coleta dá quinze e-mails numa tarde, e
o resultado prático é você parar de abrir todos. A represa funciona por **slot**: vale o
último horário que já passou, então máquina que ficou desligada acorda e manda um boletim
só, não seis atrasados.

Para ver o boletim fora de hora: `./.venv/bin/python enviar.py --forcar`.

## 6. Alerta: o gatilho que interrompe

```json
"alerta": { "ativo": true, "queda_pct": 15, "reforco_pct": 5, "silencio_horas": 12, "piso": null }
```

- `queda_pct`: queda contra a **leitura anterior** (não contra a série histórica do
  Google, que falha dia sim dia não). 15% é o padrão; 20% se estiver disparando por
  oscilação normal da rota.
- `reforco_pct`: depois de um alerta, só volta a avisar se cair mais essa porcentagem.
- `silencio_horas`: teto de repetição do mesmo aviso.
- `piso`: um preço absoluto abaixo do qual você quer ser avisado sempre, mesmo sem queda
  brusca. Serve para "abaixo de R$ 1.500 eu compro sem pensar".
- `"ativo": false` desliga só a interrupção e mantém o rastreio e o boletim. É o ajuste
  certo para rota já comprada ou para rota tão plana que o gatilho nunca dispararia.

O alerta sai por todos os canais configurados, não pelo primeiro que funcionar. Duplicar
um aviso que acontece poucas vezes por mês custa menos que perder um.

## 7. O parecer precisa de histórico

O veredito ("bom dia", "dia ruim") é o percentil do preço de hoje dentro da série que o
próprio rastreador coletou. Nos primeiros dois ou três dias ele é quase enfeite: com
poucas leituras, tudo é 98% ou 2%. A partir de uma semana ele fica útil.

**Se você mudar o que está sendo medido, corte a série.** Mudou rota, datas, janela de
horário ou filtro de volta: renomeie o `historico.csv` para algo como
`historico-ate-<data>-<o-que-media>.csv` e comece do zero. Série misturada dá percentil
errado e, pior, "queda" que é só mudança de régua.

## 8. Curva de antecedência, uma vez por semana

O `antecedencia.py` mede, no mesmo dia, o preço da mesma rota em várias datas de voo
futuras. Responde "comprar com quanta antecedência sai melhor nesta rota". Achado que se
repete em rota curta com concorrência: costuma dar **platô**. O preço não sobe devagar
conforme a data se aproxima; ele salta quando acaba o assento na classe mais barata. Isso
muda a estratégia: não adianta "comprar cedo", adianta estar olhando quando abre.

Para rota doméstica brasileira existe dado público de verdade, classificado por mês da
**venda**: microdados de tarifas da ANAC (sas.anac.gov.br → Tarifas Aéreas Domésticas).
Para rota internacional não existe equivalente por data de compra; a curva de
antecedência medida no presente é o melhor substituto.

## 9. Mais de uma viagem ao mesmo tempo

Uma pasta por viagem, cada uma com o seu `config.json` e o seu `rotulo`. Elas já se
protegem entre si: o agendamento dá um minuto diferente para cada uma (derivado do
rótulo) e um lock garante que duas coletas nunca rodem juntas. Dois navegadores
escondidos brigando pela mesma máquina transformam três minutos de coleta em horas, e
isso aconteceu de verdade.

Com três ou mais viagens, vale consolidar os boletins num e-mail só. O teto de
notificação é do assunto inteiro, não de cada rastreador.
