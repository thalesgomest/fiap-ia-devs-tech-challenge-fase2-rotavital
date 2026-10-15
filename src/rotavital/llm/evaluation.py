"""Avaliação automática da qualidade dos textos gerados pela LLM.

Três métricas complementares:
  1. Fidelidade numérica - todo número/horário citado no texto existe nos dados de origem?
     (detecta alucinação de forma objetiva e barata);
  2. Cobertura e ordem - nas instruções do motorista, todas as paradas aparecem e na
     ordem correta?
  3. LLM-como-juiz (opcional, LLM_JUDGE=1) - rubrica de clareza, correção,
     acionabilidade e segurança, de 1 a 5.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Iterable, List, Optional, Set

from rotavital.llm.prompts import render

_TIME_RE = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b")
_NUM_RE = re.compile(r"(?<![\w#])(\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?)(?![\w])")
_LIST_MARKER_RE = re.compile(r"^\s*\d+[.)]\s", re.MULTILINE)


def _collect(value: Any, numbers: List[float], times: Set[str]) -> None:
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, (int, float)):
        numbers.append(float(value))
        if 0 < abs(value) <= 1:  # taxas 0-1 também podem aparecer como porcentagem
            numbers.append(float(value) * 100)
    elif isinstance(value, str):
        for h, m in _TIME_RE.findall(value):
            times.add(f"{int(h):02d}:{m}")
        for raw in _NUM_RE.findall(value):
            parsed = _parse_number(raw)
            if parsed is not None:
                numbers.append(parsed)
    elif isinstance(value, dict):
        for v in value.values():
            _collect(v, numbers, times)
    elif isinstance(value, (list, tuple)):
        for v in value:
            _collect(v, numbers, times)


def _parse_number(raw: str) -> Optional[float]:
    try:
        if "," in raw:  # padrão brasileiro: 1.234,5
            return float(raw.replace(".", "").replace(",", "."))
        if re.fullmatch(r"\d{1,3}(\.\d{3})+", raw):  # 1.234 = milhar
            return float(raw.replace(".", ""))
        return float(raw)
    except ValueError:
        return None


def numeric_faithfulness(text: str, facts: Any) -> dict:
    fact_numbers: List[float] = []
    fact_times: Set[str] = set()
    _collect(facts, fact_numbers, fact_times)

    clean = _LIST_MARKER_RE.sub(" ", text)  # "3. " de listas numeradas não é um fato
    unsupported, checked = [], 0
    for h, m in _TIME_RE.findall(clean):
        checked += 1
        stamp = f"{int(h):02d}:{m}"
        if stamp not in fact_times:
            unsupported.append(stamp)
    without_times = _TIME_RE.sub(" ", clean)
    for raw in _NUM_RE.findall(without_times):
        value = _parse_number(raw)
        if value is None or value in (0, 1, 2, 8):  # contagens triviais e "2 °C a 8 °C"
            continue
        checked += 1
        tolerance = lambda f: max(0.6, abs(f) * 0.01)  # noqa: E731 - arredondamentos
        if not any(abs(value - f) <= tolerance(f) for f in fact_numbers):
            unsupported.append(raw)
    score = 1.0 if checked == 0 else (checked - len(unsupported)) / checked
    return {"score": round(score, 3), "verificados": checked, "nao_suportados": unsupported[:15]}


def coverage(text: str, names: Iterable[str]) -> dict:
    lowered = text.lower()
    positions, missing = [], []
    for name in names:
        pos = lowered.find(name.lower())
        if pos < 0:
            missing.append(name)
        else:
            positions.append(pos)
    names = list(names)
    found = len(names) - len(missing)
    pairs = max(len(positions) - 1, 0)
    ordered = sum(1 for a, b in zip(positions, positions[1:], strict=False) if a < b)
    return {
        "score": round(found / len(names), 3) if names else 1.0,
        "ordem_correta": round(ordered / pairs, 3) if pairs else 1.0,
        "faltando": missing,
    }


def judge(provider, kind: str, text: str, facts: Any) -> Optional[dict]:
    if provider.offline or os.environ.get("LLM_JUDGE", "0") not in ("1", "true", "yes"):
        return None
    prompt = render("juiz", tipo=kind, dados=json.dumps(facts, ensure_ascii=False), texto=text)
    try:
        raw = provider.complete("Você é um avaliador rigoroso e imparcial.", prompt, max_tokens=400)
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        data = json.loads(match.group(0)) if match else None
        keys = ("clareza", "correcao", "acionabilidade", "seguranca")
        if not data or not all(isinstance(data.get(k), (int, float)) for k in keys):
            return None
        return {**{k: max(1, min(5, int(data[k]))) for k in keys}, "comentario": str(data.get("comentario", ""))}
    except Exception:  # noqa: BLE001 - avaliação é opcional, nunca derruba a resposta
        return None


def evaluate(provider, kind: str, text: str, facts: Any, stop_names: Optional[List[str]] = None) -> dict:
    faith = numeric_faithfulness(text, facts)
    cov = coverage(text, stop_names) if stop_names else None
    verdict = judge(provider, kind, text, facts)

    auto = faith["score"] * 100
    if cov:
        auto = 0.6 * auto + 0.4 * (cov["score"] * 0.7 + cov["ordem_correta"] * 0.3) * 100
    overall = auto
    if verdict:
        rubric = sum(verdict[k] for k in ("clareza", "correcao", "acionabilidade", "seguranca")) / 20 * 100
        overall = 0.5 * auto + 0.5 * rubric
    return {
        "nota_geral": round(overall),
        "fidelidade_numerica": faith,
        "cobertura": cov,
        "juiz": verdict,
    }
