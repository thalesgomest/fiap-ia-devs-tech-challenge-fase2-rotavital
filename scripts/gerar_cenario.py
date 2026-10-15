"""Gera cenários sintéticos reprodutíveis em ``scenarios/``.

Uso:
    python scripts/gerar_cenario.py                    # recria os cenários padrão
    python scripts/gerar_cenario.py --id meu-caso --paradas 30 --semente 42

As localizações usam coordenadas aproximadas de distritos da cidade de São Paulo; os
nomes das unidades e as demandas são fictícios (dados sintéticos para fins acadêmicos).
Para outro caso/cidade, troque a lista ``DISTRITOS`` ou importe um CSV pela interface.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DEPOSITO = {"nome": "Hemocentro Central (CD)", "lat": -23.5571, "lon": -46.6690}

DISTRITOS = [
    ("Santana", -23.5025, -46.6253), ("Tucuruvi", -23.4800, -46.6030),
    ("Vila Maria", -23.5130, -46.5800), ("Penha", -23.5290, -46.5450),
    ("Tatuapé", -23.5400, -46.5760), ("Mooca", -23.5590, -46.5990),
    ("Ipiranga", -23.5890, -46.6060), ("Vila Mariana", -23.5890, -46.6340),
    ("Saúde", -23.6180, -46.6390), ("Jabaquara", -23.6460, -46.6410),
    ("Santo Amaro", -23.6540, -46.7100), ("Campo Limpo", -23.6450, -46.7600),
    ("Morumbi", -23.5990, -46.7200), ("Butantã", -23.5710, -46.7080),
    ("Pinheiros", -23.5660, -46.6920), ("Lapa", -23.5230, -46.7040),
    ("Pirituba", -23.4870, -46.7260), ("Freguesia do Ó", -23.4990, -46.6960),
    ("Casa Verde", -23.5060, -46.6600), ("Brasilândia", -23.4630, -46.6850),
    ("Perus", -23.4040, -46.7550), ("Itaquera", -23.5400, -46.4560),
    ("Guaianases", -23.5440, -46.4140), ("São Mateus", -23.6070, -46.4770),
    ("Sapopemba", -23.6060, -46.5100), ("Vila Prudente", -23.5830, -46.5830),
    ("Aricanduva", -23.5780, -46.5110), ("Ermelino Matarazzo", -23.4970, -46.4770),
    ("São Miguel Paulista", -23.4980, -46.4440), ("Itaim Paulista", -23.5010, -46.3990),
    ("Cidade Ademar", -23.6680, -46.6560), ("Grajaú", -23.7650, -46.6970),
    ("Parelheiros", -23.8270, -46.7280), ("Capão Redondo", -23.6700, -46.7790),
    ("Jardim Ângela", -23.7000, -46.7700), ("Interlagos", -23.6830, -46.6950),
    ("Bela Vista", -23.5610, -46.6470), ("Liberdade", -23.5590, -46.6340),
    ("Brás", -23.5440, -46.6160), ("Barra Funda", -23.5260, -46.6650),
    ("Cidade Tiradentes", -23.5820, -46.4060), ("Vila Andrade", -23.6280, -46.7330),
    ("Jaçanã", -23.4630, -46.5810), ("Cangaíba", -23.5040, -46.5250),
]

# tipo: (rótulo, carga, refrigerado, prioridades possíveis, faixa kg, janela, serviço)
PERFIS = {
    "hospital": ("Hospital", "Hemocomponentes", True, ["critica", "critica", "alta"], (6, 22), ("07:00", "18:00"), 12),
    "ubs": ("UBS", "Vacinas", True, ["alta", "rotina"], (10, 35), ("08:00", "17:00"), 10),
    "laboratorio": ("Laboratório", "Reagentes", True, ["rotina", "alta"], (4, 14), ("08:00", "16:00"), 8),
    "domiciliar": ("Paciente domiciliar", "Medicamentos home care", False, ["alta", "rotina"], (3, 12), None, 15),
    "ama": ("AMA/UPA", "Insumos hospitalares", False, ["rotina", "rotina", "alta"], (40, 120), ("07:30", "17:30"), 15),
}

FROTA_PADRAO = [
    {"codigo": "VAN-REF", "nome": "Van refrigerada", "quantidade": 2, "capacidade_kg": 350,
     "autonomia_km": 220, "velocidade_kmh": 26, "refrigerado": True, "custo_fixo": 180,
     "custo_km": 1.9, "jornada_max_min": 600, "co2_kg_km": 0.26},
    {"codigo": "UTIL", "nome": "Utilitário de carga seca", "quantidade": 2, "capacidade_kg": 700,
     "autonomia_km": 300, "velocidade_kmh": 24, "refrigerado": False, "custo_fixo": 140,
     "custo_km": 1.5, "jornada_max_min": 600, "co2_kg_km": 0.24},
    {"codigo": "MOTO", "nome": "Moto com baú térmico", "quantidade": 3, "capacidade_kg": 30,
     "autonomia_km": 140, "velocidade_kmh": 34, "refrigerado": True, "custo_fixo": 70,
     "custo_km": 0.45, "jornada_max_min": 480, "co2_kg_km": 0.06},
]

PRIORIDADES = {
    "critica": {"rotulo": "Crítica", "sla_min": 120, "multa_min": 40.0, "ordem": 0},
    "alta": {"rotulo": "Alta", "sla_min": 240, "multa_min": 10.0, "ordem": 1},
    "rotina": {"rotulo": "Rotina", "sla_min": None, "multa_min": 1.5, "ordem": 2},
}


def _hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def gerar(cid: str, nome: str, descricao: str, n: int, mix: dict, semente: int, frota=None) -> dict:
    rng = random.Random(semente)
    distritos = rng.sample(DISTRITOS, k=min(n, len(DISTRITOS)))
    while len(distritos) < n:  # mais paradas que distritos: reaproveita com deslocamento
        d = rng.choice(DISTRITOS)
        distritos.append((d[0], d[1] + rng.uniform(-0.01, 0.01), d[2] + rng.uniform(-0.01, 0.01)))
    tipos = [t for t, q in mix.items() for _ in range(q)]
    rng.shuffle(tipos)
    paradas = []
    for i, ((bairro, lat, lon), tipo) in enumerate(zip(distritos, tipos, strict=True), start=1):
        rotulo, carga, refrig, prios, (kmin, kmax), janela, servico = PERFIS[tipo]
        if janela is None:  # domiciliar: janela de 2 h combinada com a família
            inicio = rng.choice(range(8 * 60, 15 * 60 + 1, 30))
            janela = (_hhmm(inicio), _hhmm(inicio + 120))
        paradas.append(
            {
                "id": f"P{i:02d}",
                "nome": f"{rotulo} {bairro}",
                "tipo": tipo,
                "lat": round(lat + rng.uniform(-0.004, 0.004), 5),
                "lon": round(lon + rng.uniform(-0.004, 0.004), 5),
                "demanda_kg": round(rng.uniform(kmin, kmax), 1),
                "prioridade": rng.choice(prios),
                "refrigerado": refrig,
                "janela_inicio": janela[0],
                "janela_fim": janela[1],
                "tempo_servico_min": servico,
                "carga": carga,
            }
        )
    return {
        "id": cid,
        "nome": nome,
        "descricao": descricao,
        "inicio_turno": "07:00",
        "fator_sinuosidade": 1.35,
        "multa_veiculo_excedente": 2500,
        "deposito": DEPOSITO,
        "prioridades": PRIORIDADES,
        "frota": frota or FROTA_PADRAO,
        "paradas": paradas,
    }


def salvar(cenario: dict) -> Path:
    path = ROOT / "scenarios" / f"{cenario['id']}.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(cenario, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def padrao() -> None:
    salvar(gerar(
        "sp-hemorrede-40",
        "Hemorrede SP - 40 pontos",
        "Distribuição diária de hemocomponentes, vacinas, reagentes e insumos a partir do "
        "Hemocentro Central para hospitais, UBS, laboratórios, AMAs e pacientes de home care.",
        40, {"hospital": 9, "ubs": 11, "laboratorio": 5, "domiciliar": 9, "ama": 6}, 2026,
        frota=[dict(FROTA_PADRAO[0], quantidade=3), dict(FROTA_PADRAO[1], quantidade=2),
               dict(FROTA_PADRAO[2], quantidade=4)],
    ))
    salvar(gerar(
        "sp-homecare-18",
        "Home care Zona Sul/Oeste - 18 pontos",
        "Operação menor focada em atendimento domiciliar com janelas curtas e algumas "
        "urgências hospitalares.",
        18, {"hospital": 3, "ubs": 3, "domiciliar": 10, "ama": 2}, 7,
        frota=[dict(FROTA_PADRAO[0], quantidade=1), dict(FROTA_PADRAO[1], quantidade=1),
               dict(FROTA_PADRAO[2], quantidade=2)],
    ))
    salvar(gerar(
        "sp-mini-8",
        "Demonstração rápida - 8 pontos",
        "Cenário mínimo para testes e demonstração ao vivo.",
        8, {"hospital": 2, "ubs": 2, "domiciliar": 3, "ama": 1}, 3,
    ))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--id")
    parser.add_argument("--nome", default="Cenário sintético")
    parser.add_argument("--paradas", type=int, default=30)
    parser.add_argument("--semente", type=int, default=1)
    args = parser.parse_args()
    if args.id:
        n = args.paradas
        mix = {"hospital": n // 5, "ubs": n // 4, "laboratorio": n // 10, "ama": n // 8}
        mix["domiciliar"] = n - sum(mix.values())
        print(salvar(gerar(args.id, args.nome, "Cenário gerado automaticamente.", n, mix, args.semente)))
    else:
        padrao()
        print("Cenários padrão gerados em scenarios/")
