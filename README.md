# Rastreador de passagem

Esta ferramenta vigia o preço de **uma viagem específica** e avisa quando ele cai.
Ela não procura "passagem barata para qualquer lugar": você diz a rota, as datas e o
tipo de voo que aceita, e ela olha esse preço de meia em meia hora, todo dia, até você
comprar.

Você recebe duas coisas diferentes, de propósito:

- **Boletim**, duas vezes por dia: o preço de hoje, o histórico e um parecer dizendo se
  este é um bom dia para comprar. É para ler com calma.
- **Alerta**, raro: só quando o preço cai bastante de uma leitura para a outra. É para
  agir na hora. Chega com o assunto `[QUEDA DE PRECO]`, para você criar um som próprio
  no celular.

Misturar as duas coisas num canal só é o erro que faz a pessoa parar de ler os e-mails
e perder a queda justamente quando ela acontece.

## O que você precisa

- Um computador que **fique ligado** (ver a observação lá embaixo).
- **Claude Code** instalado, com o conector de e-mail (Gmail) já conectado. É por ele
  que o boletim e o alerta são enviados, sem você configurar senha nenhuma.
- Python 3 (já vem no Mac e no Linux).

## Como começar, em uma frase

Abra esta pasta no Claude Code e diga:

> Leia o CLAUDE.md e me ajude a configurar o rastreador para a minha viagem.

Ele vai perguntar a rota, as datas, os horários que você aceita, para qual e-mail
mandar, e faz o resto sozinho: cria a configuração, instala e deixa rodando.

Se preferir o passo a passo escrito, está em [`docs/01-primeiro-dia.md`](docs/01-primeiro-dia.md).

## As três coisas que mais importam na calibragem

1. **Filtre o voo que você realmente compraria.** Se você não pega voo que chega de
   madrugada, diga isso. Preço de voo que você não tomaria não é informação, é ruído.
2. **Se a viagem é ida e volta, vigie a viagem inteira**, não cada trecho. É a reserva
   que você vai comprar que decide, e a soma de dois trechos avulsos quase sempre mente.
3. **Deixe o histórico crescer.** Nos primeiros dias o parecer é chute: ele compara o
   preço de hoje com o que já viu, e no primeiro dia ele só viu hoje. A partir de uns
   três ou quatro dias o percentil começa a valer.

O resto está em [`docs/02-calibragem.md`](docs/02-calibragem.md).

## A observação importante sobre computador que dorme

Isto foi medido, não é teoria: num laptop que dorme, **3 de cada 4 leituras se perdem**.
O programa não acorda a máquina. Se o computador estiver dormindo às 3h da manhã, quando
a companhia soltou vinte assentos baratos, ninguém viu.

Opções, em ordem de preferência:

- Um computador que fique ligado o tempo todo, ou um servidor barato na nuvem.
- Um Mac ligado na tomada, com o "impedir que entre em repouso" ligado.
- Um laptop comum: funciona, mas conte com menos leituras e menos chance de pegar a
  queda relâmpago. Nesse caso vale aumentar a frequência de coleta.

## Perguntas frequentes

**Isso é legal?** Sim: ele lê a mesma página pública do Google Flights que você leria.
Só faz isso devagar, de 30 em 30 minutos, com um atraso aleatório para não parecer robô.

**Ele compra a passagem?** Não, e isso é de propósito. Ele avisa; a compra é sua.

**E se eu comprar antes do fim?** Rode `./desinstalar.sh`, ou peça ao Claude: "comprei,
pode desligar o rastreador". Rastreador de viagem comprada só serve para encher a caixa
de e-mail. Ele também se desliga sozinho na data `rastreio_termina_em`.

---
Feito a partir de uma família de rastreadores em uso real desde agosto de 2026. As
cicatrizes estão documentadas em [`docs/04-licoes.md`](docs/04-licoes.md): vale a leitura
antes de mudar qualquer coisa no código.
