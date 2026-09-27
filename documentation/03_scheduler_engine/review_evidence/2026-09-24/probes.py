"""Read-only review probes; records observed defects without changing product code."""
import json
from dataclasses import replace
from datetime import date, time, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from app.scheduler.domain.calendar import normalize_period
from app.scheduler.domain.candidate import Assignment, CandidateSchedule, PlanningSnapshot, ScheduledLesson
from app.scheduler.domain.candidate_validation import validate_candidate
from app.scheduler.domain.oracle import enumerate_candidates
from app.scheduler.domain.projection import ModuleRequirement, ModuleSlice
from app.scheduler.lab.campaign import campaign_failures, run_campaign_directory
from app.scheduler.lab.fixtures import AssignmentSpec, CaseExpectation, FixtureSpec
from app.scheduler.lab.manifest import CaseSeeds, LabCase, to_manifest
from app.scheduler.lab.reports import CampaignReport, CaseOutcome, CaseResult, compare_reports

DAY = date(2026, 9, 21)
def period(day=DAY, start=time(9), end=time(10)):
    return normalize_period(day, start, end, 'Europe/Lisbon')

assignment = Assignment(1, 1, 1, 1, frozenset({1}),
                        (ModuleRequirement(1, 1, 60), ModuleRequirement(2, 2, 60)))
snapshot = PlanningSnapshot(DAY, DAY + timedelta(days=4), DAY + timedelta(days=30),
                            (assignment,), {}, frozenset(range(5)), frozenset(), frozenset())
first = ScheduledLesson(1, 1, period(), 1, 60, (ModuleSlice(1, 1, 0, 60),))
second = ScheduledLesson(2, 1, period(DAY + timedelta(days=1)), 1, 60, (ModuleSlice(2, 2, 0, 60),))
candidate = CandidateSchedule((first, second))
assert validate_candidate(snapshot, candidate).valid
results = []
def record(identifier, expected, observed):
    results.append({'id': identifier, 'expected': expected, 'observed': observed,
                    'defect_reproduced': expected != observed})

swapped = CandidateSchedule((replace(first, slices=(ModuleSlice(1, 2, 0, 60),)),
                             replace(second, slices=(ModuleSlice(2, 1, 0, 60),))))
record('R01-module-chronology', False, validate_candidate(snapshot, swapped).valid)
unavailable = replace(snapshot, teacher_unavailable=frozenset({(1, period(start=time(9,30), end=time(10,30)))}))
record('R02-overlapping-unavailability', False, validate_candidate(unavailable, candidate).valid)
night = CandidateSchedule((replace(first, period=period(start=time(2),end=time(3))),second))
record('R03-no-school-period-membership', False, validate_candidate(snapshot, night).valid)
late = CandidateSchedule((first,replace(second,period=period(DAY+timedelta(days=7)))))
record('R04-initial-preferred-limit-unrepresented', False, validate_candidate(snapshot, late).valid)
protected = replace(snapshot, protected_lessons=(swapped.lessons[0],))
record('R05-legal-modular-update-protected', True, validate_candidate(protected, candidate).valid)

small = replace(snapshot, assignments=(replace(assignment,modules=(ModuleRequirement(1,1,60),)),),
                protected_lessons=(first,))
assert validate_candidate(small,CandidateSchedule((first,))).valid
record('R06-oracle-protected-witness', True, enumerate_candidates(small,(period(),)).feasible)
executed = {1: {1: 0}}
mutable = replace(snapshot,executed_minutes=executed)
executed[1][1] = 60
record('R07-snapshot-alias-mutation', 0, mutable.executed_minutes[1][1])

spec=FixtureSpec(DAY,DAY+timedelta(days=4),DAY+timedelta(days=30),frozenset(range(5)),
                 ((DAY,time(9),time(10)),),(AssignmentSpec(1,1,(60,),(1,)),))
case=LabCase('audit-case','minimal',1,CaseExpectation.FEASIBLE_WITH_WITNESS,spec,CaseSeeds(1,2,3))
with TemporaryDirectory() as directory:
    manifest=to_manifest('audit',(case,))
    original=run_campaign_directory(manifest,directory,commit='original')
    changed=replace(case,version=2,spec=replace(spec,assignments=(AssignmentSpec(1,1,(120,),(1,)),)))
    revised=to_manifest('audit',(changed,))
    resumed=run_campaign_directory(revised,directory,commit='different',resume=True)
    record('R08-resume-stale-case-accepted', False, len(campaign_failures(revised,resumed))==0)
    empty=run_campaign_directory(manifest,Path(directory)/'empty',case_ids=('unknown-id',))
    record('R09-unknown-selection-success', False, len(empty.results)==0 and not campaign_failures(manifest,empty))
    invalid=replace(case,expectation=CaseExpectation.INVALID_INPUT)
    invalid_manifest=to_manifest('invalid',(invalid,))
    invalid_run=run_campaign_directory(invalid_manifest,Path(directory)/'invalid')
    record('R10-invalid-input-inconclusive-pass', False, not campaign_failures(invalid_manifest,invalid_run))

before=CampaignReport('audit','old',(CaseResult('x','f',1,CaseOutcome.INVALID,'old-digest'),))
after=CampaignReport('audit','new',(CaseResult('x','f',2,CaseOutcome.VALID,'different-digest'),))
record('R11-comparator-mutation-regression', False,compare_reports(before,after).clean)

partial_a=replace(first,credit_minutes=30,slices=(ModuleSlice(1,1,0,30),))
partial_b=replace(second,credit_minutes=30,slices=(ModuleSlice(2,1,30,30),))
partial_snapshot=replace(small,protected_lessons=())
record('R12-nonfinal-partial-credit',False,validate_candidate(partial_snapshot,CandidateSchedule((partial_a,partial_b))).valid)

destination=Path('/workspace/.test-artifacts/scheduler-v1-review-20260924/probes.json')
destination.parent.mkdir(parents=True, exist_ok=True)
destination.write_text(json.dumps(results,indent=2)+'\n',encoding='utf-8')
for item in results:
    print(json.dumps(item))
assert all(item['defect_reproduced'] for item in results)
print(f'{len(results)} review discrepancies reproduced; no product files changed.')
