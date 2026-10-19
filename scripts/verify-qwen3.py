"""Verificação real do chat pela API. Requer app e Ollama iniciados.

python scripts/verify-qwen3.py --base-url http://127.0.0.1:8000
Não usa provedor falso nem aceita contingência como integração real.
"""
import argparse
import json
import time
from pathlib import Path
from uuid import uuid4

import requests


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:8000')
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output_dir or root / 'data/evidencias' / ('qwen3-' + uuid4().hex[:8])
    output.mkdir(parents=True, exist_ok=False)
    client = requests.Session()
    client.trust_env = False
    base = args.base_url.rstrip('/')

    def request(method, endpoint, **kwargs):
        response = client.request(method, base + endpoint, timeout=1000, **kwargs)
        response.raise_for_status()
        return response.json()

    def save(name, data):
        (output / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    status = request('GET', '/api/status')
    save('status.json', status)
    assert status['llm']['modo'] == 'llm' and status['llm']['modelo'] == 'qwen3:4b', status
    manifest_path = root / '.runtime/ollama/imported-model-manifest.json'
    if manifest_path.exists():
        expected = json.loads(manifest_path.read_text(encoding='utf-8-sig'))['model_digest']
        assert status['llm']['model_digest'] == expected, 'Digest diferente do Qwen3 testado.'
    started = request('POST', '/api/execucoes', json={
        'cenario_id': 'sp-mini-8', 'preset': 'rapido',
        'config': {'population_size': 20, 'generations': 10, 'seed': 2026},
    })
    run_id = started['id']
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        progress = request('GET', f'/api/execucoes/{run_id}/progresso')
        if progress['status'] == 'concluido':
            break
        if progress['status'] == 'erro':
            raise RuntimeError(progress)
        time.sleep(0.2)
    else:
        raise TimeoutError('A otimização não terminou para o teste.')
    run = request('GET', f'/api/execucoes/{run_id}')
    save('run.json', run)
    vehicle = run['solucao']['rotas'][0]['veiculo']
    cases = [
        ('riscos', 'Quais entregas críticas estão em risco?', {'entregas_em_risco'}),
        ('veiculo', f'Qual é a distância e o horário de retorno da rota da {vehicle}?',
         {'detalhar_rota', 'listar_rotas'}),
        ('indisponivel', 'Qual é o trânsito em tempo real durante esta operação?', set()),
    ]
    messages, results = [], []
    for case_id, question, expected_tools in cases:
        print(f'Consultando Qwen3: {case_id} — {question}', flush=True)
        messages.append({'papel': 'usuario', 'conteudo': question})
        began = time.perf_counter()
        reply = request('POST', f'/api/execucoes/{run_id}/chat', json={'mensagens': messages})
        elapsed = time.perf_counter() - began
        save(case_id + '.json', {'question': question, 'response': reply, 'elapsed_seconds': elapsed})
        assert reply['provedor'] == 'ollama' and reply['modelo'] == 'qwen3:4b', reply
        assert reply['resposta'].strip(), reply
        selected = {tool['nome'] for tool in reply['ferramentas']}
        results.append({'case': case_id, 'elapsed_seconds': elapsed, 'tools': sorted(selected),
                        'reference_tool_check': bool(selected & expected_tools) if expected_tools else None,
                        'response': reply['resposta']})
        save('summary.json', {'run_id': run_id, 'model': status['llm'], 'cases': results,
                              'manual_review_required': True})
        messages.append({'papel': 'assistente', 'conteudo': reply['resposta'][:4000]})
        print(f"Recebido: {reply['provedor']} / {reply['modelo']} em {elapsed:.1f}s; ferramentas: {selected}", flush=True)
    print(f'Evidências: {output}', flush=True)


if __name__ == '__main__':
    main()
