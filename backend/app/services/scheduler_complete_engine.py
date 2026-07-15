from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone

from app import models
from app.scheduler.domain.contracts import (
    DraftBlockSpec,
    NoValidGenerationOutput,
    ValidatedGenerationResult,
)
from app.services.scheduler_candidates import CandidateUniverseBuilder
from app.services.scheduler_complete_demand import CompleteDemandLedgerBuilder
from app.services.scheduler_far_fill import FarFutureFiller
from app.services.scheduler_horizon import AdaptiveHorizonSelector
from app.services.scheduler_job_runtime import (
    GenerationExecutionContext,
)
from app.services.scheduler_near_optimizer import NearFutureOptimizer
from app.services.scheduler_quality_service import evaluate_target_quality


class CompleteGenerationEngine:
    async def generate(
        self,
        context: GenerationExecutionContext,
    ) -> ValidatedGenerationResult | NoValidGenerationOutput:
        await context.ensure_can_continue()
        if context.strategy != models.ScheduleGenerationStrategy.COMPLETE_GENERATION:
            return NoValidGenerationOutput(
                blockers=("Complete generation engine received a repair job.",)
            )
        snapshot = context.immutable_snapshot["generation_input"]
        ledger = CompleteDemandLedgerBuilder().build(snapshot)
        if not ledger.is_complete:
            return NoValidGenerationOutput(
                blockers=ledger.blockers,
                metrics={"required_minutes": ledger.required_minutes},
            )

        school_start = date.fromisoformat(snapshot["start_date"])
        hard_end = date.fromisoformat(snapshot["hard_end_date"])
        remaining_seconds = self._remaining_seconds(context)
        horizon = AdaptiveHorizonSelector().select(
            snapshot,
            ledger,
            start_date=school_start,
            remaining_solve_seconds=remaining_seconds,
        )
        candidate_builder = CandidateUniverseBuilder()
        near_universe = await asyncio.to_thread(
            candidate_builder.build,
            snapshot,
            ledger,
            window_start=horizon.start_date,
            window_end=horizon.end_date,
            deadline_at=context.solve_deadline_at,
        )
        await context.ensure_can_continue()
        if not near_universe.is_usable:
            return NoValidGenerationOutput(
                blockers=near_universe.blockers,
                metrics={"horizon_days": horizon.horizon_days},
            )
        optimizer_seconds = max(0.15, self._remaining_seconds(context) * 0.6)
        near_result = await asyncio.to_thread(
            NearFutureOptimizer().optimize,
            near_universe,
            ledger,
            snapshot,
            max_seconds=optimizer_seconds,
        )
        await context.ensure_can_continue()
        if near_result.status == "infeasible":
            return NoValidGenerationOutput(
                blockers=("Near-future optimization found no hard-valid placement.",),
                metrics={"horizon_days": horizon.horizon_days},
            )

        far_universe = await asyncio.to_thread(
            candidate_builder.build,
            snapshot,
            ledger,
            window_start=horizon.end_date + timedelta(days=1),
            window_end=hard_end,
            deadline_at=context.solve_deadline_at,
        )
        await context.ensure_can_continue()
        assembly = await asyncio.to_thread(
            FarFutureFiller().fill,
            ledger,
            near_result.selected,
            far_universe,
            snapshot,
            deadline_at=context.solve_deadline_at,
        )
        await context.ensure_can_continue()
        if not assembly.is_complete or assembly.projected_completion_date is None:
            return NoValidGenerationOutput(
                blockers=assembly.blockers or (
                    "The annual curriculum could not be fully placed before the hard end date.",
                ),
                metrics={
                    "required_minutes": assembly.required_minutes,
                    "scheduled_minutes": assembly.scheduled_minutes,
                    "horizon_days": horizon.horizon_days,
                },
            )

        room_types = {
            item.subject_id: item.required_room_type for item in ledger.items
        }
        blocks = tuple(
            DraftBlockSpec(
                stable_block_key=block.stable_block_key,
                class_id=block.class_id,
                subject_id=block.subject_id,
                teacher_id=block.teacher_id,
                room_id=block.room_id,
                room_type_id=models.RoomType(room_types[block.subject_id]),
                date=block.output_date,
                timeslot_id=block.timeslot_id,
                duration_minutes=block.duration_minutes,
                module_sequence_index=block.module_sequence_index,
                change_type=models.ScheduleDraftBlockChangeType.ADDED,
                reason_code=(
                    "OPTIMIZED_NEAR_FUTURE"
                    if block.source == "optimized"
                    else "PROVISIONAL_FAR_FUTURE"
                ),
            )
            for block in assembly.blocks
        )
        margin_days = (hard_end - assembly.projected_completion_date).days
        quality_metrics = evaluate_target_quality(snapshot, blocks)
        return ValidatedGenerationResult(
            result_category=models.ScheduleGenerationResultCategory.COMPLETE_SUCCESS,
            projected_completion_date=assembly.projected_completion_date,
            hard_end_date=hard_end,
            blocks=blocks,
            summary={
                "block_count": len(blocks),
                "required_minutes": assembly.required_minutes,
                "scheduled_minutes": assembly.scheduled_minutes,
                "near_future_blocks": sum(
                    block.reason_code == "OPTIMIZED_NEAR_FUTURE" for block in blocks
                ),
                "provisional_far_future_blocks": sum(
                    block.reason_code == "PROVISIONAL_FAR_FUTURE" for block in blocks
                ),
                "natural_hard_end_margin_days": margin_days,
            },
            warnings=(
                ("Far-future blocks are capacity-aware provisional placements.",)
                if any(block.reason_code == "PROVISIONAL_FAR_FUTURE" for block in blocks)
                else ()
            ),
            metrics={
                "horizon_days": horizon.horizon_days,
                "complexity_score": horizon.complexity_score,
                "estimated_near_candidate_count": horizon.estimated_candidate_count,
                **near_result.metrics,
                **quality_metrics,
                "quality_optimization_complete": near_result.status == "optimal",
            },
        )

    @staticmethod
    def _remaining_seconds(context: GenerationExecutionContext) -> float:
        return max(
            0.0,
            (context.solve_deadline_at - datetime.now(timezone.utc)).total_seconds(),
        )


async def run_complete_generation(
    context: GenerationExecutionContext,
) -> ValidatedGenerationResult | NoValidGenerationOutput:
    return await CompleteGenerationEngine().generate(context)
