# Experimentos

Cada execução de `make experimentos` cria uma pasta `AAAAMMDD-HHMMSS/` com:

- `resultados.csv`: uma linha por (configuração, semente) e por heurística de referência;
- `resumo.md`: média, desvio padrão e diferença para a melhor heurística;
- `convergencia.json`: curva do melhor custo por geração, para gráficos.

As pastas de resultado não são versionadas. Copie o `resumo.md` relevante para
`docs/experimentos.md`.
