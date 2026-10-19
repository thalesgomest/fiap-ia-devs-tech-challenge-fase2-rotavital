# Qwen3 local no RotaVital

O diretório `fiap-ia-devs-tech-challenge-fase2-rotavital` é o projeto principal. Ele usa sua própria API, interface, domínio, ambiente Python, banco e runtime. O projeto anterior é referência histórica da configuração do modelo, não uma dependência de execução.

## Iniciar nesta máquina

No PowerShell:

```powershell
cd C:\repos\fiap-ia-devs-tech-challenge-fase2-rotavital
.\scripts\start-local.ps1
```

Abra `http://127.0.0.1:8000`. O script inicia o Ollama em loopback e a aplicação; se o RotaVital já estiver ativo na porta, informa o endereço. Use `-Port 8080` para outra porta. O servidor Ollama fica em segundo plano; ele é um serviço separado da aplicação. Para encerrar um aplicativo iniciado no terminal, use `Ctrl+C`.

A preparação desta máquina reaproveitou o Qwen3 já baixado e deixou os arquivos em `.runtime/ollama/` deste projeto. Os blobs grandes e o GGUF foram ligados por hardlinks no mesmo volume, com caminhos próprios: remover o nome do arquivo do projeto anterior não remove o conteúdo acessível pelo novo projeto. Binários e pequenos manifestos foram copiados. Não existe importação Python do RotaMed.

## Preparar uma cópia nova

```powershell
py -3.11 scripts/tasks.py setup
.\scripts\setup-ollama.ps1
.\scripts\start-local.ps1
```

A primeira preparação pode baixar alguns GB. Os scripts fixam o Ollama 0.40.4 e validam o checksum oficial da distribuição; a importação do Qwen3 fixa revisão e SHA-256 do GGUF oficial. Os arquivos locais, `.env`, dados e pesos são ignorados pelo Git. Não é necessário cadastrar uma chave de API ou pagar um provedor para essa integração.

