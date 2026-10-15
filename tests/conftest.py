import os
import sys
import tempfile
from pathlib import Path

# Ambiente isolado: sem LLM real e banco temporário (definido antes de importar o app)
os.environ["LLM_PROVIDER"] = "offline"
os.environ["ROTAVITAL_DB"] = str(Path(tempfile.mkdtemp()) / "test.db")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest  # noqa: E402

from rotavital.domain.models import Depot, Scenario, Stop, VehicleType  # noqa: E402


def make_stop(i, lat, lon, kg=10.0, priority="rotina", refrig=False, window=(420, 1080), service=10):
    return Stop(
        id=f"S{i}", name=f"Parada {i}", kind="ubs", lat=lat, lon=lon, demand_kg=kg,
        priority=priority, refrigerated=refrig, window_start=window[0], window_end=window[1],
        service_min=service, cargo="Teste",
    )


@pytest.fixture
def small_scenario():
    """Seis paradas ao redor do depósito, duas refrigeradas e uma crítica."""
    stops = [
        make_stop(1, -23.55, -46.60, kg=20, priority="critica", refrig=True),
        make_stop(2, -23.50, -46.63, kg=30),
        make_stop(3, -23.58, -46.70, kg=15, refrig=True),
        make_stop(4, -23.62, -46.65, kg=40),
        make_stop(5, -23.53, -46.72, kg=25, priority="alta"),
        make_stop(6, -23.60, -46.58, kg=35),
    ]
    fleet = [
        VehicleType("REF", "Van refrigerada", 1, 60, 200, 30, True, 150, 1.8, 600, 0.25),
        VehicleType("SECO", "Utilitário", 2, 120, 250, 30, False, 100, 1.2, 600, 0.22),
    ]
    return Scenario(
        id="teste", name="Cenário de teste", description="",
        depot=Depot("CD", -23.557, -46.669), stops=stops, fleet=fleet,
    )
