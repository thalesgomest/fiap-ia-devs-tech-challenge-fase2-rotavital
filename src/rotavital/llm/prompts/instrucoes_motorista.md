Gere a FOLHA DE ROTA do motorista do veículo $veiculo a partir dos dados abaixo.

DADOS DA ROTA (JSON):
$dados

FORMATO OBRIGATÓRIO (Markdown):
# Folha de rota - <veículo>
**Saída:** <horário> · **Retorno previsto:** <horário> · **Distância:** <km> km · **Carga total:** <kg> kg

## Antes de sair
- Lista curta de verificações (temperatura do baú se houver carga refrigerada, conferência das cargas na ordem de entrega, documentos).

## Sequência de entregas
Uma linha numerada por parada, NA MESMA ORDEM dos dados, usando o nome exato da parada:
N. **<nome>** - chegada <chegada> · janela <janela> · prazo <prazo> · entregar <demanda_kg> kg de <carga>. Acrescente "⚠️ PRIORIDADE CRÍTICA" quando prioridade = critica, "❄️ manter refrigerado" quando refrigerado = true, e "aguardar abertura (<espera_min> min)" quando espera_min > 0.

## Atenção
- Paradas com atraso_min > 0 ou folga_min < 15 e o que fazer (avisar a central, priorizar).
- Em caso de imprevisto: contatar a central antes de alterar a ordem das entregas críticas.

EXEMPLO DE LINHA (apenas formato, não use estes dados):
3. **Hospital Exemplo** - chegada 08:12 · janela 07:00-18:00 · prazo 09:00 · entregar 12.5 kg de Hemocomponentes. ⚠️ PRIORIDADE CRÍTICA ❄️ manter refrigerado

Responda apenas com a folha de rota.
