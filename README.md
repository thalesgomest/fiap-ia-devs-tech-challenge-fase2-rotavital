<div align="center">

# 🚑 RotaVital — Otimização de Rotas Hospitalares

**Roteirização de hemocomponentes, vacinas e insumos hospitalares com algoritmo genético** — da modelagem do problema à geração de instruções e relatórios por LLM.

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/API-FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Algoritmo Genético](https://img.shields.io/badge/Otimiza%C3%A7%C3%A3o-Algoritmo%20Gen%C3%A9tico-0E6E66)](docs/algoritmo_genetico.md)
[![LLM](https://img.shields.io/badge/LLM-Ollama%20%7C%20OpenAI%20%7C%20Claude-8A2BE2)](docs/llm.md)
[![Testes](https://img.shields.io/badge/Testes-pytest-0A9EDC?logo=pytest&logoColor=white)](tests/)

**Tech Challenge — Fase 2 · Projeto 2 · Pós-graduação em IA (FIAP)**

📄 [Relatório Técnico Completo](reports/relatorio_tecnico.pdf) · 🔗 [Repositório](https://github.com/thalesgomest/fiap-ia-devs-tech-challenge-fase2-rotavital)

</div>

---

## 👥 Equipe

| Nome                           | RM       |
| ------------------------------ | -------- |
| Daniel Henrique Soter de Souza | rm376376 |
| Otavio Braga Goulart           | rm376980 |
| Thales Gomes Targino           | rm376365 |

---

## 📌 Sobre o Projeto

Um hemocentro na capital paulista abastece diariamente hospitais, UBS, laboratórios,
AMAs e pacientes em atendimento domiciliar. Cada entrega tem **prioridade** (crítica,
alta ou rotina), **janela de recebimento**, **peso** e pode exigir **cadeia fria**. A
frota é **heterogênea** (vans refrigeradas, utilitários de carga seca e motos com baú
térmico), com **capacidade**, **autonomia** e **jornada** limitadas.

Este projeto resolve esse "caixeiro-viajante médico" — tecnicamente, um problema de
roteamento de veículos com frota heterogênea e janelas de tempo (HFVRPTW) — com um
**algoritmo genético**, e usa uma **LLM** para gerar instruções aos motoristas,
relatórios de eficiência e responder perguntas em linguagem natural sobre as rotas.

O trabalho cobre o ciclo completo — **modelagem do problema → função de custo →
algoritmo genético → comparação com heurísticas clássicas → experimentos de
parâmetros → integração com LLM → interface web** — e discute com clareza onde o
algoritmo ganha e quais são os limites do modelo.

| Restrição exigida        | Como foi modelada                                                                 |
| ------------------------ | --------------------------------------------------------------------------------- |
| Prioridades diferentes   | SLA por prioridade + multa em R$/min de atraso (crítica 40, alta 10, rotina 1,50) |
| Capacidade de carga      | kg por tipo de veículo — restrição rígida                                         |
| Autonomia                | km máximos por veículo, incluindo o retorno ao depósito                           |
| Múltiplos veículos (VRP) | frota heterogênea com quantidade limitada por tipo                                |
| Outras restrições        | janelas de horário, cadeia fria e jornada máxima do motorista                     |

> **🎯 Decisão central do projeto:** o algoritmo genético minimiza o **custo total do
> dia em reais** — custo fixo dos veículos + custo por km + multas de atraso + multa
> por exceder a frota. Converter quilômetros, minutos e veículos para uma moeda comum
> evita pesos arbitrários e gera um número que o gestor entende. A justificativa de
> cada decisão está em [docs/algoritmo_genetico.md](docs/algoritmo_genetico.md).

### Resultados em resumo

Cenário principal `sp-hemorrede-40` (40 entregas, frota de 9 veículos):

| Item                              | Resultado                                                                                                        |
| --------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| Representação genética            | Permutação das entregas ("tour gigante") decodificada pelo Split de Prins (programação dinâmica)                 |
| Configuração final                | População 120 · torneio k=3 · cruzamento OX (0,9) · mutação adaptativa 0,25→0,8 · elitismo 2 · busca local 2-opt |
| Custo do GA                       | R$ 1.630 (média de 10 sementes, desvio de R$ 27,93; pior execução R$ 1.676)                                      |
| Melhor heurística (Clarke-Wright) | R$ 4.230 — o GA fica **61,5% abaixo no custo total**                                                             |
| Só custo operacional (sem multas) | GA R$ 1.607 × Clarke-Wright R$ 1.730 — **cerca de 7% abaixo**                                                    |
| Frota                             | GA usa 7 veículos e é a **única abordagem que cabe na frota real**; todas as heurísticas excedem e pagam multa   |
| Pontualidade                      | 99,75% das entregas no prazo (média de 10 sementes)                                                              |
| Experimentos                      | 8 configurações × 10 sementes, um fator por vez; nenhuma difere da base com significância                        |

Detalhamento de cada etapa, métricas e limitações: **[relatório técnico em PDF](reports/relatorio_tecnico.pdf)** e [docs/experimentos.md](docs/experimentos.md).

---

## ✨ Destaques Técnicos

- **Cromossomo de permutação + Split de Prins:** o GA busca a ordem das entregas; uma
  programação dinâmica decide onde cortar as rotas e qual veículo usar em cada uma.
- **Preços-sombra de frota:** quando um tipo de veículo excede a quantidade disponível,
  o Split é refeito encarecendo esse tipo até a solução caber na frota real.
- **GA memético:** torneio, OX/PMX/ERX, mutação adaptativa, imigrantes contra
  estagnação e busca local 2-opt e de realocação.
- **Comparativo automático** com 4 abordagens: aleatória, regra manual por prioridade,
  vizinho mais próximo e Clarke-Wright — todas avaliadas pela mesma função de custo.
- **LLM com ferramentas (function calling):** o assistente consulta rotas, paradas e
  simulações "e se?" em vez de receber o JSON inteiro, o que reduz alucinação.
- **Provedores intercambiáveis:** Ollama local (padrão, gratuito), qualquer API
  compatível com OpenAI ou Claude, e modo offline determinístico.
- **Avaliação automática dos textos da LLM:** fidelidade numérica, cobertura e ordem
  das paradas e, opcionalmente, LLM como juiz.
- **Adaptável a casos novos:** cenários em JSON ou importação de CSV pela interface,
  sem alterar o código.

---

## 🗂️ Estrutura de Pastas

```
11IADT-otimizar-rotas-medicas/
├── src/rotavital/
│   ├── domain/            # Entidades, cenários e validação
│   ├── optimization/      # Avaliador (Split), operadores, GA, busca local, heurísticas, experimentos
│   ├── llm/               # Provedores, ferramentas, prompts versionados, relatórios e avaliação
│   ├── storage/           # Histórico de execuções em SQLite
│   ├── api/               # API REST (FastAPI)
│   ├── web/static/        # Interface web (HTML/CSS/JS + Leaflet + Chart.js)
│   └── services.py        # Orquestra uma otimização em segundo plano
├── scenarios/             # Cenários em JSON (adicione os seus aqui)
├── scripts/               # Tarefas do Makefile (tasks.py) e gerador de cenários
├── tests/                 # Testes unitários e de API
├── experiments/           # Resultados das baterias de experimentos (gerados)
├── reports/
│   ├── figures/           # Figuras do relatório (scripts/gerar_figuras.py)
│   ├── relatorio_tecnico.html
│   └── relatorio_tecnico.pdf
├── docs/                  # Arquitetura, modelagem do GA, LLM e experimentos
├── Makefile
├── Dockerfile / docker-compose.yml
├── requirements.txt
└── README.md
```

---

## Qwen3 local e projeto principal

Este é o projeto principal. A integração usa o **Qwen3 4B Q4_K_M** já validado no protótipo anterior, com runtime e ambiente próprios. Nesta máquina Windows:

```powershell
.\scripts\start-local.ps1
```

Abra `http://127.0.0.1:8000`, conclua uma otimização e entre na etapa **Assistente**. Instruções de preparação, parâmetros, origem dos pesos e avaliação em [docs/qwen3-local.md](docs/qwen3-local.md).

## 🚀 Como Executar

Todo o projeto é operado pelo `make`, igual em Windows, macOS e Linux. Se preferir não
instalar o `make`, veja [Execução sem make](#execucao-sem-make).

### Pré-requisitos

| Sistema               | Python 3.11+                                  | make                                                                              |
| --------------------- | --------------------------------------------- | --------------------------------------------------------------------------------- |
| Windows               | `winget install Python.Python.3.11`           | `winget install ezwinports.make` (ou `scoop install make` / `choco install make`) |
| macOS                 | `brew install python@3.11`                    | `xcode-select --install`                                                          |
| Linux (Debian/Ubuntu) | `sudo apt install python3.11 python3.11-venv` | `sudo apt install make`                                                           |

No Windows, **abra um terminal novo** depois de instalar, para que o PATH seja atualizado.

### Rodar

```bash
make doctor   # opcional: verifica o ambiente e diz o que falta
make demo     # prepara o ambiente (na 1ª vez), roda os testes e sobe o app
```

Abra <http://localhost:8000> (documentação da API em <http://localhost:8000/docs>).
`Ctrl+C` encerra.

Na primeira execução, o `make` cria o ambiente virtual com um Python 3.11+, instala as
dependências e gera o `.env`. Nas seguintes, isso só se repete se as dependências mudarem.

### Comandos

| Comando                                                | Descrição                                                                   |
| ------------------------------------------------------ | --------------------------------------------------------------------------- |
| `make demo`                                            | Prepara o ambiente, roda os testes e sobe o app (recomendado)               |
| `make doctor`                                          | Diagnóstico: Python, venv, dependências, cenários, porta 8000 e Ollama      |
| `make app`                                             | Sobe o app em <http://localhost:8000> (`make dev` = com recarga automática) |
| `make test`                                            | Testes automatizados (pytest)                                               |
| `make lint` / `make format`                            | Análise estática / formatação (ruff)                                        |
| `make experimentos`                                    | Experimentos do GA → `experiments/<data>/resumo.md`                         |
| `make experimentos SEMENTES=10 CENARIO=sp-homecare-18` | Idem, com parâmetros                                                        |
| `make llm`                                             | Baixa o modelo do Ollama (`OLLAMA_MODEL=...` para outro)                    |
| `make cenarios`                                        | Regenera os cenários sintéticos                                             |
| `make docker`                                          | App + Ollama via docker compose                                             |
| `make setup`                                           | Reinstala as dependências                                                   |
| `make clean` / `make reset`                            | Remove caches / remove o ambiente virtual                                   |

Outras variáveis: `PORTA=8080` muda a porta; `PYTHON=caminho/do/python` força um interpretador.

---

## 🤖 LLM local

O padrão desta integração é **Qwen3 4B Q4_K_M pelo Ollama**, com temperatura 0,
semente 2026, contexto 8192 e `think=false`. Não houve fine-tuning. Os pesos
reaproveitados têm aproximadamente 2,5 GB; nesta execução o Ollama utilizou CPU.

```powershell
.\scripts\start-local.ps1
```

Na etapa **Assistente**, o topo deve mostrar `LLM: ollama · qwen3:4b` e `online`.
A primeira resposta pode levar minutos em CPU. Para perguntas sobre prioridade,
a ferramenta aplica o filtro em Python, distinguindo alta de crítica.

O modelo é definido por `OLLAMA_MODEL` no `.env`. O modo determinístico é
`LLM_PROVIDER=offline`; ele não equivale a uma chamada real à LLM. No chat,
`LLM_FALLBACK_OFFLINE=0` expõe falhas, e `1` permite contingência identificada.
Outros provedores continuam disponíveis na configuração existente.

Preparação, parâmetros e origem: [Qwen3 local](docs/qwen3-local.md).
Testes, chamadas reais e limitações: [Validação da integração](docs/validacao-qwen3.md).

---

## 🖥️ Usando a Interface

| #   | Etapa              | O que faz                                                                             |
| --- | ------------------ | ------------------------------------------------------------------------------------- |
| 1   | **Cenário**        | Escolhe um cenário (ou importa um CSV) e mostra as paradas no mapa                    |
| 2   | **Frota & Regras** | Ajusta quantidade e capacidade dos veículos e o modo do GA                            |
| 3   | **Otimização**     | Mostra a convergência ao vivo, com as heurísticas como referência                     |
| 4   | **Resultados**     | KPIs, comparativo, mapa por veículo, linha do tempo de cada rota e folha do motorista |
| 5   | **Assistente**     | Responde perguntas como _"Se a VAN-REF #1 atrasar 30 minutos, o que acontece?"_       |
| 6   | **Relatórios**     | Relatório da operação, relatório diário/semanal e avaliação de qualidade dos textos   |
| 7   | **Histórico**      | Execuções anteriores                                                                  |

---

## 📚 Documentação

| Documento                                        | Conteúdo                                                             |
| ------------------------------------------------ | -------------------------------------------------------------------- |
| [Arquitetura](docs/arquitetura.md)               | Componentes, fluxo de dados, diagramas e decisões                    |
| [Algoritmo genético](docs/algoritmo_genetico.md) | Representação, Split, função de custo e operadores                   |
| [Integração com LLM](docs/llm.md)                | Provedores, ferramentas, prompts, avaliação e requisitos de hardware |
| [Experimentos](docs/experimentos.md)             | Configurações testadas, resultados e análise                         |
| [Adaptando para um caso novo](docs/novo_caso.md) | Como criar cenários para outro hospital ou cidade                    |

---

<a id="execucao-sem-make"></a>

## ⌨️ Execução sem make

Os mesmos passos chamando o Python diretamente.

**Windows (PowerShell):**

```powershell
py -3.11 -m venv venv
.\venv\Scripts\python -m pip install -r requirements.txt
.\venv\Scripts\python -m pip install -e .
copy .env.example .env
.\venv\Scripts\python -m pytest
.\venv\Scripts\python -m uvicorn rotavital.api.main:app --port 8000
```

**macOS / Linux:**

```bash
python3.11 -m venv venv
venv/bin/python -m pip install -r requirements.txt
venv/bin/python -m pip install -e .
cp .env.example .env
venv/bin/python -m pytest
venv/bin/python -m uvicorn rotavital.api.main:app --port 8000
```

Equivalentes dos demais comandos (no Windows, troque `venv/bin/python` por `.\venv\Scripts\python`):

| make                            | Comando direto                                                                                  |
| ------------------------------- | ----------------------------------------------------------------------------------------------- |
| `make doctor`                   | `python scripts/tasks.py doctor`                                                                |
| `make experimentos SEMENTES=10` | `venv/bin/python -m rotavital.optimization.experiments --cenario sp-hemorrede-40 --sementes 10` |
| `make lint`                     | `venv/bin/python -m ruff check src tests scripts`                                               |
| `make llm`                      | `ollama pull llama3.1:8b`                                                                       |
| `make cenarios`                 | `venv/bin/python scripts/gerar_cenario.py`                                                      |
| `make docker`                   | `docker compose up --build`                                                                     |

---

## 📄 Relatório Técnico

O relatório técnico desta fase — implementação do algoritmo genético, estratégias para
as restrições, integração com LLM, comparativo com outras abordagens, visualizações das
rotas e arquitetura — está em [`reports/relatorio_tecnico.pdf`](reports/relatorio_tecnico.pdf).

O PDF é gerado a partir de `reports/relatorio_tecnico.html`, e as figuras com
`python scripts/gerar_figuras.py --exp experiments/<pasta>` (requer `matplotlib`).

## 🔗 Repositório

[https://github.com/thalesgomest/fiap-ia-devs-tech-challenge-fase2-rotavital](https://github.com/thalesgomest/fiap-ia-devs-tech-challenge-fase2-rotavital)
