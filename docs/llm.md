# Integração com LLM

> Integração local atual: **Qwen3 4B Q4_K_M via Ollama**, no projeto principal RotaVital. Para iniciar o runtime já preparado, usar o chat e conferir origem/avaliação, siga [Qwen3 local](qwen3-local.md). Os demais provedores continuam disponíveis.

## Requisitos atendidos

| Requisito do enunciado | Implementação |
|---|---|
| Instruções detalhadas para motoristas | `reports.driver_instructions` → folha de rota por veículo (imprimível) |
| Relatórios diários/semanais de eficiência | `reports.period_report(dias=1\|7)` sobre o histórico SQLite |
| Sugerir melhorias a partir de padrões | seção "Sugestões" do relatório + regras sobre indicadores passadas como evidência |
| Prompts eficientes | prompts versionados em `src/rotavital/llm/prompts/*.md` |
| Perguntas em linguagem natural | `assistant.answer` com *function calling* sobre 8 ferramentas |

## Escolha do provedor

Os critérios foram: o avaliador precisa conseguir rodar o projeto sem depender de serviços
ou cotas de terceiros, nenhuma credencial pode ficar no repositório, e a aplicação não pode
parar de funcionar quando a LLM estiver indisponível. Por isso, a camada:

1. **Não tem credencial no código**: toda chave vem do `.env`.
2. **Usa Ollama como padrão**: Qwen3 4B Q4_K_M local, com configuração e pesos rastreáveis.
3. **Troca de provedor com uma variável**: `LLM_PROVIDER=ollama|openai|anthropic|offline`.
4. **Distingue falha e contingência**: no chat, a contingência depende de `LLM_FALLBACK_OFFLINE`; quando desativada, o erro chega à interface como HTTP 503.

| Provedor | Integração |
|---|---|
| `ollama` | Qwen3 4B Q4_K_M local verificado nesta máquina |
| `openai` | Adaptador existente para APIs compatíveis com OpenAI |
| `anthropic` | Adaptador existente para SDK Anthropic |
| `offline` | Textos determinísticos, sem inferência de LLM |

Esta rodada verificou o Qwen3 local; não comparou a qualidade dos outros provedores.

Para usar o Claude: `LLM_PROVIDER=anthropic` e a credencial em
`ANTHROPIC_API_KEY` (ou `ant auth login`). O modelo padrão é `claude-opus-5-5`, com esforço
`medium` (`ANTHROPIC_EFFORT`). As chamadas habilitam o fallback do lado do servidor
(`fallbacks="default"`), e uma eventual recusa é tratada e devolvida como mensagem amigável.

## Requisitos de hardware para o Ollama local

O modelo precisa caber na memória disponível. O arquivo usado é o GGUF oficial
Qwen3 4B Q4_K_M, de **2.497.280.256 bytes** (aproximadamente 2,5 GB decimais).
Com contexto 8192, a API do Ollama informou cerca de **3,89 GB** para modelo/contexto
e `size_vram=0`: a inferência desta rodada utilizou CPU. Isso não mede o pico de
memória de todo o processo nem estabelece o mínimo de RAM de qualquer máquina.

Não houve avaliação comparativa de outros modelos ou GPUs nesta integração.
Os pesos, a quantização e o contexto importam mais que o nome do modelo sozinho.
A preparação portátil também exige espaço para os binários do Ollama.

### Como trocar de modelo

O modelo é configurável por `OLLAMA_MODEL` no `.env`; reinicie o aplicativo após
alterar a configuração. No Windows, `scripts/setup-ollama.ps1 -Model nome:tag`
prepara o modelo escolhido. A importação padrão do Qwen3 utiliza revisão e hash
fixados; outro nome/registro pode fornecer bytes e desempenho diferentes.

### Tempos observados e `LLM_TIMEOUT_S`

Na avaliação inicial do chat, três perguntas levaram aproximadamente **150,1 s**,
**65,7 s** e **15,6 s**. A primeira incluiu carregamento e consulta de ferramenta;
os contextos e comprimentos de resposta eram diferentes. São observações locais,
não um benchmark controlado de hardware ou uma promessa para toda pergunta.

`LLM_TIMEOUT_S=300` limita cada chamada ao modelo. Uma pergunta pode exigir uma
chamada para selecionar a ferramenta e outra para redigir a resposta. A configuração
usa `think=false`, saída de chat de até 512 tokens e `keep_alive=10m`. A interface
aguarda a resposta completa e informa que a primeira pode levar alguns minutos.

