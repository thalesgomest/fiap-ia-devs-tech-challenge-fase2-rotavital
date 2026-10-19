import json

import pytest

from rotavital.llm import assistant, reports
from rotavital.llm.evaluation import coverage, numeric_faithfulness
from rotavital.llm.prompts import PROMPTS_DIR, render
from rotavital.llm.providers.base import ChatResult, LLMError, LLMProvider, ToolCall, ToolSpec, run_tool
from rotavital.llm.providers.offline import OfflineProvider
from rotavital.llm.providers.ollama import OllamaProvider
from rotavital.llm.providers.openai_compat import OpenAICompatibleProvider
from rotavital.llm.tools import RunTools, find_route
from rotavital.optimization.baselines import run_baselines
from rotavital.optimization.evaluator import RouteEvaluator
from rotavital.services import scenario_summary


@pytest.fixture
def run(small_scenario):
    ev = RouteEvaluator(small_scenario)
    baselines = [{k: v for k, v in b.items() if k != "_routes"} for b in run_baselines(ev)]
    sol = ev.solution_from_tour(ev.nodes)
    best = min(baselines, key=lambda b: b["custo_total"])
    return {
        "id": "run-teste",
        "criado_em": "2026-10-13T10:00:00",
        "cenario": scenario_summary(small_scenario),
        "ga": {"config": {}, "geracoes": 10, "motivo_parada": "estagnacao", "tempo_s": 1.2, "avaliacoes": 99, "historico": []},
        "solucao": sol,
        "baselines": baselines,
        "comparativo": {"melhor_baseline": best["nome"], "custo_baseline": best["custo_total"],
                        "economia_rs": round(best["custo_total"] - sol["custo_total"], 2), "economia_pct": 1.0},
    }


class FakeProvider(LLMProvider):
    name, model = "fake", "fake-1"

    def __init__(self, text="", fail=False):
        self.text, self.fail, self.prompts = text, fail, []

    def complete(self, system, prompt, max_tokens=3000):
        if self.fail:
            raise LLMError("sem conexão")
        self.prompts.append(prompt)
        return self.text

    def chat(self, system, messages, tools, max_steps=6):
        tool_map = {t.name: t for t in tools}
        args, result = run_tool(tool_map, "listar_rotas", {})
        return ChatResult("Há rotas planejadas.", [ToolCall("listar_rotas", args, result)])

    def health(self):
        return True, "ok"


# ---------------------------------------------------------------- avaliação
def test_faithfulness_flags_invented_numbers():
    facts = {"distancia_km": 42.3, "chegada": "08:15", "taxa": 0.95}
    good = numeric_faithfulness("Chegada 08:15, 42.3 km, 95% no prazo.", facts)
    bad = numeric_faithfulness("Chegada 09:40, 77 km.", facts)
    assert good["score"] == 1.0
    assert bad["score"] == 0.0 and "09:40" in bad["nao_suportados"]


def test_faithfulness_understands_brazilian_number_format():
    assert numeric_faithfulness("Custo de R$ 1.234,50", {"custo": 1234.5})["score"] == 1.0


def test_coverage_checks_presence_and_order():
    names = ["Hospital A", "UBS B", "Lab C"]
    assert coverage("1. Hospital A 2. UBS B 3. Lab C", names) == {"score": 1.0, "ordem_correta": 1.0, "faltando": []}
    out_of_order = coverage("Lab C, depois Hospital A", names)
    assert out_of_order["faltando"] == ["UBS B"] and out_of_order["ordem_correta"] == 0.0


# ------------------------------------------------------------------ prompts
def test_prompts_have_no_unfilled_placeholders():
    for path in PROMPTS_DIR.glob("*.md"):
        text = render(path.stem, veiculo="V", dados="{}", cenario="C", periodo="P", run_id="R",
                      veiculos="V", tipo="T", texto="X")
        assert "$" not in text.replace("R$", ""), path.name


# -------------------------------------------------------------- ferramentas
def test_find_route_accepts_variants(run):
    label = run["solucao"]["rotas"][0]["veiculo"]  # ex.: "REF #1"
    assert find_route(run, label.lower().replace(" #", "#"))["veiculo"] == label
    assert find_route(run, "1")["veiculo"] == label
    with pytest.raises(KeyError):
        find_route(run, "XYZ #9")


def test_delay_simulation_never_reduces_lateness(run):
    tools = RunTools(run)
    label = run["solucao"]["rotas"][0]["veiculo"]
    sim = tools.simular_atraso(label, 600)
    for item in sim["impacto_por_parada"]:
        assert item["novo_atraso_min"] >= item["atraso_original_min"]
    assert sim["paradas_que_passam_a_atrasar"]


def test_run_tool_reports_errors_instead_of_raising():
    spec = ToolSpec("x", "", {}, lambda veiculo: 1 / 0)
    _, result = run_tool({"x": spec}, "x", '{"veiculo": "a"}')
    assert "erro" in json.loads(result)
    _, missing = run_tool({}, "nao_existe", {})
    assert "erro" in json.loads(missing)


