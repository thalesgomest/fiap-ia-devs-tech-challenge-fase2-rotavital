import time

import pytest
from fastapi.testclient import TestClient

from rotavital.api.main import app

client = TestClient(app)


@pytest.fixture(scope="module")
def finished_run():
    resp = client.post(
        "/api/execucoes",
        json={"cenario_id": "sp-mini-8", "preset": "rapido", "config": {"generations": 30, "seed": 1}},
    )
    assert resp.status_code == 202
    run_id = resp.json()["id"]
    for _ in range(200):
        status = client.get(f"/api/execucoes/{run_id}/progresso").json()["status"]
        if status != "executando":
            break
        time.sleep(0.1)
    assert status == "concluido"
    return client.get(f"/api/execucoes/{run_id}").json()


def test_status_reports_offline_mode():
    body = client.get("/api/status").json()
    assert body["llm"]["modo"] == "offline"


def test_scenarios_and_presets():
    ids = {s["id"] for s in client.get("/api/cenarios").json()}
    assert "sp-mini-8" in ids
    assert client.get("/api/cenarios/sp-mini-8").json()["paradas"]
    assert client.get("/api/cenarios/nao-existe").status_code == 404
    assert set(client.get("/api/presets").json()) == {"rapido", "equilibrado", "qualidade"}


def test_run_lifecycle(finished_run):
    sol = finished_run["solucao"]
    assert sol["entregas"] == 8
    assert finished_run["comparativo"]["melhor_baseline"]
    assert any(r["id"] == finished_run["id"] for r in client.get("/api/execucoes").json())


def test_llm_endpoints_offline(finished_run):
    run_id = finished_run["id"]
    vehicle = finished_run["solucao"]["rotas"][0]["veiculo"]
    instr = client.post(f"/api/execucoes/{run_id}/instrucoes", json={"veiculo": vehicle}).json()
    assert vehicle in instr["markdown"] and instr["avaliacao"]["nota_geral"] >= 90
    assert client.post(f"/api/execucoes/{run_id}/instrucoes", json={"veiculo": "X #9"}).status_code == 404
    report = client.post(f"/api/execucoes/{run_id}/relatorio").json()
    assert report["markdown"].startswith("# Relatório")
    chat = client.post(
        f"/api/execucoes/{run_id}/chat",
        json={"mensagens": [{"papel": "usuario", "conteudo": "Quais entregas estão em risco?"}]},
    ).json()
    assert chat["ferramentas"][0]["nome"] == "entregas_em_risco"
    period = client.get("/api/relatorios/periodo?dias=7").json()
    assert period["execucoes"] >= 1
    texts = client.get(f"/api/execucoes/{run_id}/textos").json()
    assert {t["kind"] for t in texts} >= {"instrucoes", "relatorio_execucao"}


def test_fleet_override_validation():
    resp = client.post(
        "/api/execucoes",
        json={"cenario_id": "sp-mini-8", "frota": [{"codigo": "VAN-REF", "capacidade_kg": 1}, {"codigo": "MOTO", "capacidade_kg": 1}]},
    )
    assert resp.status_code == 422  # carga refrigerada deixa de caber em qualquer veículo


def test_csv_import(tmp_path, monkeypatch):
    from rotavital.config import settings

    monkeypatch.setattr(settings, "scenarios_dir", settings.scenarios_dir)
    csv_content = "id,nome,lat,lon,demanda_kg,prioridade,refrigerado\nX1,UBS Nova,-23.55,-46.64,10,alta,sim\n"
    resp = client.post(
        "/api/cenarios/importar",
        data={"nome": "Teste CSV pytest", "base_id": "sp-mini-8"},
        files={"arquivo": ("paradas.csv", csv_content, "text/csv")},
    )
    assert resp.status_code == 200, resp.text
    created = resp.json()["id"]
    assert client.get(f"/api/cenarios/{created}").json()["paradas"][0]["nome"] == "UBS Nova"
    (settings.scenarios_dir / f"{created}.json").unlink()

def test_chat_exposes_llm_failure_instead_of_disguised_offline_success(finished_run, monkeypatch):
    from rotavital.config import settings
    from rotavital.llm.providers.base import LLMError

    def fail(*args, **kwargs):
        raise LLMError("falha controlada do modelo local")

    monkeypatch.setattr(settings, "llm_fallback_offline", False)
    monkeypatch.setattr("rotavital.api.main.assistant.answer", fail)
    response = client.post(f"/api/execucoes/{finished_run['id']}/chat", json={
        "mensagens": [{"papel": "usuario", "conteudo": "Qual é a distância?"}],
    })
    assert response.status_code == 503
    assert "falha controlada" in response.json()["detail"]