O chat apresenta erro quando a LLM falha e a contingência está desativada. O modo
offline e textos de contingência são identificados, não contam como respostas do Qwen3.
A [validação da integração](validacao-qwen3.md) preserva também um erro semântico
observado e o reteste dirigido após a correção.

## Arquitetura da camada

```
providers/base.py         interface LLMProvider (complete, chat com ferramentas, health)
providers/ollama.py       /api/chat com tools
providers/openai_compat.py  /chat/completions com tool_calls
providers/anthropic_provider.py  SDK anthropic, laço tool_use/tool_result
providers/offline.py      marcador do modo sem LLM
tools.py                  8 ferramentas sobre os dados reais da execução
assistant.py              chat (ferramentas → contexto compacto → offline)
reports.py                instruções, relatório da execução, relatório do período
templates.py              textos determinísticos (offline/contingência)
evaluation.py             métricas de qualidade
prompts/*.md              prompts versionados
```

## Ferramentas do assistente

| Ferramenta | Pergunta típica |
|---|---|
| `resumo_execucao` | "Como foi a operação de hoje?" |
| `listar_rotas` | "Quantos veículos saem e com qual ocupação?" |
| `detalhar_rota(veiculo)` | "Qual a sequência da MOTO #1?" |
| `buscar_parada(nome)` | "Quando chega a entrega do Hospital Santana?" |
| `entregas_em_risco(folga_minima_min)` | "Alguma entrega crítica corre risco?" |
| `comparar_abordagens` | "Quanto economizamos frente ao Clarke-Wright?" |
| `simular_atraso(veiculo, minutos)` | "E se a VAN-REF #1 sair 30 min atrasada?" |
| `historico(dias)` | "Como foi a semana?" |

Ferramentas no lugar de despejar o JSON inteiro reduzem tokens (o JSON de 40 paradas tem
cerca de 30 KB), permitem perguntas "e se?" calculadas de verdade e tornam a resposta
auditável: a interface mostra quais ferramentas foram chamadas e o que retornaram.

## Técnicas de prompt engineering

| Técnica | Onde | Efeito |
|---|---|---|
| Papel e contexto do domínio | `sistema_base.md` | tom e vocabulário de logística hospitalar |
| Regras de *grounding* ("use SOMENTE os dados", "copie números exatamente") | `sistema_base.md` | menos alucinação numérica, medido pela fidelidade |
| Dados estruturados em JSON enxuto | todos | o modelo recebe só os campos relevantes |
| Formato de saída explícito (seções fixas) | instruções e relatórios | saída previsível e fácil de avaliar |
| Exemplo de linha (*one-shot*) | `instrucoes_motorista.md` | formato consistente das paradas e alertas |
| Ordem e nomes exatos exigidos | `instrucoes_motorista.md` | permite medir cobertura e ordem |
| Evidências pré-calculadas (sugestões por regra, entregas em risco) | `relatorio_execucao.md` | a LLM interpreta em vez de calcular |
| Ferramentas descritas com exemplos de argumento | `tools.py` | menos chamadas com argumento inválido |
| Temperatura baixa (0,2) | configuração | respostas estáveis entre execuções |
| Aviso de baixa confiança com poucos dados | `relatorio_periodo.md` | evita conclusões infundadas |

## Avaliação de qualidade

Cada texto gerado recebe uma nota de 0 a 100, salva no histórico:

1. **Fidelidade numérica**: extrai todos os números e horários do texto (entende o formato
   brasileiro, `1.234,50`) e verifica se existem nos dados de origem, com tolerância de
   arredondamento. Isso detecta alucinação de forma objetiva.
2. **Cobertura e ordem** (instruções): todas as paradas foram citadas? Na ordem planejada?
3. **LLM como juiz** (opcional, `LLM_JUDGE=1`): rubrica de 1 a 5 para clareza, correção,
   acionabilidade e segurança do paciente.

Nota = 60% fidelidade + 40% cobertura (instruções) ou 100% fidelidade (relatórios). Com o
juiz ativo, a nota é a média entre a parte automática e a rubrica.

Com o modelo local, use a aba **Relatórios → Textos gerados e avaliação** para comparar
provedores e versões de prompt. Os números entram no relatório técnico.