# ---------------------------------------------------------------- relatórios
def test_driver_instructions_offline_are_complete(run):
    label = run["solucao"]["rotas"][0]["veiculo"]
    out = reports.driver_instructions(run, label, OfflineProvider())
    assert out["provedor"] == "offline"
    assert out["avaliacao"]["cobertura"]["score"] == 1.0
    assert out["avaliacao"]["fidelidade_numerica"]["score"] == 1.0


def test_llm_text_is_used_and_prompt_contains_route_data(run):
    label = run["solucao"]["rotas"][0]["veiculo"]
    fake = FakeProvider("# Folha de rota\nTexto da LLM")
    out = reports.driver_instructions(run, label, fake)
    assert out["markdown"].startswith("# Folha de rota") and out["provedor"] == "fake"
    first_stop = run["solucao"]["rotas"][0]["paradas"][0]["nome"]
    assert first_stop in fake.prompts[0]


def test_llm_failure_falls_back_to_template(run):
    out = reports.execution_report(run, FakeProvider(fail=True))
    assert out["provedor"] == "offline" and "contingência" in out["markdown"]
    assert out["erro_llm"] == "sem conexão"


# ---------------------------------------------------------------- assistente
@pytest.mark.parametrize(
    "question, tool",
    [
        ("Quais entregas estão em risco?", "entregas_em_risco"),
        ("Detalhe a rota do REF #1", "detalhar_rota"),
        ("Quanto economizamos vs Clarke-Wright?", "comparar_abordagens"),
        ("Onde fica a Parada 3?", "buscar_parada"),
    ],
)
def test_offline_assistant_routes_intents(run, question, tool):
    out = assistant.answer(run, [{"papel": "usuario", "conteudo": question}], OfflineProvider())
    assert out["ferramentas"][0]["nome"] == tool
    assert out["resposta"]


def test_assistant_with_llm_returns_tool_trace(run):
    out = assistant.answer(run, [{"papel": "usuario", "conteudo": "Quais rotas?"}], FakeProvider())
    assert out["resposta"] == "Há rotas planejadas."
    assert out["ferramentas"][0]["nome"] == "listar_rotas"


# ----------------------------------------------------- adaptadores (HTTP mock)
class _Resp:
    def __init__(self, payload, status=200):
        self._payload, self.status_code, self.text = payload, status, json.dumps(payload)

    def json(self):
        return self._payload


def test_ollama_tool_loop(monkeypatch, run):
    replies = iter([
        {"message": {"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": "resumo_execucao", "arguments": {}}}]}},
        {"message": {"role": "assistant", "content": "Custo calculado."}},
    ])
    sent = []

    def fake_post(self, url, json=None, timeout=None):
        sent.append(json)
        return _Resp(next(replies))

    monkeypatch.setattr("rotavital.llm.providers.ollama.requests.Session.post", fake_post)
    tools = [ToolSpec("resumo_execucao", "", {"type": "object", "properties": {}}, RunTools(run).resumo_execucao)]
    result = OllamaProvider("http://x", "llama3.1:8b").chat("sys", [{"role": "user", "content": "custo?"}], tools)
    assert result.text == "Custo calculado."
    assert result.tool_calls[0].name == "resumo_execucao"
    assert sent[1]["messages"][-1]["role"] == "tool"


def test_openai_compatible_tool_loop(monkeypatch, run):
    replies = iter([
        {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "listar_rotas", "arguments": "{}"}}]}}]},
        {"choices": [{"message": {"role": "assistant", "content": "Duas rotas."}}]},
    ])
    sent = []

    def fake_post(url, json=None, headers=None, timeout=None):
        sent.append(json)
        return _Resp(next(replies))

    monkeypatch.setattr("rotavital.llm.providers.openai_compat.requests.post", fake_post)
    tools = [ToolSpec("listar_rotas", "", {"type": "object", "properties": {}}, RunTools(run).listar_rotas)]
    result = OpenAICompatibleProvider("http://x", "k", "m").chat("sys", [{"role": "user", "content": "?"}], tools)
    assert result.text == "Duas rotas."
    assert sent[1]["messages"][-1] == {"role": "tool", "tool_call_id": "c1", "content": result.tool_calls[0].result}

