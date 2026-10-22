# Experimentos

Cenário principal **Hemorrede SP - 40 pontos** (`sp-hemorrede-40`): 9 hospitais, 11 UBS, 5
laboratórios, 9 pacientes de home care e 6 AMAs; frota de 3 vans refrigeradas, 2 utilitários e
4 motos. **10 sementes por configuração**, base de 400 gerações, estagnação de 120 e tempo
limite de 300 s. Cada configuração muda um único fator em relação à base E1.

Reproduzir: `make experimentos SEMENTES=10` (ou
`python -m rotavital.optimization.experiments --cenario sp-hemorrede-40 --sementes 10`).
Figuras do relatório: `python scripts/gerar_figuras.py --exp experiments/<pasta>`.

## Resultados (10 sementes)

Custo em R$ (menor é melhor). p = valor-p do teste de Mann-Whitney contra o E1.

| Experimento | Custo médio | Desvio | Melhor | Pior | Tempo médio | p (vs E1) |
|---|---|---|---|---|---|---|
| Baseline: Aleatório (melhor de 30) | 9.911,12 | - | - | - | 0,1 s | |
| Baseline: Regra manual por prioridade | 8.385,87 | - | - | - | 0,0 s | |
| Baseline: Vizinho mais próximo + Split | 9.978,94 | - | - | - | 0,0 s | |
| Baseline: Clarke-Wright (economias) | 4.229,69 | - | - | - | 0,0 s | |
| **E1 - base (pop 120, OX, mut 0,25)** | **1.630,39** | **27,93** | 1.584,48 | **1.675,86** | 24,7 s | - |
| E2 - população 40 | 1.665,21 | 53,06 | 1.584,24 | 1.767,64 | 6,6 s | 0,10 |
| E3 - população 250 | 1.624,92 | 52,26 | 1.527,53 | 1.686,53 | 52,0 s | 1,00 |
| E4 - mutação fixa 0,6 | 1.645,31 | 59,88 | 1.572,96 | 1.741,27 | 67,1 s | 0,62 |
| E5 - cruzamento PMX | 1.652,88 | 80,08 | 1.547,72 | 1.828,76 | 22,4 s | 0,68 |
| E6 - cruzamento ERX | 1.614,39 | 80,66 | 1.468,03 | 1.731,85 | 53,5 s | 0,85 |
| E7 - sem busca local periódica | 1.626,71 | 69,00 | 1.530,92 | 1.793,87 | 23,6 s | 0,52 |
| E8 - sem sementes heurísticas | 1.627,11 | 61,84 | 1.522,91 | 1.753,98 | 23,4 s | 0,73 |

## Composição do custo (E1, semente 1)

| Abordagem | Operacional | Multa atraso | Multa frota | Total | Veículos | km | No prazo |
|---|---|---|---|---|---|---|---|
| Vizinho mais próximo | 2.478,94 | 0,00 | 7.500,00 | 9.978,94 | 10 | 585,5 | 100% |
| Aleatório (30) | 3.018,00 | 1.893,12 | 5.000,00 | 9.911,12 | 11 | 996,6 | 90,0% |
| Regra manual | 2.781,48 | 604,40 | 5.000,00 | 8.385,87 | 11 | 908,3 | 92,5% |
| Clarke-Wright | 1.729,69 | 0,00 | 2.500,00 | 4.229,69 | 8 | 446,3 | 100% |
| **Algoritmo genético** | **1.607,33** | 0,00 | 0,00 | **1.607,33** | 7 | 523,1 | 100% |

## Outros cenários (E1, 10 sementes)

| Cenário | Clarke-Wright | GA (média) | Desvio | Redução | No prazo (GA) |
|---|---|---|---|---|---|
| sp-mini-8 | 622,82 | 490,53 | 7,92 | 21,2% | 100% |
| sp-homecare-18 | 3.537,75 | 806,63 | 59,11 | 77,2% | 98,9% |
| sp-hemorrede-40 | 4.229,69 | 1.630,39 | 27,93 | 61,5% | 99,75% |

## Análise

- **Nenhuma configuração difere do E1 com significância estatística** (todos os p > 0,05). As
  médias ficam a menos de 3% umas das outras: o desempenho vem da modelagem (representação,
  Split e função de custo), não do ajuste fino.
- **E1 é a configuração mais previsível:** menor desvio padrão (cerca da metade do segundo
  menor) e melhor pior caso. Por isso é o padrão (preset "Equilibrado").
- **População 40:** 3,7× mais rápida e 2,1% mais cara (p ≈ 0,10). Base do preset "Rápido".
- **ERX:** menor média e melhor resultado individual, mas o maior desvio e 2,2× o tempo. Por
  isso é usado no preset "Qualidade".
- **PMX:** pior caso mais alto, coerente com preservar posições absolutas que o Split desfaz.
- **Sem busca local periódica ou sem sementes:** média igual, dispersão maior.
- **Vantagem sobre o Clarke-Wright:** 61,5% no custo total, mas a maior parte vem da multa de
  frota (o Clarke-Wright usa 4 vans refrigeradas para 3 disponíveis). Só no custo operacional, a
  vantagem é de cerca de 7%, com um veículo a menos.
- **Teto de gerações:** a média de gerações ficou entre 308 e 400; várias execuções chegaram a
  400 ainda melhorando lentamente.

> Com 3 sementes, as conclusões preliminares eram diferentes (por exemplo, o E1 parecia ter
> média menor que E3 e E6). As 10 sementes mostraram que essas diferenças eram ruído.

## Limitações

- Distâncias estimadas por Haversine × 1,35, não por roteamento viário real.
- Velocidades médias fixas por tipo de veículo, sem variação de trânsito por horário.
- Cada veículo faz uma única viagem por turno, e a espera por janelas não é penalizada.
- Fatores variados um de cada vez; interações entre parâmetros não foram exploradas.
