import pytest

from rotavital.domain.scenarios import (
    ScenarioError,
    list_scenarios,
    load_scenario,
    scenario_from_dict,
    scenario_to_file_dict,
    stops_from_csv,
)
from rotavital.optimization.evaluator import RouteEvaluator


def test_bundled_scenarios_load_and_are_feasible():
    items = list_scenarios()
    assert {"sp-hemorrede-40", "sp-homecare-18", "sp-mini-8"} <= {i["id"] for i in items}
    for item in items:
        RouteEvaluator(load_scenario(item["id"]))  # lança se houver parada inatingível


def test_round_trip_file_format(small_scenario):
    again = scenario_from_dict(scenario_to_file_dict(small_scenario))
    assert again.stops == small_scenario.stops
    assert again.fleet == small_scenario.fleet


def test_csv_import_accepts_semicolon_and_decimal_comma():
    content = (
        "id;nome;lat;lon;demanda_kg;prioridade;refrigerado;janela_inicio;janela_fim\n"
        "A1;UBS Teste;-23,55;-46,63;12,5;alta;sim;08:00;12:00\n"
    )
    rows = stops_from_csv(content)
    assert rows[0]["lat"] == "-23.55" and rows[0]["demanda_kg"] == "12.5"


def test_csv_missing_columns_is_rejected():
    with pytest.raises(ScenarioError):
        stops_from_csv("id,nome\n1,x\n")


def test_validation_flags_impossible_stop(small_scenario):
    data = scenario_to_file_dict(small_scenario)
    data["paradas"][0]["demanda_kg"] = 999  # maior que qualquer veículo
    with pytest.raises(ScenarioError, match="nenhum veículo comporta"):
        scenario_from_dict(data)
