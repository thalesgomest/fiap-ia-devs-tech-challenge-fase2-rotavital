# Experimentos

Cenário **Hemorrede SP - 40 pontos** (`sp-hemorrede-40`): 9 hospitais, 11 UBS, 5
laboratórios, 9 pacientes de home care e 6 AMAs. A frota tem 3 vans refrigeradas, 2
utilitários e 4 motos. São 3 sementes por configuração, com base de 400 gerações,
estagnação de 120 e tempo limite de 300 s.

Reproduzir: `make experimentos` (ou `python -m rotavital.optimization.experiments --cenario sp-hemorrede-40 --sementes 3`).

## Resultados

Custo em R$ (fitness = custo operacional + multas; menor é melhor).

| Experimento | Custo médio | Desvio | Melhor | vs melhor baseline | No prazo | Tempo médio (s) |
|---|---|---|---|---|---|---|
| Baseline: Aleatório (melhor de 30) | 9911.12 | - | 9911.12 | -134.3% | 90.0% | 0.1 |
| Baseline: Regra manual por prioridade | 8385.87 | - | 8385.87 | -98.3% | 92.5% | 0.0 |
| Baseline: Vizinho mais próximo + Split | 9978.94 | - | 9978.94 | -135.9% | 100.0% | 0.0 |
| Baseline: Clarke-Wright (economias) | 4229.69 | - | 4229.69 | referência | 100.0% | 0.0 |
| E1-base (pop 120, OX, mut 0.25) | 1617.15 | 12.62 | 1607.33 | +61.8% | 100.0% | 29.1 |
| E2-população pequena (40) | 1696.15 | 65.47 | 1639.11 | +59.9% | 100.0% | 8.0 |
| E3-população grande (250) | 1626.04 | 35.49 | 1594.41 | +61.6% | 100.0% | 58.1 |
| E4-mutação alta (0.6) | 1658.67 | 72.46 | 1576.00 | +60.8% | 100.0% | 74.2 |
| E5-cruzamento PMX | 1708.11 | 109.04 | 1616.59 | +59.6% | 100.0% | 27.9 |
| E6-cruzamento ERX | 1632.31 | 45.70 | 1586.75 | +61.4% | 100.0% | 70.4 |
| E7-sem busca local | 1595.05 | 56.55 | 1530.92 | +62.3% | 100.0% | 28.7 |
| E8-sem sementes heurísticas | 1605.27 | 73.43 | 1522.91 | +62.0% | 100.0% | 26.3 |

## Análise

- **GA × heurísticas**: todas as configurações do GA custam cerca de 60% menos que a
  melhor heurística (Clarke-Wright) e 80% menos que a regra manual de despacho, com 100%
  das entregas no prazo. A regra manual e a aleatória geram multas de atraso e de frota.
- **Tamanho da população**: com 40 indivíduos o GA é 3,6 vezes mais rápido, mas fica 5%
  pior e com o maior desvio. Com 250 não há ganho médio sobre 120, e o tempo dobra. O
  ponto de equilíbrio é 120 (preset "Equilibrado").
- **Cruzamento**: ERX e OX ficam empatados em custo, mas o ERX é cerca de 2,4 vezes mais
  lento. O PMX tem o pior desvio, pois preserva posições absolutas, que importam pouco
  quando o Split redefine as rotas.
- **Mutação alta**: acha bons ótimos isolados (melhor 1576), mas com variância alta e tempo
  maior, porque a estagnação demora a ocorrer.
- **Busca local e sementes**: com 3 sementes, as diferenças de E7 e E8 para E1 (±1,5%)
  ficam **dentro do desvio padrão**, ou seja, não são estatisticamente conclusivas. O
  polimento final (2-opt + realocação) roda em todas as configurações, o que reduz o
  impacto do 2-opt periódico. Para o relatório, rode `--sementes 10` antes de tirar conclusões.

## Limitações

- Distâncias estimadas por Haversine × 1,35, não por roteamento viário real.
- Velocidades médias fixas por tipo de veículo, sem variação de trânsito por horário.
- Cada veículo faz uma única viagem por turno (sem retorno ao depósito para recarregar).