Caso o PowerShell bloqueie o script, execute-o em um processo com política válida somente para essa chamada:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-local.ps1
```

Os comandos existentes `make app`, `make demo` e `make doctor` continuam disponíveis. No Windows, `make llm` usa o preparador portátil; em Linux/macOS, utiliza o Ollama instalado. A verificação desta integração foi local no Windows; o Docker não foi executado nesta rodada.

## Usar o chat da interface

1. Selecione um cenário, por exemplo `sp-mini-8` para uma primeira execução curta.
2. Confira frota/regras e inicie a otimização. Aguarde a conclusão.
3. Abra **Assistente**, na etapa 5, ou carregue uma execução pelo **Histórico**.
4. Confira no topo `LLM: ollama · qwen3:4b` e `online`.
5. Faça uma pergunta ou use uma sugestão. O veículo e a parada das sugestões vêm da execução aberta.

Exemplos: “Quais entregas críticas estão em risco?”, “Qual é o horário de retorno da MOTO #1?” ou “Se esse veículo atrasar trinta minutos, quais entregas são afetadas?”. Use o identificador que aparece nas rotas da sua execução; os nomes não são iguais em todos os cenários.

Diferentemente do terminal de perguntas do protótipo anterior, o RotaVital envia até as últimas 12 mensagens da conversa. O modelo deve consultar novamente as ferramentas para obter números, sem tratar uma resposta anterior como nova evidência. Rotas de outra execução têm outro contexto.

## Modelo e configuração

A configuração local fica no `.env`; exemplos em `.env.example`:

```dotenv
LLM_PROVIDER=ollama
LLM_FALLBACK_OFFLINE=0
LLM_TEMPERATURE=0
LLM_TIMEOUT_S=300
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3:4b
OLLAMA_THINK=0
OLLAMA_NUM_CTX=8192
OLLAMA_NUM_PREDICT=512
OLLAMA_SEED=2026
OLLAMA_KEEP_ALIVE=10m
```

`think=false` evita gastar a resposta em raciocínio interno no modelo usado. O contexto e o limite de saída também se aplicam ao chat com ferramentas. Em instruções/relatórios, o chamador pode solicitar outro limite de saída. Temperatura e semente não garantem respostas idênticas entre versões e plataformas.

`LLM_TIMEOUT_S` é o prazo de cada chamada; uma pergunta com ferramentas pode precisar de mais de uma chamada. O primeiro carregamento em CPU pode levar minutos. Não há streaming de tokens nesta interface: o indicador aguarda a resposta completa.

No chat, `LLM_FALLBACK_OFFLINE=0` faz uma falha chegar como erro HTTP 503, visível na interface. Com `1`, a contingência é explicitamente identificada como offline. O modo offline não conta como uma chamada real ao Qwen3. Reinicie a aplicação após alterar o `.env`.

O modelo foi importado do [GGUF oficial da Qwen](https://huggingface.co/Qwen/Qwen3-4B-GGUF), revisão `bc640142c66e1fdd12af0bd68f40445458f3869b`, quantização **Q4_K_M**. Não houve fine-tuning.

- Pesos SHA-256: `7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5`.
- Digest local verificado: `9a09256a51fe03679e2c348cfcb337dd7cbfe3cbeed790db4eba1b854f46d3b2`.
- Origem/importação: `.runtime/ollama/imported-model-manifest.json`.

O nome `qwen3:4b` sozinho não identifica os mesmos bytes em qualquer instalação. `/api/status` informa o digest do modelo detectado. Os hashes acima correspondem à importação efetivamente reaproveitada dos testes anteriores.

## O que foi integrado

Interface → `POST /api/execucoes/{id}/chat` → assistente → Ollama `/api/chat` → ferramentas Python → resposta com provedor, modelo e ferramentas consultadas.

Foram reaproveitados os pesos e as escolhas de inferência do projeto anterior, adaptados à arquitetura de ferramentas do RotaVital. Não copiamos a representação genética, fitness ou dados do RotaMed sobre o domínio novo. Custos em reais aqui são estimativas parametrizadas do cenário do RotaVital; a fitness sem unidade do protótipo anterior não foi convertida em dinheiro.

O transporte local ignora proxies do ambiente. Respostas HTTP inválidas, sem mensagem ou vazias viram erro, em vez de um sucesso vazio. O histórico existente continua registrando as respostas de LLM. A camada de ferramentas também restringe a prioridade quando o usuário pede uma categoria única; não permite que o modelo troque uma consulta crítica por alta. Zero ocorrências é uma contagem calculada e não informação ausente.

Os formatos de tool calling e o parâmetro de raciocínio seguem a [documentação oficial do Ollama](https://docs.ollama.com/capabilities/tool-calling) e a [opção de thinking](https://docs.ollama.com/capabilities/thinking). Ferramentas e prompts não garantem verdade semântica. As respostas continuam precisando de revisão.

## Verificar

```powershell
.\venv\Scripts\python.exe -m pytest
.\venv\Scripts\python.exe -m pip check
.\venv\Scripts\python.exe -X utf8 scripts/verify-qwen3.py
```

O último comando exige aplicativo e Ollama iniciados. Cria uma execução pequena e faz perguntas reais; rejeita provedor offline e salva cenário, resposta, ferramentas, identidade do modelo e tempos em uma pasta nova de `data/evidencias/`. A seleção de ferramentas é uma checagem de referência, não uma taxa geral de acerto. Revise também os textos.

A avaliação inicial foi preservada em `data/evidencias/qwen3-4afa2b63/`: o Qwen3 respondeu pela integração real, mas confundiu prioridade alta com crítica na pergunta de riscos. Isso levou ao filtro em Python e a testes de regressão. É um ajuste em caso conhecido, não uma avaliação independente de generalização. Os detalhes e a verificação após a correção estão em [Validação da integração](validacao-qwen3.md).

## Se algo falhar

- **Ollama indisponível:** execute `scripts/setup-ollama.ps1`; veja os logs em `.runtime/ollama/server.stderr.log`.
- **Modelo não disponível:** confira `/api/tags` e o `.env`; o nome local configurado é `qwen3:4b`.
- **Erro 503 no chat:** a consulta real falhou; examine a mensagem. Não é uma confirmação de resposta da LLM.
- **Assistente bloqueado:** conclua uma otimização ou abra uma execução no Histórico.
- **Porta em uso por outro aplicativo:** use `scripts/start-local.ps1 -Port 8080`.
- **Interface antiga em cache:** atualize a página com `Ctrl+F5` após as alterações de JavaScript.

Esta integração não constitui uma revisão completa do algoritmo, do modelo de custos ou da validade operacional do novo projeto, nem uma validação clínica. Ela conecta e verifica a camada de linguagem no fluxo do chat.
