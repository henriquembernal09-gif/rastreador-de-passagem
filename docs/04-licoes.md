# As cicatrizes

Cada regra chata deste repositório existe porque alguma coisa deu errado de um jeito
específico. Estão aqui para não serem "simplificadas" por quem não viu acontecer.

## 1. O alerta que não saiu (o incidente que criou a ferramenta)

Uma rota caiu de R$ 4.293 para R$ 2.347 e nenhum aviso chegou. A leitura boa existiu: a
coleta das 7h12 **leu** os R$ 2.347 e travou logo depois, e como o programa só gravava o
CSV no fim de todos os combos, a leitura morreu dentro do processo pendurado. O processo
ficou 3h15 vivo sem fazer nada. Até o fim do dia o preço já tinha subido de novo.

O que mudou, e que não se mexe mais:

- **Grava cada combo na hora, com fsync.** Um combo lento não leva junto a leitura boa dos
  outros.
- **Lock global entre rastreadores.** O gatilho do travamento foi o laptop acordar do
  sono, o agendador disparar dois rastreadores no mesmo segundo e dois navegadores
  escondidos brigarem pela máquina.
- **Teto de tempo em cada etapa.**
- **Alerta antes do parecer e do boletim.** É a etapa que não pode depender de o resto dar
  certo.

## 2. Silêncio não é preço estável

Rodadas se perderam em três dias seguidos sem ninguém perceber, porque a falha e a
estabilidade se parecem: nos dois casos não chega nada. Daí vem o `ultima_rodada_ok.txt` e
o hábito de perguntar "quando foi a última leitura?" em vez de "o preço mexeu?".

Em instalação com várias viagens, vale um vigia separado que cobra rastreador calado há
mais de seis horas.

## 3. Máquina que dorme perde 3 de cada 4 leituras

Medido, não estimado: um rastreador configurado para 48 leituras por dia entregou entre 5
e 14 por dia num laptop que dormia. Nenhum ajuste de agendador resolve isso, porque o
agendador não acorda a máquina. Um servidor que fica ligado resolveu na primeira semana.

## 4. Copiar arquivo entre rastreadores sem conferir o arquivo inteiro

Um `coletar.py` foi copiado de uma pasta para outra depois de comparar só a função
principal. Um dos rastreadores era só ida e o outro era ida e volta: o resultado foi um
erro de chave e a coleta parou. Se for reaproveitar código entre pastas, compare o arquivo
inteiro.

## 5. Misturar duas séries que medem coisas diferentes

Durante um tempo, num rastreador de ida e volta, o preço gravado era "ida dentro da janela
com **qualquer** volta". Quando o coletor aprendeu a fechar a volta, o mesmo dia passou a
valer R$ 1.202 em vez de R$ 1.104. Continuar a mesma série daria percentil errado e um
alerta de "queda" que era só mudança de régua. A série antiga foi arquivada com um nome
que diz o que ela media, e a nova começou do zero.

## 6. Boletim vira ruído depressa

Uma coleta a cada 20 minutos mandando e-mail por rodada deu quinze e-mails em três horas.
O efeito prático não é incômodo, é pior: a pessoa para de abrir. Boletim represado por
slot, duas vezes por dia; e o alerta, que é raro, continua chegando na hora. **Alerta e
boletim nunca no mesmo canal.**

## 7. Fuso horário, três armadilhas

- Servidor roda em UTC. Sem `TZ` explícito, a janela de horário do voo e o slot do boletim
  são comparados com o relógio errado.
- O cron lê a agenda no fuso do sistema e costuma **ignorar** `CRON_TZ`. Testado com duas
  entradas gêmeas, uma marcada em hora local e outra em UTC: só a de UTC disparou. Por
  isso a conversão é feita ao escrever a linha do cron.
- `%` não escapado numa linha de cron trunca o comando ali mesmo. Um teste com
  `date '+%H:%M'` virou `date '+`.

## 8. Marcar horário com o `date` do shell

A marca do último boletim gravada pelo shell saiu num formato que o Python antigo não
conseguia reler (offset `-0300` sem dois pontos). A represa não enxergou a marca e os
e-mails saíram de novo. Quem grava a marca é o próprio Python.

## 9. O PATH tem que estar no topo

O `export PATH` estava logo antes da etapa de e-mail. Quando o alerta também passou a sair
por e-mail — e o alerta roda antes —, ele ficou sem encontrar o `claude` e falhava calado.
PATH vai no topo do `rodada.sh`, e também no ambiente do agendamento, que não carrega
perfil de login nenhum.

## 10. A unidade de decisão é a reserva, não o trecho

Foram montados três rastreadores para uma viagem: as duas pernas avulsas e a reserva
conjunta. Só a reserva conjunta interessava, porque é ela que se compra. Os dois de perna
foram apagados. Quando alguém pede "vigia essa viagem", o que ele vai comprar é uma
reserva.
