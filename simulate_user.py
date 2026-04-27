"""
Simulacao completa de comportamento admin no Horario Zen (Solver V2).
Fluxo:
  1. Login admin
  2. Gerar horario completo (full, Solver V2)
  3. Aguardar conclusao e obter data de fim original
  4. Criar 5 ocorrencias marcadas como GAP (furo)
  5. Criar 5 ocorrencias marcadas como SUBSTITUTED (substituicao valida)
  6. Criar 5 ocorrencias marcadas como GIVEN (aula dada)
  7. Gerar horario de reparacao (repair, Solver V2)
  8. Aprovar o rascunho de reparacao
  9. Comparar data de fim: original vs reparado

Requisitos: docker compose up && seed small-realistic
"""
import time
import sys
import requests
from datetime import date, timedelta
from collections import defaultdict

BASE = "http://localhost:8000/api/v1"
ADMIN_EMAIL = "ana.silva@escola.pt"
ADMIN_PASSWORD = "1234"

sess = requests.Session()

def step(msg):
    print(f"\n{'='*60}")
    print(f"  {msg}")
    print('='*60)

def ok(msg):
    print(f"  [OK] {msg}")

def info(msg):
    print(f"  [->] {msg}")

def err(msg, resp=None):
    print(f"  [!!] {msg}")
    if resp is not None:
        try:
            print(f"       Status: {resp.status_code}")
            print(f"       Body:   {resp.text[:500]}")
        except Exception:
            pass