def test_qwen_options_disable_thinking_and_preserve_reproducible_settings(monkeypatch):
    from rotavital.config import settings

    monkeypatch.setattr(settings, "ollama_think", False)
    monkeypatch.setattr(settings, "ollama_seed", 2026)
    monkeypatch.setattr(settings, "ollama_num_predict", 512)
    monkeypatch.setattr(settings, "ollama_context", 8192)
    monkeypatch.setattr(settings, "llm_temperature", 0)
    sent = []

    def fake_post(self, url, json=None, timeout=None):
        sent.append(json)
        return _Resp({"message": {"content": "Resposta local baseada nas ferramentas."}})

    monkeypatch.setattr("requests.Session.post", fake_post)
    provider = OllamaProvider("http://127.0.0.1:11434", "qwen3:4b")
    assert provider.session.trust_env is False
    assert provider.chat("sistema", [{"role": "user", "content": "Olá"}], []).text
    assert sent[0]["think"] is False and sent[0]["keep_alive"] == "10m"
    assert sent[0]["options"] == {"temperature": 0, "num_ctx": 8192, "seed": 2026, "num_predict": 512}
    assert provider.complete("sistema", "pergunta", max_tokens=120)
    assert sent[-1]["options"]["num_predict"] == 120


@pytest.mark.parametrize("payload", [{}, [], {"message": None}, {"message": {"content": ""}}])
def test_ollama_rejects_missing_or_empty_messages(monkeypatch, payload):
    monkeypatch.setattr("requests.Session.post", lambda *args, **kwargs: _Resp(payload))
    with pytest.raises(LLMError):
        OllamaProvider().chat("sistema", [{"role": "user", "content": "pergunta"}], [])


def test_ollama_reports_backend_errors_and_unsupported_tools(monkeypatch):
    from rotavital.llm.providers.base import ToolsUnsupported

    monkeypatch.setattr("requests.Session.post", lambda *args, **kwargs: _Resp({"error": "modelo indisponível"}, 500))
    with pytest.raises(LLMError, match="HTTP 500"):
        OllamaProvider().complete("sistema", "pergunta")
    response = _Resp({}, 400)
    response.text = "model does not support tools"
    monkeypatch.setattr("requests.Session.post", lambda *args, **kwargs: response)
    with pytest.raises(ToolsUnsupported):
        OllamaProvider().chat("sistema", [], [])


def test_ollama_health_records_model_digest_without_proxy(monkeypatch):
    response = _Resp({"models": [{"name": "qwen3:4b", "digest": "digest-testado"}]})
    response.raise_for_status = lambda: None
    monkeypatch.setattr("requests.Session.get", lambda *args, **kwargs: response)
    provider = OllamaProvider("http://127.0.0.1:11434", "qwen3:4b")
    assert provider.health() == (True, "ok")
    assert provider.model_digest == "digest-testado"


@pytest.mark.parametrize("fallback", [True, False])
@pytest.mark.parametrize("unsupported_tools", [True, False])
def test_chat_honors_offline_fallback_also_when_context_call_fails(run, monkeypatch, fallback, unsupported_tools):
    from rotavital.config import settings
    from rotavital.llm.providers.base import ToolsUnsupported

    class BrokenProvider(FakeProvider):
        def chat(self, *args, **kwargs):
            if unsupported_tools:
                raise ToolsUnsupported("sem ferramentas")
            raise LLMError("falha local")

    monkeypatch.setattr(settings, "llm_fallback_offline", fallback)
    provider = BrokenProvider(fail=True)
    messages = [{"papel": "usuario", "conteudo": "Quais rotas?"}]
    if fallback:
        result = assistant.answer(run, messages, provider)
        assert result["provedor"] == "offline" and result["erro_llm"]
    else:
        with pytest.raises(LLMError):
            assistant.answer(run, messages, provider)



def test_risk_priority_is_filtered_by_python_before_the_llm_sees_the_result(run):
    import copy

    data = copy.deepcopy(run)
    stops = [stop for route in data["solucao"]["rotas"] for stop in route["paradas"]]
    for stop in stops:
        stop["atraso_min"], stop["folga_min"] = 0, 60
    stops[0]["prioridade"], stops[0]["folga_min"] = "alta", 5
    impl = RunTools(data)
    assert impl.entregas_em_risco()[0]["prioridade"] == "alta"
    result = impl.entregas_em_risco(prioridade="critica")
    assert result[0]["quantidade"] == 0 and result[0]["prioridade_filtrada"] == "critica"
    text, calls = assistant.offline_answer(data, "Quais entregas críticas estão em risco?")
    assert "Nenhuma entrega de prioridade crítica" in text
    assert json.loads(calls[0].result)[0]["quantidade"] == 0


def test_model_cannot_change_an_explicit_risk_priority_scope(run):
    from rotavital.llm.tools import build_tools, requested_priority

    assert requested_priority("Quais entregas críticas estão em risco?") == "critica"
    assert requested_priority("Compare entregas críticas e de prioridade alta") is None
    tools = {tool.name: tool for tool in build_tools(run, risk_priority="critica")}
    _, rejected = run_tool(tools, "entregas_em_risco", {"prioridade": "alta"})
    assert "erro" in json.loads(rejected)
    _, accepted = run_tool(tools, "entregas_em_risco", {})
    assert all(item.get("prioridade") == "critica" or item.get("quantidade") == 0 for item in json.loads(accepted))
