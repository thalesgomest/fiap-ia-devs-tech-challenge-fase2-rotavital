# Arquitetura

## Visão geral

```mermaid
flowchart LR
    subgraph Navegador
        UI[Interface web<br/>HTML + JS + Leaflet + Chart.js]
    end
    subgraph Backend["Backend Python (FastAPI)"]
        API[api/main.py<br/>REST + arquivos estáticos]
        SVC[services.py<br/>JobManager - thread por execução]
        subgraph OPT[optimization]
            EV[evaluator.py<br/>Split + restrições + custo]
            GA[ga.py<br/>GA memético]
            LS[local_search.py<br/>2-opt + realocação]
            BL[baselines.py<br/>4 heurísticas]
        end
        subgraph LLM[llm]
            PR[providers/<br/>Ollama · OpenAI · Claude · offline]
            TL[tools.py<br/>function calling]
            AS[assistant.py]
            RP[reports.py + prompts/*.md]
            EVL[evaluation.py]
        end
        DOM[domain/<br/>modelos + cenários]
        DB[(SQLite<br/>histórico)]
    end
    FILES[(scenarios/*.json<br/>CSV importado)]
    OLL[Ollama local<br/>ou API em nuvem]

    UI <-->|JSON / polling| API
    API --> SVC --> BL & GA
    GA --> EV
    GA --> LS --> EV
    BL --> EV
    SVC --> DB
    API --> AS & RP
    AS --> TL --> DB
    AS & RP --> PR --> OLL
    RP --> EVL
    DOM --> FILES
    API --> DOM
```

## Camadas

| Camada | Pacote | Responsabilidade | Depende de |
|---|---|---|---|
| Domínio | `rotavital.domain` | Entidades (`Stop`, `VehicleType`, `Scenario`), validação, leitura de JSON/CSV | - |
| Otimização | `rotavital.optimization` | Avaliação de soluções, GA, busca local, heurísticas e experimentos | domínio |
| LLM | `rotavital.llm` | Provedores, ferramentas, prompts, relatórios e avaliação de qualidade | storage |
| Persistência | `rotavital.storage` | Histórico de execuções e textos gerados (SQLite) | - |
| Serviço | `rotavital.services` | Orquestra uma execução em segundo plano e publica o progresso | otimização, storage |
| API | `rotavital.api` | Endpoints REST e entrega da interface | todas |
| Interface | `rotavital/web/static` | SPA sem etapa de build | API |

O núcleo de otimização não conhece a API nem a LLM. Ele pode ser usado por linha de
comando (`experiments.py`), por testes ou por outra interface.

## Fluxo de uma otimização

```mermaid
sequenceDiagram
    participant U as Usuário
    participant W as Interface
    participant A as API
    participant J as JobManager (thread)
    participant G as GA + Avaliador
    participant S as SQLite
    U->>W: escolhe cenário, frota e preset
    W->>A: POST /api/execucoes
    A->>J: start(cenário, config)
    A-->>W: 202 {id}
    J->>G: baselines (Clarke-Wright, vizinho mais próximo...)
    loop a cada N gerações
        G-->>J: Snapshot (melhor, média, diversidade, rotas)
        W->>A: GET /progresso?desde=k
        A-->>W: progresso incremental
    end
    G-->>J: melhor tour + polimento final
    J->>S: salva execução completa
    W->>A: GET /api/execucoes/{id}
```

## Fluxo do assistente (function calling)

```mermaid
sequenceDiagram
    participant U as Usuário
    participant A as assistant.py
    participant L as LLM
    participant T as tools.py
    U->>A: "Se a VAN-REF #1 atrasar 30 min?"
    A->>L: system prompt + pergunta + definição das ferramentas
    L-->>A: tool_call simular_atraso(veiculo="VAN-REF #1", minutos=30)
    A->>T: executa sobre os dados reais da execução
    T-->>A: paradas que passam a atrasar + multa extra
    A->>L: resultado da ferramenta
    L-->>A: resposta em linguagem natural
    A-->>U: resposta + rastro das ferramentas usadas
```

Contingências: se o modelo não suporta ferramentas, um contexto compacto vai no próprio
prompt; se a LLM está indisponível, um roteador de intenções responde com as mesmas
ferramentas (modo offline).

## Decisões de arquitetura

| Decisão | Alternativas consideradas | Motivo |
|---|---|---|
| FastAPI + SPA estática | Streamlit, Dash | API documentada (OpenAPI em `/docs`), interface de produto, progresso ao vivo via polling, separação clara frontend/backend |
| Sem etapa de build no frontend | React/Vite | Avaliador roda com `make app`; bibliotecas via CDN com versão fixa |
| Python puro no núcleo (sem numpy) | numpy/numba | O Split é sequencial (DP incremental); listas Python + cache de fitness bastam (~25 s para 40 paradas) |
| Thread por execução + polling | Celery/Redis, WebSocket | Infra mínima para um projeto acadêmico; o contrato de progresso é incremental (`desde=k`) |
| SQLite | PostgreSQL | Zero configuração; suficiente para histórico e relatórios por período |
| Ollama como LLM padrão | API paga em nuvem | Gratuito, offline, sem chave exposta no repositório; modelos LLaMA citados no enunciado |
| Prompts em arquivos `.md` | strings no código | Versionamento, revisão e citação no relatório técnico |
| Modo offline determinístico | falhar sem LLM | A aplicação e os testes nunca dependem de serviço externo |

## Escalabilidade e monitoramento

- **Execuções concorrentes**: cada otimização roda em uma thread própria; o cache de
  fitness é por execução. Para escalar horizontalmente, o `JobManager` pode ser trocado
  por uma fila (ex.: Cloud Tasks ou Celery) sem mudar a API.
- **Contêiner**: `Dockerfile` + `docker-compose.yml` (app + Ollama). A imagem é *stateless*
  (dados em volume) e pode ir para Cloud Run ou ECS com autoescala por requisições.
- **Observabilidade**: cada execução registra gerações, avaliações de fitness, tempo, motivo
  de parada e curva de convergência; cada texto da LLM fica salvo com provedor, modelo e
  nota de qualidade (`GET /api/execucoes/{id}/textos`).