# ---------------------------------------------------------------------------
# 1. LOGIN
# ---------------------------------------------------------------------------
step("1 -- Login como Admin")
r = sess.post(f"{BASE}/auth/token", data={"username": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
if r.status_code != 200:
    err("Login falhou", r); sys.exit(1)
token = r.json()["access_token"]
sess.headers.update({"Authorization": f"Bearer {token}"})
ok(f"Token obtido (20 chars): {token[:20]}...")

# ---------------------------------------------------------------------------
# 2. GERAR HORARIO COMPLETO (full, V2)
# ---------------------------------------------------------------------------
step("2 -- Gerar horario completo (modo: full, Solver V2)")
r = sess.post(f"{BASE}/schedule/generate", json={"mode": "full"})
if r.status_code != 200:
    err("Geracao falhou no preflight", r); sys.exit(1)
gen_data = r.json()
task_id = gen_data["task_id"]
solver_version = gen_data.get("solver_version", "?")
ok(f"Task ID: {task_id}")
ok(f"Solver Version: {solver_version}")
if "v2" not in solver_version.lower():
    print(f"\n  [AVISO] Solver version e '{solver_version}', esperado v2!")

# ---------------------------------------------------------------------------
# 3. AGUARDAR CONCLUSAO
# ---------------------------------------------------------------------------
step("3 -- Aguardar conclusao da geracao...")
TERMINAL = {"SUCCESS", "FAILURE", "REVOKED", "CANCELED"}
MAX_WAIT_SECS = 300

def wait_for_task(tid):
    waited = 0
    last_phase = ""
    status_data = {}
    while waited < MAX_WAIT_SECS:
        try:
            r2 = sess.get(f"{BASE}/schedule/status/{tid}", timeout=15)
        except Exception as e:
            info(f"Polling - erro de rede: {type(e).__name__}. A tentar novamente...")
            time.sleep(5)
            waited += 5
            continue
        if r2.status_code != 200:
            info(f"Polling - HTTP {r2.status_code}, a tentar novamente...")
            time.sleep(5)
            waited += 5
            continue
        status_data = r2.json()
        status = status_data.get("status", "")
        phase = status_data.get("phase") or ""
        result_obj = status_data.get("result") or {}
        if isinstance(result_obj, dict):
            phase = phase or result_obj.get("phase", "")
        if phase != last_phase:
            info(f"Fase: {phase or status}")
            last_phase = phase
        bstatus = result_obj.get("status") if isinstance(result_obj, dict) else None
        if status in TERMINAL or bstatus in {"Success", "Error", "Impossible", "Canceled"}:
            break
        time.sleep(5)
        waited += 5
    return status_data

status_data = wait_for_task(task_id)
if status_data is None:
    sys.exit(1)
result = status_data.get("result") or {}
business_status = result.get("status") if isinstance(result, dict) else status_data.get("status")
ok(f"Geracao concluida -- Status: {business_status}")
if business_status not in {"Success", "SUCCESS"}:
    err(f"Geracao terminou com erro: {business_status}")
    sys.exit(1)

# ---------------------------------------------------------------------------
# 4. OBTER DATA DE FIM DO HORARIO ORIGINAL
# ---------------------------------------------------------------------------
step("4 -- Recolher data de fim do horario original")
r = sess.get(f"{BASE}/schedule/audit/generations")
if r.status_code != 200:
    err("Erro ao listar geracoes", r); sys.exit(1)
generations = r.json()
if not generations:
    err("Nenhuma geracao encontrada"); sys.exit(1)

gen_original = generations[0]
original_end_date = gen_original.get("end_date")
original_gen_id = gen_original.get("generation_id")
ok(f"Geracao original: {original_gen_id[:8]}...")
ok(f"Data de fim original: {original_end_date}")

# ---------------------------------------------------------------------------
# 5. OBTER BLOCOS DO HORARIO PARA CRIAR OCORRENCIAS
#    Estrategia: buscar ScheduleOutputs diretamente via audit/summary
# ---------------------------------------------------------------------------
step("5 -- Obter blocos do horario para criar ocorrencias")

# Buscar schedule_outputs via endpoint de audit de forma indireta:
# Listar turmas e buscar weekly slots a partir da data de inicio do seed
r = sess.get(f"{BASE}/classes/")
classes = r.json() if r.status_code == 200 else []
if not classes:
    err("Sem turmas"); sys.exit(1)

# Mapear todas as classes subject links para encontrar substitutos validos
r = sess.get(f"{BASE}/teachers/")
teachers = r.json() if r.status_code == 200 else []

# Para cada turma, encontrar blocos e tentar criar ocorrencias
all_eligible_blocks = []  # (schedule_output_id, class_id, lesson_teacher_id, subject_id)

seed_start = date(2025, 9, 15)
for cls in classes[:3]:  # verificar as 3 primeiras turmas para ter blocos suficientes
    cls_id = cls["id"]
    for week_offset in range(0, 8):
        w_start = seed_start + timedelta(weeks=week_offset)
        w_start = w_start - timedelta(days=w_start.weekday())
        r2 = sess.get(f"{BASE}/schedule/week", params={"week_start": w_start.isoformat(), "class_id": cls_id})
        if r2.status_code == 200:
            slots = r2.json()
            for sl in slots:
                soid = sl.get("schedule_output_id")
                if soid:
                    all_eligible_blocks.append({
                        "schedule_output_id": soid,
                        "class_id": cls_id,
                        "teacher_id": sl.get("teacher", {}).get("id") if sl.get("teacher") else None,
                        "subject_id": sl.get("subject", {}).get("id") if sl.get("subject") else None,
                        "date": sl.get("date"),
                    })
        if len(all_eligible_blocks) >= 50:
            break
    if len(all_eligible_blocks) >= 50:
        break

info(f"Total de blocos encontrados: {len(all_eligible_blocks)}")
if len(all_eligible_blocks) < 15:
    err(f"Apenas {len(all_eligible_blocks)} blocos encontrados. Necessarios 15 minimos.")
    sys.exit(1)

# ---------------------------------------------------------------------------
# 6. CRIAR OCORRENCIAS
#    Para SUBSTITUTED: precisa de professor diferente com ClassSubjectLink valida na turma.
#    Estrategia: para blocos especificos, buscar class_subjects e encontrar professores elegíveis.
# ---------------------------------------------------------------------------
step("6 -- Criar 15 ocorrencias (5 GAP + 5 SUBSTITUTED + 5 GIVEN)")

def create_occurrence(soid):
    """Cria ou reutiliza ocorrencia para um schedule_output_id. Retorna (occ_id, ok)."""
    r2 = sess.post(f"{BASE}/occurrences/", json={"action": "CREATE_OCCURRENCE", "schedule_output_id": soid})
    if r2.status_code in (200, 201):
        return r2.json()["id"], True
    info(f"  Criar occ para bloco {soid} -> HTTP {r2.status_code}: {r2.text[:150]}")
    return None, False

def decide_occurrence(occ_id, status, sub_teacher_id=None, sub_subject_id=None):
    """Decide status da ocorrencia."""
    payload = {"status": status}
    if status == "SUBSTITUTED":
        payload["substitute_teacher_id"] = sub_teacher_id
        payload["substitute_subject_id"] = sub_subject_id
    r2 = sess.patch(f"{BASE}/occurrences/{occ_id}", json=payload)
    if r2.status_code in (200, 201):
        return True
    info(f"  Decidir occ {occ_id} ({status}) -> HTTP {r2.status_code}: {r2.text[:200]}")
    return False

# --- 5 GAPs (simples, sem validacoes complexas)
gap_blocks = all_eligible_blocks[:5]
gap_ok = 0
for blk in gap_blocks:
    occ_id, created = create_occurrence(blk["schedule_output_id"])
    if occ_id and decide_occurrence(occ_id, "GAP"):
        gap_ok += 1
ok(f"GAPs criados: {gap_ok}/5")

# --- 5 GIVEN (simples)
given_blocks = all_eligible_blocks[5:10]
given_ok = 0
for blk in given_blocks:
    occ_id, created = create_occurrence(blk["schedule_output_id"])
    if occ_id and decide_occurrence(occ_id, "GIVEN"):
        given_ok += 1
ok(f"Aulas dadas (GIVEN) criadas: {given_ok}/5")

# --- 5 SUBSTITUTED (precisa de professor diferente com link valida)
# Estrategia: para cada bloco, buscar class_subjects e encontrar outro professor com outra disciplina
sub_blocks = all_eligible_blocks[10:20]  # mais candidatos para ter flexibilidade
sub_ok = 0
for blk in sub_blocks:
    if sub_ok >= 5:
        break
    cls_id = blk["class_id"]
    planned_teacher_id = blk["teacher_id"]
    planned_subject_id = blk["subject_id"]

    # Buscar as disciplinas da turma para encontrar um par valido (outro professor / outra disciplina)
    r2 = sess.get(f"{BASE}/classes/{cls_id}/subjects")
    if r2.status_code != 200:
        continue
    class_subjects_data = r2.json()
    subjects_in_class = class_subjects_data.get("subjects", []) if isinstance(class_subjects_data, dict) else []

    # Encontrar um par: (teacher != planned_teacher, subject != planned_subject) com teacher_id definido
    valid_pair = None
    for subj_info in subjects_in_class:
        s_id = subj_info.get("subject_id")
        t_id = subj_info.get("teacher_id")
        if s_id and t_id and s_id != planned_subject_id and t_id != planned_teacher_id:
            valid_pair = (t_id, s_id)
            break

    if valid_pair is None:
        info(f"  Sem par valido de substituicao para bloco {blk['schedule_output_id']} (turma {cls_id})")
        continue

    sub_teacher_id, sub_subject_id = valid_pair
    occ_id, created = create_occurrence(blk["schedule_output_id"])
    if occ_id and decide_occurrence(occ_id, "SUBSTITUTED", sub_teacher_id=sub_teacher_id, sub_subject_id=sub_subject_id):
        sub_ok += 1
    elif occ_id:
        # Fallback: marcar como GAP se substituicao falhou
        decide_occurrence(occ_id, "GAP")

ok(f"Substituicoes (SUBSTITUTED) criadas: {sub_ok}/5")

if gap_ok + given_ok + sub_ok == 0:
    err("Nenhuma ocorrencia criada. Algo esta errado com os dados.")
    sys.exit(1)

# ---------------------------------------------------------------------------
# 7. GERAR HORARIO DE REPARACAO (repair, V2)
# ---------------------------------------------------------------------------
step("7 -- Gerar horario de reparacao (modo: repair, Solver V2)")
r = sess.post(f"{BASE}/schedule/generate", json={"mode": "repair"})
if r.status_code != 200:
    try:
        detail = r.json()
    except Exception:
        detail = r.text[:300]
    err(f"Geracao repair falhou: {detail}", r); sys.exit(1)

repair_data = r.json()
repair_task_id = repair_data["task_id"]
repair_solver_version = repair_data.get("solver_version", "?")
ok(f"Repair Task ID: {repair_task_id}")
ok(f"Solver Version: {repair_solver_version}")

# ---------------------------------------------------------------------------
# 8. AGUARDAR CONCLUSAO DO REPAIR
# ---------------------------------------------------------------------------
step("8 -- Aguardar conclusao da reparacao...")
status_data = wait_for_task(repair_task_id)
if status_data is None:
    sys.exit(1)
repair_result = status_data.get("result") or {}
repair_business_status = repair_result.get("status") if isinstance(repair_result, dict) else status_data.get("status")
ok(f"Reparacao concluida -- Status: {repair_business_status}")

if repair_business_status not in {"Success", "SUCCESS"}:
    err(f"Reparacao terminou com estado inesperado: {repair_business_status}")
    info(f"Detalhe: {repair_result.get('detail', 'sem detalhe') if isinstance(repair_result, dict) else ''}")
    sys.exit(1)

# ---------------------------------------------------------------------------
# 9. VERIFICAR DRAFT E OBTER DIFF
# ---------------------------------------------------------------------------
step("9 -- Verificar rascunho e diff estatistico")
r = sess.get(f"{BASE}/schedule/drafts")
if r.status_code != 200:
    err("Erro ao listar drafts", r); sys.exit(1)
drafts = r.json()
if not drafts:
    err("Nenhum draft encontrado apos repair"); sys.exit(1)

draft = drafts[0]
draft_gen_id = draft["generation_id"]
draft_count = draft["count"]
ok(f"Draft encontrado: {draft_gen_id[:8]}... ({draft_count} blocos)")

r = sess.get(f"{BASE}/schedule/drafts/{draft_gen_id}/diff")
diff_end_date = None
if r.status_code != 200:
    err("Erro ao obter diff", r)
else:
    diff = r.json()
    stats = diff.get("statistics", {})
    print(f"\n  +--------------------------------------+--------------------+")
    print(f"  | COMPARACAO ESTATISTICA DO RASCUNHO   |                    |")
    print(f"  +--------------------------------------+--------------------+")
    print(f"  | Blocos adicionados                   | {diff.get('added', '?'):>18} |")
    print(f"  | Blocos removidos                     | {diff.get('removed', '?'):>18} |")
    print(f"  | Blocos sem alteracao                 | {diff.get('unchanged', '?'):>18} |")
    if stats:
        delta = stats.get('delta_projected_end_date_days', '?')
        sign = '+' if isinstance(delta, int) and delta > 0 else ''
        print(f"  +--------------------------------------+--------------------+")
        print(f"  | Delta fim das aulas (dias)           | {sign}{str(delta):>18} |")
        print(f"  | Dispersao data de fim (dias)         | {stats.get('end_date_spread_days', '?'):>18} |")
        churn = stats.get('churn_outside_frozen_ratio', 0)
        print(f"  | Churn fora da janela (%)             | {churn*100:>17.1f}% |")
        print(f"  | Total blocos alterados               | {stats.get('total_blocks_changed', '?'):>18} |")
        print(f"  | Backlog por agendar (h)              | {stats.get('backlog_remaining_hours', '?'):>18} |")
        print(f"  | Variacao de furos                    | {stats.get('aggregate_gap_variation', '?'):>18} |")
    print(f"  +--------------------------------------+--------------------+")

    if stats and isinstance(stats.get('delta_projected_end_date_days'), int):
        delta_days = stats['delta_projected_end_date_days']
        print(f"\n  CONCLUSAO SOBRE DURACAO:")
        print(f"  Data de fim original : {original_end_date}")
        if original_end_date and delta_days:
            from datetime import datetime
            orig_d = datetime.strptime(original_end_date, "%Y-%m-%d").date()
            repair_d = orig_d + timedelta(days=delta_days)
            diff_end_date = repair_d.isoformat()
        print(f"  Data de fim reparado : {diff_end_date or 'N/D'}")
        if delta_days == 0:
            print(f"  O horario de reparacao termina NA MESMA DATA que o original.")
        elif delta_days > 0:
            print(f"  O horario de reparacao demora mais {delta_days} dia(s) a terminar.")
        else:
            print(f"  O horario de reparacao termina {abs(delta_days)} dia(s) mais cedo!")

# ---------------------------------------------------------------------------
# 10. APROVAR DRAFT
# ---------------------------------------------------------------------------
step("10 -- Aprovar rascunho de reparacao")
r = sess.post(f"{BASE}/schedule/drafts/{draft_gen_id}/approve")
if r.status_code == 200:
    approve_data = r.json()
    ok(f"Draft aprovado! Promovidos: {approve_data.get('promoted', '?')} blocos")
else:
    err("Erro ao aprovar draft", r)

print(f"\n{'='*60}")
print(f"  SIMULACAO CONCLUIDA COM SUCESSO")
print(f"{'='*60}")
print(f"  Horario Full (Solver {solver_version}): fim em {original_end_date}")
print(f"  15 ocorrencias: {gap_ok} GAP + {given_ok} GIVEN + {sub_ok} SUBSTITUTED")
print(f"  Repair (Solver {repair_solver_version}): fim em {diff_end_date or 'ver acima'}")
print(f"  Draft aprovado e ativado")
