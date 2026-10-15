# Adaptando o RotaVital para um caso novo

Nenhuma linha de código precisa mudar. Há três caminhos, do mais rápido ao mais completo.

## 1. Importar um CSV pela interface

Em **Cenário → Importar CSV**, envie as paradas e escolha um cenário existente como base
(de onde vêm depósito, frota e regras de prioridade).

```csv
id,nome,tipo,lat,lon,demanda_kg,prioridade,refrigerado,janela_inicio,janela_fim,tempo_servico_min,carga
H1,Hospital Regional Norte,hospital,-23.4720,-46.6150,14.5,critica,sim,07:00,18:00,12,Hemocomponentes
U1,UBS Jardim Azul,ubs,-23.5810,-46.5020,22,alta,sim,08:00,17:00,10,Vacinas
D1,Paciente Sr. A.,domiciliar,-23.6120,-46.7010,6,rotina,não,14:00,16:00,15,Medicamentos
```

Obrigatórias: `id, nome, lat, lon, demanda_kg`. São aceitos `,` ou `;` como separador e
vírgula decimal.

## 2. Criar um arquivo de cenário

Copie `scenarios/sp-mini-8.json`, mude `id`, `nome`, `deposito`, `frota`, `prioridades` e
`paradas`. Exemplos de adaptação:

| Caso novo | O que muda no arquivo |
|---|---|
| Outra cidade | `deposito` e coordenadas das `paradas`; `fator_sinuosidade` (≈1,25 em malha regular, 1,4+ em relevo acidentado) |
| Distribuição entre unidades de uma rede | `tipo` das paradas e `demanda_kg` maiores; frota de caminhões |
| Vacinação em campanha | todas as paradas `refrigerado: true`, janelas curtas, mais motos |
| Turno noturno | `inicio_turno: "19:00"` e janelas noturnas |
| Novas prioridades (ex.: "emergencia") | adicione a chave em `prioridades` com `sla_min` e `multa_min` |

O arquivo é validado ao carregar. Paradas que nenhum veículo comporta, ou inalcançáveis
dentro da autonomia, geram erro claro antes da otimização.

## 3. Gerar cenários sintéticos

```bash
python scripts/gerar_cenario.py --id teste-60 --paradas 60 --semente 42
```

Para outra cidade, troque a lista `DISTRITOS` e o `DEPOSITO` no script.

## Ajustes de modelagem

- **Velocidades e custos** ficam na frota de cada cenário.
- **Multas por atraso** (R$/min) definem o equilíbrio entre custo e pontualidade: multas
  maiores fazem o GA usar mais veículos para cumprir prazos.
- **Distâncias reais por estrada**: troque `road_distance_matrix` em
  `optimization/geo.py` por uma consulta a OSRM ou Google Distance Matrix. O restante do
  sistema só depende da matriz.
