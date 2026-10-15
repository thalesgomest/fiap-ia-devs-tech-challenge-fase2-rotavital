# Integração com LLM

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
2. **Usa Ollama como padrão**: LLM local (Llama 3.1 8B, citado no enunciado como família
   LLaMA), gratuita e offline.
3. **Troca de provedor com uma variável**: `LLM_PROVIDER=ollama|openai|anthropic|offline`.
4. **Nunca quebra**: sem LLM disponível, cai para textos determinísticos e sinaliza isso na interface.

| Provedor | Quando usar | Custo | Qualidade em pt-BR / ferramentas |
|---|---|---|---|
| `ollama` (llama3.1:8b, qwen2.5:7b) | padrão, demonstração local | grátis (CPU/GPU local) | boa / boa no Qwen 2.5 e no Llama 3.1 |
| `openai` (qualquer API compatível) | OpenAI, Groq, OpenRouter, LM Studio, Gemini | por token | muito boa |
| `anthropic` (Claude via SDK oficial) | melhor qualidade de raciocínio e ferramentas | por token | excelente |
| `offline` | testes, CI, sem internet | grátis | textos fixos |

Para usar o Claude: `LLM_PROVIDER=anthropic` e a credencial em
`ANTHROPIC_API_KEY` (ou `ant auth login`). O modelo padrão é `claude-opus-5-5`, com esforço
`medium` (`ANTHROPIC_EFFORT`). As chamadas habilitam o fallback do lado do servidor
(`fallbacks="default"`), e uma eventual recusa é tratada e devolvida como mensagem amigável.

## Requisitos de hardware para o Ollama local

O modelo roda inteiro na máquina. Ele precisa caber na **memória de vídeo (VRAM)** da GPU
ou, sem GPU compatível, na **memória RAM livre**, e na CPU fica bem mais lento. Os valores
abaixo são para os modelos quantizados padrão do Ollama (Q4) com o contexto usado pelo
RotaVital (`num_ctx` = 8192 tokens, que acrescenta cerca de 1 GB ao tamanho do arquivo).

| Modelo (`OLLAMA_MODEL`) | Download | Mínimo para rodar | Recomendado | Ferramentas | Uso |
|---|---|---|---|---|---|
| `llama3.2:1b` | 1,3 GB | 8 GB de RAM total, sem GPU | GPU com 4 GB | sim | só para testar o fluxo (qualidade baixa em pt-BR) |
| `llama3.2:3b` | 2,0 GB | 8 GB de RAM total **com ~4 GB livres**, sem GPU | GPU com 4 GB de VRAM | sim | **máquinas modestas** |
| `qwen2.5:3b` | 1,9 GB | igual ao anterior | GPU com 4 GB de VRAM | sim | alternativa ao 3B, bom em ferramentas |
| `llama3.1:8b` (padrão) | 4,9 GB | 16 GB de RAM total **ou** GPU com 6 GB de VRAM | GPU com 8 GB de VRAM | sim | melhor qualidade local |
| `qwen2.5:7b` | 4,7 GB | igual ao `llama3.1:8b` | GPU com 8 GB de VRAM | sim | alternativa ao 8B, ótimo em ferramentas |

Também são necessários: cerca de 10 GB de disco livre, Windows 10+, macOS 12+ ou Linux, e
para GPU uma NVIDIA com drivers atuais (ou Apple Silicon, que usa a memória unificada).
O modelo precisa suportar **ferramentas (function calling)**: todos da tabela suportam.
Modelos sem esse suporte funcionam no modo de contexto compacto, com respostas menos
precisas.

### Caso medido: abaixo do mínimo

Máquina de desenvolvimento: Intel Core i5-4440 (4 núcleos), **8 GB de RAM (0,9 GB livre)** e
GeForce GTX 960 com **2 GB de VRAM**.

- `llama3.1:8b` **não rodou**: o Ollama colocou 0 de 33 camadas na GPU (2 GB não comportam o
  modelo), tentou carregar os 4,7 GB na RAM, que estava quase toda ocupada, e desistiu depois
  de 18 minutos sem gerar nenhuma resposta.
- Nesse cenário o RotaVital cortou a chamada no prazo (`LLM_TIMEOUT_S`) e entregou a folha de
  rota pelo modelo determinístico, sinalizando a contingência na interface.

Para uma máquina assim, use `llama3.2:3b` e feche outros programas pesados (navegador com
muitas abas, IDE) antes de carregar o modelo.

### Como trocar de modelo

```bash
make llm OLLAMA_MODEL=llama3.2:3b     # ou: ollama pull llama3.2:3b
```

Depois, no `.env`, defina `OLLAMA_MODEL=llama3.2:3b` e reinicie o app. `make doctor` confirma
se o modelo configurado está baixado.

### Tempos esperados e `LLM_TIMEOUT_S`

- A **primeira chamada** inclui carregar o modelo na memória: de segundos (GPU, SSD) a
  minutos (CPU, HD). As seguintes são mais rápidas enquanto o modelo continua carregado
  (o Ollama o mantém por 5 minutos sem uso).
- Uma folha de rota tem cerca de 400 a 800 tokens. Na CPU, modelos 7-8B costumam gerar
  poucos tokens por segundo, então cada texto pode levar minutos.
- `LLM_TIMEOUT_S` (padrão 120 s) é o prazo **total** de cada chamada. Em máquina lenta,
  aumente para 300 s; ao estourar, o app usa o texto de contingência em vez de travar.

Sem hardware adequado, a alternativa é um provedor em nuvem (`LLM_PROVIDER=openai` ou
`anthropic`), que roda em qualquer máquina com internet.

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
