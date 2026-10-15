# Algoritmo genético

## 1. Representação

O cromossomo é uma **permutação das paradas** (o "tour gigante"), sem depósito e sem
separadores de rota:

```
cromossomo = [P07, P02, P15, P11, P03, ...]
```

Uma representação mais simples também facilita os operadores: qualquer permutação é
válida, e cruzamento e mutação nunca geram indivíduos inválidos. A divisão em rotas e a
escolha do veículo ficam com o decodificador.

## 2. Decodificação: Split de Prins

Para um tour `T = t1..tn`, o Split calcula por programação dinâmica:

```
V[0] = 0
V[j] = min_{i<j, k ∈ tipos}  V[i] + custo_k(t_{i+1} .. t_j)
```

`custo_k` é o custo da rota que sai do depósito, visita `t_{i+1}..t_j` em ordem e volta,
feita por um veículo do tipo `k`. Ele é infinito se violar capacidade, autonomia, jornada
ou cadeia fria. A simulação é **incremental**: estender a rota de `j` para `j+1` custa
O(1), e a varredura para assim que a capacidade, a autonomia ou a jornada estoura. A
complexidade é `O(n · L · K)`, com `L` igual ao tamanho máximo de uma rota viável.

O Split garante que, **para uma dada ordem de visita**, a partição em rotas e a escolha dos
veículos são ótimas. O GA só precisa buscar boas ordens.

### Frota limitada: reparo + preços-sombra

O Split clássico supõe frota ilimitada. Para respeitar a quantidade de cada tipo:

1. **Reparo guloso**: rotas de um tipo excedido migram para o tipo com folga de menor
   aumento de custo, quando a rota continua viável.
2. **Preços-sombra**: se ainda houver excesso, o Split é refeito com o custo fixo do tipo
   excedido acrescido de `multa/3`, até 3 vezes. Fica a melhor solução pelo custo real.
3. O excesso que sobrar recebe a multa de frota (R$ 2.500 por veículo), e a interface
   sinaliza o veículo como *excedente*.

Sem os preços-sombra, o GA convergia para soluções com uma van refrigerada a mais do que
o disponível, pagando a multa de frota. Com eles, as soluções do cenário de 40 pontos
cabem na frota real e o custo cai para menos da metade.

## 3. Função de fitness (minimizada, em R$)

```
custo = Σ rotas [ custo_fixo_k + custo_km_k · distância ]          (operacional)
      + Σ paradas  multa_prioridade · max(0, início_atendimento − prazo)   (atrasos)
      + multa_frota · veículos_excedentes
```

- **prazo** = mínimo entre o fim da janela e o início do turno + SLA da prioridade
  (crítica 2 h, alta 4 h, rotina sem SLA). Entregas agendadas cuja janela abre depois do SLA
  seguem a janela.
- Chegar antes da janela gera **espera**, que consome jornada mas não gera multa.
- Distância por estrada ≈ Haversine × 1,35 (fator de sinuosidade urbana).
- Tempo de viagem = distância / velocidade média do tipo de veículo (van 26 km/h,
  utilitário 24 km/h, moto 34 km/h, valores urbanos).

Todas as grandezas de tempo estão em **minutos**. Usar uma única unidade evita comparar o
SLA com o tempo acumulado em unidades diferentes, erro que anularia o peso das prioridades.

## 4. Operadores

| Etapa | Operador | Detalhe |
|---|---|---|
| População inicial | 10% heurísticas + 90% aleatória | vizinho mais próximo, regra por prioridade, Clarke-Wright e mutações delas |
| Seleção | Torneio (k=3) | pressão seletiva ajustável |
| Cruzamento | OX, PMX ou ERX (taxa 0,9) | OX preserva blocos; PMX preserva posições; ERX preserva arestas (vizinhanças) |
| Mutação | troca, inserção ou inversão | taxa base 0,25, **adaptativa**: ×1,6 a cada 1/3 do limite de estagnação |
| Elitismo | 2 melhores | nunca se perde a melhor solução |
| Diversidade | imigrantes aleatórios | 15% piores substituídos durante a estagnação |
| Busca local | 2-opt intra-rota a cada 10 gerações | avaliado pelo custo completo (respeita janelas) |
| Polimento final | 2-opt + realocação entre rotas | aplicado ao melhor indivíduo |

Critérios de parada: máximo de gerações, estagnação (sem melhoria), tempo limite ou
interrupção pelo usuário.

## 5. Presets

| Preset | População | Gerações | Estagnação | Cruzamento | Uso |
|---|---|---|---|---|---|
| Rápido | 60 | 150 | 50 | OX | demonstração ao vivo |
| Equilibrado | 120 | 400 | 120 | OX | padrão |
| Qualidade | 200 | 900 | 250 | ERX | planejamento definitivo |

## 6. Abordagens de comparação

Todas usam o mesmo avaliador, então os custos são comparáveis:

1. **Aleatório (melhor de 30)**: limite inferior de qualidade.
2. **Regra manual por prioridade**: ordena por prioridade, prazo e distância (como um
   despachante faria) e divide com o Split.
3. **Vizinho mais próximo + Split**: heurística construtiva gulosa.
4. **Clarke-Wright (economias)**: clássico da literatura de VRP. Uma rota só é unida a
   outra se o custo, incluindo atrasos, não aumentar.

Resultados em [experimentos.md](experimentos.md).
