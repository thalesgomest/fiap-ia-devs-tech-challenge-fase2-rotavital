"""Modelos de entrada da API (Pydantic). As respostas são dicionários JSON documentados."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class GAOverrides(BaseModel):
    population_size: Optional[int] = Field(None, ge=10, le=1000)
    generations: Optional[int] = Field(None, ge=1, le=5000)
    crossover: Optional[str] = Field(None, pattern="^(ox|pmx|erx)$")
    crossover_rate: Optional[float] = Field(None, ge=0, le=1)
    mutation_rate: Optional[float] = Field(None, ge=0, le=1)
    tournament_k: Optional[int] = Field(None, ge=2, le=10)
    elitism: Optional[int] = Field(None, ge=0, le=20)
    seed_ratio: Optional[float] = Field(None, ge=0, le=1)
    local_search_every: Optional[int] = Field(None, ge=0, le=100)
    stagnation_limit: Optional[int] = Field(None, ge=5, le=5000)
    time_limit_s: Optional[float] = Field(None, ge=1, le=1800)
    seed: Optional[int] = None


class FleetOverride(BaseModel):
    codigo: str
    quantidade: Optional[int] = Field(None, ge=0, le=50)
    capacidade_kg: Optional[float] = Field(None, gt=0)
    autonomia_km: Optional[float] = Field(None, gt=0)
    custo_fixo: Optional[float] = Field(None, ge=0)
    custo_km: Optional[float] = Field(None, ge=0)
    jornada_max_min: Optional[int] = Field(None, gt=0)


class RunRequest(BaseModel):
    cenario_id: str
    preset: str = "equilibrado"
    config: GAOverrides = GAOverrides()
    frota: List[FleetOverride] = []


class InstructionsRequest(BaseModel):
    veiculo: str


class ChatMessage(BaseModel):
    papel: str = Field(..., pattern="^(usuario|assistente)$")
    conteudo: str = Field(..., min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    mensagens: List[ChatMessage]
