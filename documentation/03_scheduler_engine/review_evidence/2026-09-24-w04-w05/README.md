# Evidência da revisão W04/W05

Estas experiências observam o código anterior às correções propostas. Não são uma nova suite de aceitação: exit 0 de `probes.py` significa que as experiências terminaram, mesmo quando o resultado observado é defeituoso.

- `probes.py`: entradas explícitas, resultados do gerador, comparação com enumeração nos casos pequenos e uma experiência de certificação com estado FEASIBLE injetado.
- `probes.json`: saída integral; horários, violações e evidência estão incluídos.
- `campaign_report.json`: cópia da campanha de 26 casos reexecutada nesta revisão.
- `source_manifest.json`: identidade de código e hashes de 88 ficheiros de fonte/evidência. Não inclui segredos de configuração.

Runtime observado: Python 3.14.7; OR-Tools 9.15.6755; imagem `cronos-backend-test:local`. Ver ID da imagem no manifesto.

Comando PowerShell, a partir da raiz do repositório, com a imagem local de testes já construída:

```powershell
docker run --rm --network none --mount "type=bind,source=C:\Users\Hp\Desktop\AnoLetivo25_26\MeuProjeto,target=/workspace,readonly" -w /workspace/backend -e PYTHONPATH=/workspace/backend cronos-backend-test:local python /workspace/documentation/03_scheduler_engine/review_evidence/2026-09-24-w04-w05/probes.py
```

Não sobrescrever a evidência histórica depois de corrigir o motor. Guardar uma nova execução noutro diretório e comparar outcomes, vetores e relatórios. A imagem/runtime e as fontes devem ser registados novamente se forem diferentes.

Suite existente reexecutada:

```powershell
node scripts/test.mjs fast --scope backend
node scripts/test.mjs campaign --manifest backend/tests/scheduler_lab/generation_manifest.json --mode generator --time-limit 30
```

O limite de 30 segundos é o parâmetro desta campanha experimental, não uma proposta de limite de produto ou p95. Os testes de integração/contratos do implementador não foram reexecutados nesta revisão.
