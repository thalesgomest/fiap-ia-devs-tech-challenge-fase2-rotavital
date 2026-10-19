# RotaVital - comandos do projeto (Windows, macOS e Linux)
#
#   make demo   -> prepara tudo (na primeira vez), roda os testes e sobe o app
#   make help   -> lista todos os comandos
#
# A lógica dependente de sistema operacional fica em scripts/tasks.py.

ifeq ($(OS),Windows_NT)
    # Fixa o cmd.exe para não depender de um sh.exe (ex.: Git Bash) que esteja no PATH
    SHELL := cmd.exe
    .SHELLFLAGS := /c
    VPY := venv\Scripts\python.exe
    LAUNCHER := $(shell where py >NUL 2>&1 && echo py -3|| echo python)
    BLANK := echo.
else
    VPY := venv/bin/python
    LAUNCHER := $(shell command -v python3 2>/dev/null || echo python)
    BLANK := echo
endif

STAMP := venv/.instalado
PORTA ?= 8000
CENARIO ?= sp-hemorrede-40
SEMENTES ?= 3
OLLAMA_MODEL ?= qwen3:4b

# Repassa um interpretador específico, se informado: make setup PYTHON=caminho/do/python
ifdef PYTHON
    export ROTAVITAL_PYTHON := $(PYTHON)
endif

.DEFAULT_GOAL := help
.PHONY: help demo setup doctor app dev test lint format experimentos cenarios llm docker clean reset

help:
	@$(BLANK)
	@echo RotaVital - comandos disponiveis
	@$(BLANK)
	@echo   make demo           prepara o ambiente, roda os testes e sobe o app - recomendado
	@echo   make doctor         verifica o ambiente e diz o que falta
	@echo   make app            sobe o app em http://localhost:$(PORTA)
	@echo   make test           roda os testes automatizados
	@echo   make experimentos   experimentos do GA - CENARIO=$(CENARIO) SEMENTES=$(SEMENTES)
	@echo   make llm            baixa o modelo local do Ollama - $(OLLAMA_MODEL)
	@echo   make docker         sobe app + Ollama via Docker
	@echo   make setup          reinstala as dependencias
	@echo   make lint / format  analise estatica / formatacao
	@echo   make cenarios       regenera os cenarios sinteticos
	@echo   make clean / reset  limpa caches / remove o ambiente virtual
	@$(BLANK)
	@echo Exemplo: make experimentos SEMENTES=10

# O ambiente é (re)instalado automaticamente quando não existe ou quando as dependências mudam
$(STAMP): requirements.txt pyproject.toml
	$(LAUNCHER) scripts/tasks.py setup

setup:
	$(LAUNCHER) scripts/tasks.py setup

doctor:
	$(LAUNCHER) scripts/tasks.py doctor

demo: $(STAMP)
	$(VPY) -m pytest -q
	@$(BLANK)
	@echo Abra http://localhost:$(PORTA) - documentacao da API em /docs - Ctrl+C para encerrar
	$(VPY) -m uvicorn rotavital.api.main:app --port $(PORTA)

app: $(STAMP)
	$(VPY) -m uvicorn rotavital.api.main:app --port $(PORTA)

dev: $(STAMP)
	$(VPY) -m uvicorn rotavital.api.main:app --reload --port $(PORTA)

test: $(STAMP)
	$(VPY) -m pytest

lint: $(STAMP)
	$(VPY) -m ruff check src tests scripts

format: $(STAMP)
	$(VPY) -m ruff check --fix src tests scripts
	$(VPY) -m ruff format src tests scripts

experimentos: $(STAMP)
	$(VPY) -m rotavital.optimization.experiments --cenario $(CENARIO) --sementes $(SEMENTES)

cenarios: $(STAMP)
	$(VPY) scripts/gerar_cenario.py

llm:
ifeq ($(OS),Windows_NT)
	powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/setup-ollama.ps1 -Model "$(OLLAMA_MODEL)"
else
	ollama pull $(OLLAMA_MODEL)
endif

docker:
	docker compose up --build

clean:
	$(LAUNCHER) scripts/tasks.py clean

reset:
	$(LAUNCHER) scripts/tasks.py reset
