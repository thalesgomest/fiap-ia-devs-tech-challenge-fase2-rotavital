"""API REST do RotaVital + servidor da interface web.

Execute com ``make app`` (ou ``uvicorn rotavital.api.main:app``) e abra
http://localhost:8000 - a documentação interativa fica em http://localhost:8000/docs.
"""

from __future__ import annotations

import mimetypes
from dataclasses import replace
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from rotavital import __version__
from rotavital.api.schemas import ChatRequest, InstructionsRequest, RunRequest
from rotavital.domain.scenarios import (
    ScenarioError,
    list_scenarios,
    load_scenario,
    save_scenario,
    scenario_from_dict,
    scenario_to_file_dict,
    stops_from_csv,
)
from rotavital.llm import assistant, get_provider, llm_status, reports
from rotavital.llm.providers.base import LLMError
from rotavital.optimization.ga import PRESETS
from rotavital.services import JobManager, apply_fleet_override
from rotavital.storage.history import HistoryStore

STATIC_DIR = Path(__file__).resolve().parents[1] / "web" / "static"

app = FastAPI(
    title="RotaVital API",
    version=__version__,
    description=(
        "Roteirização de hemocomponentes, vacinas e insumos hospitalares com algoritmo "
        "genético e assistente baseado em LLM."
    ),
)
store = HistoryStore()
jobs = JobManager(store)


@app.exception_handler(LLMError)
async def llm_error_handler(request: Request, exc: LLMError):
    return JSONResponse(status_code=503, content={"detail": f"Não foi possível consultar a LLM: {exc}"})


def _run_or_404(run_id: str) -> dict:
    job = jobs.get(run_id)
    if job and job.result:
        return job.result
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(404, "Execução não encontrada ou ainda em andamento")
    return run


# ------------------------------------------------------------------ status
@app.get("/api/status", tags=["sistema"])
def status():
    return {"versao": __version__, "llm": llm_status()}


# ---------------------------------------------------------------- cenários
@app.get("/api/cenarios", tags=["cenários"])
def get_scenarios():
    return list_scenarios()


@app.get("/api/cenarios/{scenario_id}", tags=["cenários"])
def get_scenario(scenario_id: str):
    try:
        return scenario_to_file_dict(load_scenario(scenario_id))
    except ScenarioError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/api/cenarios/importar", tags=["cenários"])
async def import_scenario(
    arquivo: UploadFile = File(..., description="CSV de paradas"),
    nome: str = Form(...),
    base_id: str = Form(..., description="Cenário de onde vêm depósito, frota e regras"),
):
    """Cria um cenário novo a partir de um CSV, reaproveitando frota e regras de outro."""
    try:
        base = scenario_to_file_dict(load_scenario(base_id))
        content = (await arquivo.read()).decode("utf-8-sig")
        base["paradas"] = stops_from_csv(content)
        base["nome"] = nome
        base["id"] = "importado-" + "".join(c if c.isalnum() else "-" for c in nome.lower()).strip("-")
        base["descricao"] = f"Importado de {arquivo.filename} com frota de '{base_id}'."
        scenario = scenario_from_dict(base)
    except (ScenarioError, UnicodeDecodeError) as exc:
        raise HTTPException(422, str(exc)) from exc
    save_scenario(scenario)
    return {"id": scenario.id, "nome": scenario.name, "paradas": len(scenario.stops)}


# --------------------------------------------------------------- execuções
@app.get("/api/presets", tags=["otimização"])
def get_presets():
    return {name: cfg.to_dict() for name, cfg in PRESETS.items()}


@app.post("/api/execucoes", tags=["otimização"], status_code=202)
def start_run(req: RunRequest):
    if req.preset not in PRESETS:
        raise HTTPException(422, f"Preset desconhecido: {req.preset}")
    try:
        scenario = load_scenario(req.cenario_id)
        scenario = apply_fleet_override(
            scenario, [f.model_dump(exclude_none=True) for f in req.frota]
        )
        scenario_from_dict(scenario_to_file_dict(scenario))  # revalida após ajustes
    except ScenarioError as exc:
        raise HTTPException(422, str(exc)) from exc
    overrides = req.config.model_dump(exclude_none=True)
    config = replace(PRESETS[req.preset], **overrides)
    job = jobs.start(scenario, config)
    return {"id": job.id}


@app.get("/api/execucoes", tags=["otimização"])
def list_runs(limite: int = Query(30, ge=1, le=200)):
    return store.list_runs(limite)


@app.get("/api/execucoes/{run_id}/progresso", tags=["otimização"])
def run_progress(run_id: str, desde: int = Query(0, ge=0)):
    job = jobs.get(run_id)
    if not job:
        if store.get_run(run_id):
            return {"id": run_id, "status": "concluido"}
        raise HTTPException(404, "Execução não encontrada")
    return job.snapshot(desde)


@app.post("/api/execucoes/{run_id}/parar", tags=["otimização"])
def stop_run(run_id: str):
    if not jobs.stop(run_id):
        raise HTTPException(404, "Execução não está em andamento")
    return {"ok": True}


@app.get("/api/execucoes/{run_id}", tags=["otimização"])
def get_run(run_id: str):
    return _run_or_404(run_id)


# --------------------------------------------------------------------- LLM
@app.post("/api/execucoes/{run_id}/instrucoes", tags=["assistente"])
def driver_instructions(run_id: str, req: InstructionsRequest):
    run = _run_or_404(run_id)
    try:
        return reports.driver_instructions(run, req.veiculo, get_provider(), store)
    except KeyError:
        raise HTTPException(404, f"Veículo {req.veiculo} não existe nesta execução") from None


@app.post("/api/execucoes/{run_id}/relatorio", tags=["assistente"])
def execution_report(run_id: str):
    return reports.execution_report(_run_or_404(run_id), get_provider(), store)


@app.post("/api/execucoes/{run_id}/chat", tags=["assistente"])
def chat(run_id: str, req: ChatRequest):
    run = _run_or_404(run_id)
    messages = [m.model_dump() for m in req.mensagens]
    return assistant.answer(run, messages, get_provider(), store)


@app.get("/api/execucoes/{run_id}/textos", tags=["assistente"])
def run_llm_outputs(run_id: str):
    return store.list_llm_outputs(run_id)


@app.get("/api/relatorios/periodo", tags=["assistente"])
def period_report(dias: int = Query(7, ge=1, le=90)):
    return reports.period_report(store, dias, get_provider())


# ---------------------------------------------------------------- frontend
@app.get("/", include_in_schema=False)
def index(_: Optional[str] = None):
    return FileResponse(STATIC_DIR / "index.html")


# O registro do Windows pode mapear .js como text/plain, o que impede o navegador de
# carregar módulos ES - força o tipo correto.
mimetypes.add_type("text/javascript", ".js")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
