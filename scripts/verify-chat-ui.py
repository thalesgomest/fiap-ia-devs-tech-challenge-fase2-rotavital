"""Teste real do chat no Edge instalado; requer pip install playwright e app ativo.

Uso: python scripts/verify-chat-ui.py --run-id ID
Não baixa navegador nem usa o perfil pessoal do usuário. Salva captura e resposta.
"""
import argparse
import json
from pathlib import Path
from uuid import uuid4

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--base-url', default='http://127.0.0.1:8000')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = root / 'data/evidencias' / ('chat-ui-' + uuid4().hex[:8])
    output.mkdir(parents=True)
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel='msedge', headless=True, timeout=25000)
        page = browser.new_page(viewport={'width': 1440, 'height': 1000}, device_scale_factor=1)
        page.on('pageerror', lambda error: errors.append(str(error)))
        # Esta verificação é do chat; não solicitar tiles OSM por navegação automatizada.
        page.route('**/*tile.openstreetmap.org/**', lambda route: route.abort())
        page.add_init_script("localStorage.setItem('rotavital.execucao', " + json.dumps(args.run_id) + ");")
        page.goto(args.base_url.rstrip('/') + '/#assistente', wait_until='domcontentloaded', timeout=60000)
        page.locator('#chat-input').wait_for(state='visible', timeout=60000)
        page.wait_for_function("!document.querySelector('#chat-input').disabled", timeout=60000)
        expect(page.locator('#llm-chip')).to_contain_text('qwen3:4b', timeout=15000)
        print('Interface carregada; enviando pergunta real pelo formulário...', flush=True)
        page.locator('#chat-input').fill('Quais entregas críticas estão em risco?')
        with page.expect_response(lambda response: response.url.endswith('/chat')
                                  and response.request.method == 'POST', timeout=900000) as response_info:
            page.locator('#chat-send').click()
        response = response_info.value
        data = response.json()
        (output / 'response.json').write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        assert response.status == 200, data
        assert data['provedor'] == 'ollama' and data['modelo'] == 'qwen3:4b', data
        page.locator('.msg-assistant .msg-meta').wait_for(state='visible', timeout=10000)
        page.screenshot(path=str(output / 'chat.png'), full_page=True)
        (output / 'browser.json').write_text(json.dumps({'page_errors': errors, 'url': page.url,
            'model_chip': page.locator('#llm-chip').inner_text()}, ensure_ascii=False, indent=2), encoding='utf-8')
        assert not errors, errors
        browser.close()
    print('Resposta:', data['resposta'], flush=True)
    print('Evidências:', output, flush=True)


if __name__ == '__main__':
    main()
