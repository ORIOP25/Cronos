"""CP-SAT Solver Engine V2 — Aperius (Fase E).

Opera sobre datas absolutas (real calendar dates) em vez de padrão semanal.
Resolve 5 objetivos em cascata lexicográfica:
  1. makespan_global        — minimizar data final global
  2. end_date_spread_classes — minimizar dispersão de fecho entre turmas
  3. target_drift_total     — minimizar desvio da data-alvo da escola
  4. churn_outside_frozen   — minimizar blocos alterados fora da janela congelada
  5. class_gaps_total       — minimizar furos por turma/dia

Hard Constraints (HC1–HC7) são verificadas no candidatos pré-prunados (Fase D)
e reforçadas no modelo CP-SAT por data real.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

import structlog
from ortools.sat.python import cp_model

from app.core.solver_v2_candidates import SolverV2Candidate

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Constantes do solver V2
# ---------------------------------------------------------------------------
SOLVER_V2_MAX_SECONDS = 300
SOLVER_V2_NUM_WORKERS = 4

# Índice numérico para cada data no horizonte (usado em variáveis inteiras)
# O makespan é representado como número de dias desde a primeira data da janela.


# ---------------------------------------------------------------------------
# Tipos de saída
# ---------------------------------------------------------------------------

@dataclass
class ScheduledBlockV2:
    """Bloco de horário com data absoluta — saída do Solver V2."""
    lesson_id: int
    class_id: int
    ts_id: int
    room_id: int
    output_date: date
    duration_minutes: int


@dataclass
class SolverV2Result:
    """Resultado completo do Solver V2."""
    status: str                          # "optimal" | "feasible" | "infeasible"
    blocks: list[ScheduledBlockV2]
    makespan_days: int | None            # dias desde window_start até último bloco
    projected_end_date: date | None      # data real do último bloco
    end_date_spread_days: int | None     # max_end - min_end entre turmas
    target_drift_days: int | None        # desvio total da data-alvo
    churn_blocks: int | None             # blocos alterados vs publicado
    gaps_total: int | None               # furos totais
    objective_value: float | None
    solver_wall_time: float | None


# ---------------------------------------------------------------------------
# Motor principal V2
# ---------------------------------------------------------------------------

class ScheduleEngineV2:
    """
    Motor CP-SAT V2 que opera sobre candidatos pré-prunados por data real.

    Recebe a lista de SolverV2Candidate já filtrados (Fase D) e resolve
    o problema de alocação com objetivo lexicográfico em 5 etapas.
    """

    def __init__(
        self,
        candidates: list[SolverV2Candidate],
        *,
        window_start_date: date,
        window_end_date: date,
        school_target_end_date: date | None = None,
        hard_end_date: date | None = None,
        published_blocks: set[tuple[int, date, int]] | None = None,
        frozen_until: date | None = None,
        max_seconds: int = SOLVER_V2_MAX_SECONDS,
    ) -> None:
        self.candidates = candidates
        self.window_start_date = window_start_date
        self.window_end_date = window_end_date
        self.school_target_end_date = school_target_end_date
        self.hard_end_date = hard_end_date or window_end_date
        # published_blocks: set of (lesson_id, date, ts_id) from current published plan
        self.published_blocks: set[tuple[int, date, int]] = published_blocks or set()
        self.frozen_until = frozen_until
        self.max_seconds = max(1, max_seconds)

        self.model = cp_model.CpModel()
        self.solver = cp_model.CpSolver()

        # Decision variables: x[candidate_key] = BoolVar
        self.x: dict[str, cp_model.IntVar] = {}
        # Auxiliary: lesson_scheduled_on_date[(lesson_id, date_idx)] = BoolVar
        self.lesson_on_date: dict[tuple[int, int], cp_model.IntVar] = {}

        # Date index mapping
        self._dates: list[date] = self._build_date_index()
        self._date_to_idx: dict[date, int] = {d: i for i, d in enumerate(self._dates)}
        self._n_dates = len(self._dates)

        # Group candidates by key dimensions
        self._cands_by_lesson: dict[int, list[SolverV2Candidate]] = defaultdict(list)
        self._cands_by_teacher_date_ts: dict[tuple[int, date, int], list[str]] = defaultdict(list)
        self._cands_by_class_date_ts: dict[tuple[int, date, int], list[str]] = defaultdict(list)
        self._cands_by_room_date_ts: dict[tuple[int, date, int], list[str]] = defaultdict(list)
        self._class_ids: set[int] = set()
        self._lesson_class: dict[int, int] = {}  # lesson_id -> class_id
        self._lesson_duration: dict[int, int] = {}  # lesson_id -> duration_minutes (first ts)

        for c in candidates:
            self._cands_by_lesson[c.lesson_id].append(c)
            self._cands_by_teacher_date_ts[(c.teacher_id, c.output_date, c.ts_id)].append(c.candidate_key)
            self._cands_by_class_date_ts[(c.class_id, c.output_date, c.ts_id)].append(c.candidate_key)
            self._cands_by_room_date_ts[(c.room_id, c.output_date, c.ts_id)].append(c.candidate_key)
            self._class_ids.add(c.class_id)
            self._lesson_class[c.lesson_id] = c.class_id
            if c.lesson_id not in self._lesson_duration:
                self._lesson_duration[c.lesson_id] = c.duration_minutes

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def solve(self) -> SolverV2Result:
        """Executa a resolução lexicográfica em 5 etapas."""
        if not self.candidates or self._n_dates == 0:
            return SolverV2Result(
                status="infeasible", blocks=[], makespan_days=None,
                projected_end_date=None, end_date_spread_days=None,
                target_drift_days=None, churn_blocks=None, gaps_total=None,
                objective_value=None, solver_wall_time=None,
            )

        logger.info(
            "🧠 Solver V2 a iniciar",
            candidates=len(self.candidates),
            dates=self._n_dates,
            classes=len(self._class_ids),
        )

        self._create_variables()
        self._apply_hard_constraints()

        # Lexicographic solve
        status = self._solve_lexicographic()

        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            logger.warning("❌ Solver V2: sem solução", status=status)
            if status == cp_model.MODEL_INVALID:
                print("Model Invalid Details:", self.model.Validate())
            return SolverV2Result(
                status="infeasible", blocks=[], makespan_days=None,
                projected_end_date=None, end_date_spread_days=None,
                target_drift_days=None, churn_blocks=None, gaps_total=None,
                objective_value=self.solver.ObjectiveValue() if status == cp_model.FEASIBLE else None,
                solver_wall_time=self.solver.WallTime(),
            )

        blocks = self._extract_blocks()
        metrics = self._compute_result_metrics(blocks)
        status_str = "optimal" if status == cp_model.OPTIMAL else "feasible"
        logger.info("✅ Solver V2: solução encontrada", status=status_str, blocks=len(blocks))

        return SolverV2Result(
            status=status_str,
            blocks=blocks,
            **metrics,
            objective_value=self.solver.ObjectiveValue(),
            solver_wall_time=self.solver.WallTime(),
        )

    # ------------------------------------------------------------------
    # Internal: date index
    # ------------------------------------------------------------------

    def _build_date_index(self) -> list[date]:
        """Builds ordered list of dates in [window_start, window_end]."""
        dates = []
        cur = self.window_start_date
        while cur <= self.window_end_date:
            dates.append(cur)
            cur += timedelta(days=1)
        return dates

    # ------------------------------------------------------------------
    # E.01 — Variable creation
    # ------------------------------------------------------------------

    def _create_variables(self) -> None:
        """E.01: Creates binary decision vars x[key] for each pruned candidate."""
        for c in self.candidates:
            var = self.model.NewBoolVar(f"x_{c.candidate_key}")
            self.x[c.candidate_key] = var

        # Auxiliary: lesson_on_date[(lesson_id, date_idx)]
        for lesson_id, cands in self._cands_by_lesson.items():
            dates_for_lesson = {c.output_date for c in cands}
            for d in dates_for_lesson:
                idx = self._date_to_idx.get(d)
                if idx is None:
                    continue
                key = (lesson_id, idx)
                day_vars = [
                    self.x[c.candidate_key]
                    for c in cands
                    if c.output_date == d
                ]
                aux = self.model.NewBoolVar(f"lon_{lesson_id}_{idx}")
                self.model.Add(sum(day_vars) == aux)
                self.lesson_on_date[key] = aux

    # ------------------------------------------------------------------
    # E.02 — Hard Constraints
    # ------------------------------------------------------------------

    def _apply_hard_constraints(self) -> None:
        """E.02: HC1–HC7 enforced on real dates."""
        self._hc_room_conflict()
        self._hc_teacher_conflict()
        self._hc_class_conflict()
        # HC4 room type and HC5 IMPOSSIBLE already enforced by pruning (Phase D)
        # HC6 lunch already enforced by pruning (Phase D)
        self._hc_hard_end_date()
        self._hc_every_lesson_must_be_scheduled()

    def _hint_solution(self) -> None:
        """Adds the current solver solution as a hint to the model for the next stage."""
        self.model.ClearHints()
        for var in self.x.values():
            self.model.AddHint(var, self.solver.Value(var))

    def _hc_room_conflict(self) -> None:
        """HC1: At most one lesson per room per (date, timeslot)."""
        for (room_id, d, ts_id), keys in self._cands_by_room_date_ts.items():
            if len(keys) > 1:
                self.model.Add(sum(self.x[k] for k in keys) <= 1)

    def _hc_teacher_conflict(self) -> None:
        """HC2: At most one lesson per teacher per (date, timeslot)."""
        for (teacher_id, d, ts_id), keys in self._cands_by_teacher_date_ts.items():
            if len(keys) > 1:
                self.model.Add(sum(self.x[k] for k in keys) <= 1)

    def _hc_class_conflict(self) -> None:
        """HC3: At most one lesson per class per (date, timeslot)."""
        for (class_id, d, ts_id), keys in self._cands_by_class_date_ts.items():
            if len(keys) > 1:
                self.model.Add(sum(self.x[k] for k in keys) <= 1)

    def _hc_hard_end_date(self) -> None:
        """HC7: No assignments beyond hard_end_date."""
        for c in self.candidates:
            if c.output_date > self.hard_end_date:
                self.model.Add(self.x[c.candidate_key] == 0)

    def _hc_every_lesson_must_be_scheduled(self) -> None:
        """Coverage: each lesson must appear exactly once in the CP-SAT pattern.

        Prevents the trivial empty solution. The fill_opportunistic phase
        (Phase F) is responsible for repeating blocks to reach 100% occupancy.
        """
        for lesson_id, cands in self._cands_by_lesson.items():
            lesson_vars = [self.x[c.candidate_key] for c in cands]
            self.model.Add(sum(lesson_vars) == 1)

    # ------------------------------------------------------------------
    # E.03–E.07 — Lexicographic solve
    # ------------------------------------------------------------------

    def _solve_lexicographic(self) -> int:
        """
        Resolves stages 1–5 in cascade. Each stage fixes the optimal of the
        previous via an upper-bound constraint before optimizing the next.
        """
        self.solver.parameters.max_time_in_seconds = self.max_seconds
        self.solver.parameters.num_search_workers = SOLVER_V2_NUM_WORKERS
        self.solver.parameters.log_search_progress = False

        n = self._n_dates

        # ---- Stage 1: makespan_global ----
        # class_end_idx[class_id] = last date index where this class has a lesson
        makespan = self.model.NewIntVar(0, max(n - 1, 0), "makespan")
        class_end_idx: dict[int, cp_model.IntVar] = {}

        for class_id in self._class_ids:
            class_lessons = [lid for lid, cid in self._lesson_class.items() if cid == class_id]
            ce = self.model.NewIntVar(0, max(n - 1, 0), f"class_end_{class_id}")
            class_end_idx[class_id] = ce

            # Collect all (idx, aux_var) for lessons of this class
            idx_aux_pairs: list[tuple[int, cp_model.IntVar]] = []
            for lid in class_lessons:
                for (l2, idx), aux in self.lesson_on_date.items():
                    if l2 == lid:
                        idx_aux_pairs.append((idx, aux))

            if not idx_aux_pairs:
                self.model.Add(ce == 0)
                continue

            # ce = sum(idx * aux) for all (idx, aux) pairs of this class
            # This works because exactly one aux per lesson (coverage constraint)
            # and aux sums are either 0 or 1 per date, giving the scheduled date index.
            weighted_terms = []
            for idx, aux in idx_aux_pairs:
                term = self.model.NewIntVar(0, max(n - 1, 0), f"ce_term_{class_id}_{idx}")
                self.model.Add(term == idx * aux)
                weighted_terms.append(term)

            # ce = max of all terms (since exactly one is active per lesson across all dates)
            self.model.AddMaxEquality(ce, weighted_terms)

        for class_id, ce in class_end_idx.items():
            self.model.Add(makespan >= ce)


        self.model.Minimize(makespan)
        status = self.solver.Solve(self.model)

        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return status

        self._hint_solution()
        best_makespan = int(self.solver.Value(makespan))
        self.model.Add(makespan <= best_makespan + 1)

        # ---- Stage 2: end_date_spread_classes ----
        if len(class_end_idx) >= 2:
            max_end = self.model.NewIntVar(0, max(n - 1, 0), "max_end")
            min_end = self.model.NewIntVar(0, max(n - 1, 0), "min_end")
            spread = self.model.NewIntVar(0, max(n - 1, 0), "spread")

            # max_end >= every class end; min_end <= every class end
            for ce in class_end_idx.values():
                self.model.Add(max_end >= ce)
                self.model.Add(min_end <= ce)

            # min_end must equal the minimum (not be set arbitrarily low)
            # Enforce min_end >= some ce (existential lower bound)
            min_end_candidates = []
            for class_id, ce in class_end_idx.items():
                is_min = self.model.NewBoolVar(f"is_min_{class_id}")
                min_end_candidates.append(is_min)
                # If is_min=1 then min_end == ce
                self.model.Add(min_end == ce).OnlyEnforceIf(is_min)
            # At least one class must be the minimum
            self.model.AddBoolOr(min_end_candidates)

            self.model.Add(spread == max_end - min_end)
            self.model.Minimize(spread)
            status = self.solver.Solve(self.model)
            if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                return status
            self._hint_solution()
            best_spread = int(self.solver.Value(spread))
            self.model.Add(spread <= best_spread + 1)
        else:
            spread = None

        # ---- Stage 3: target_drift_total ----
        if self.school_target_end_date is not None:
            target_idx = self._date_to_idx.get(self.school_target_end_date)
            if target_idx is None:
                # Clamp to window bounds
                if self.school_target_end_date < self.window_start_date:
                    target_idx = 0
                else:
                    target_idx = n - 1

            drift_total = self.model.NewIntVar(0, max(n * len(self._class_ids), 1), "drift_total")
            drift_parts = []
            for class_id, ce in class_end_idx.items():
                drift = self.model.NewIntVar(0, max(n - 1, 0), f"drift_{class_id}")
                self.model.Add(drift >= ce - target_idx)
                self.model.Add(drift >= target_idx - ce)
                drift_parts.append(drift)

            self.model.Add(drift_total == sum(drift_parts))
            self.model.Minimize(drift_total)
            status = self.solver.Solve(self.model)
            if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                return status
            self._hint_solution()
            best_drift = int(self.solver.Value(drift_total))
            self.model.Add(drift_total <= best_drift + 2)

        # ---- Stage 4: churn_outside_frozen ----
        if self.published_blocks:
            # Count new blocks NOT in published set
            churn_vars = []
            for c in self.candidates:
                if self.frozen_until and c.output_date <= self.frozen_until:
                    continue
                pub_key = (c.lesson_id, c.output_date, c.ts_id)
                if pub_key not in self.published_blocks:
                    # This candidate would be a new/changed block
                    churn_vars.append(self.x[c.candidate_key])

            if churn_vars:
                churn = self.model.NewIntVar(0, len(churn_vars), "churn")
                self.model.Add(churn == sum(churn_vars))
                self.model.Minimize(churn)
                status = self.solver.Solve(self.model)
                if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                    return status
                self._hint_solution()
                best_churn = int(self.solver.Value(churn))
                self.model.Add(churn <= best_churn + 2)

        # ---- Stage 5: class_gaps_total ----
        gap_vars = self._build_gap_vars()
        if gap_vars:
            gaps_total = self.model.NewIntVar(0, len(gap_vars), "gaps_total")
            self.model.Add(gaps_total == sum(gap_vars))
            self.model.Minimize(gaps_total)
            status = self.solver.Solve(self.model)
            if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                return status
            
            self._hint_solution()
            best_gaps = int(self.solver.Value(gaps_total))
            self.model.Add(gaps_total <= best_gaps + 1)

        return status

    def _build_gap_vars(self) -> list:
        """E.07: Models gaps (empty slots between occupied slots) per class per day."""
        gap_vars = []
        # Group lesson_on_date by (class_id, date_idx)
        class_day_scheduled: dict[tuple[int, int], list[cp_model.IntVar]] = defaultdict(list)
        for (lesson_id, date_idx), aux in self.lesson_on_date.items():
            class_id = self._lesson_class.get(lesson_id)
            if class_id is not None:
                class_day_scheduled[(class_id, date_idx)].append(aux)

        for (class_id, date_idx), day_vars in class_day_scheduled.items():
            if len(day_vars) < 3:
                continue
            # Simple proxy: gap exists if there's an unoccupied slot between two occupied ones.
            # We model: sum of occupancy across day slots to detect gaps.
            # A simplified model: a gap is possible only if > 1 slots are used in the day.
            for idx in range(1, len(day_vars) - 1):
                has_before = self.model.NewBoolVar(f"gbef_{class_id}_{date_idx}_{idx}")
                has_after = self.model.NewBoolVar(f"gaft_{class_id}_{date_idx}_{idx}")
                is_empty = self.model.NewBoolVar(f"gemp_{class_id}_{date_idx}_{idx}")
                is_gap = self.model.NewBoolVar(f"gap_{class_id}_{date_idx}_{idx}")

                before_vars = day_vars[:idx]
                after_vars = day_vars[idx + 1:]
                current_var = day_vars[idx]

                # has_before = OR(before_vars)
                for v in before_vars:
                    self.model.Add(has_before >= v)
                self.model.Add(has_before <= sum(before_vars))

                # has_after = OR(after_vars)
                for v in after_vars:
                    self.model.Add(has_after >= v)
                self.model.Add(has_after <= sum(after_vars))

                # is_empty = 1 - current
                self.model.Add(is_empty == 1 - current_var)

                # is_gap = has_before AND has_after AND is_empty
                self.model.Add(is_gap <= has_before)
                self.model.Add(is_gap <= has_after)
                self.model.Add(is_gap <= is_empty)
                self.model.Add(is_gap >= has_before + has_after + is_empty - 2)

                gap_vars.append(is_gap)

        return gap_vars

    # ------------------------------------------------------------------
    # Extract results
    # ------------------------------------------------------------------

    def _extract_blocks(self) -> list[ScheduledBlockV2]:
        blocks = []
        for c in self.candidates:
            if self.solver.Value(self.x[c.candidate_key]) == 1:
                blocks.append(ScheduledBlockV2(
                    lesson_id=c.lesson_id,
                    class_id=c.class_id,
                    ts_id=c.ts_id,
                    room_id=c.room_id,
                    output_date=c.output_date,
                    duration_minutes=c.duration_minutes,
                ))
        return blocks

    def _compute_result_metrics(self, blocks: list[ScheduledBlockV2]) -> dict:
        if not blocks:
            return dict(
                makespan_days=None, projected_end_date=None,
                end_date_spread_days=None, target_drift_days=None,
                churn_blocks=None, gaps_total=None,
            )

        # makespan / projected_end
        max_date = max(b.output_date for b in blocks)
        makespan_days = (max_date - self.window_start_date).days
        projected_end_date = max_date

        # spread
        class_ends: dict[int, date] = {}
        for b in blocks:
            if b.class_id not in class_ends or b.output_date > class_ends[b.class_id]:
                class_ends[b.class_id] = b.output_date
        if len(class_ends) >= 2:
            spread = (max(class_ends.values()) - min(class_ends.values())).days
        else:
            spread = 0

        # target drift
        if self.school_target_end_date and class_ends:
            drift = sum(
                abs((end - self.school_target_end_date).days)
                for end in class_ends.values()
            )
        else:
            drift = None

        # churn
        new_block_keys = {(b.lesson_id, b.output_date, b.ts_id) for b in blocks}
        churn = len(new_block_keys - self.published_blocks) if self.published_blocks else None

        return dict(
            makespan_days=makespan_days,
            projected_end_date=projected_end_date,
            end_date_spread_days=spread,
            target_drift_days=drift,
            churn_blocks=churn,
            gaps_total=None,  # counted by model, not re-computed here
        )
