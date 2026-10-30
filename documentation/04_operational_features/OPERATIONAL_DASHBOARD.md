# Operational Dashboard

The operational dashboard at `/dashboard` shows an administrator what to do today, how this week compares with earlier weeks, and how the school year is going.
It appears after the first real schedule is approved. Before that, the preparation dashboard appears (see [Onboarding](../00_getting_started/ONBOARDING.md#phase-6-operational-transition)).

## Data Sources

| Endpoint | Content |
| :--- | :--- |
| `GET /api/v1/dashboard` | Pending tasks, resource counts, schedule statistics, class progress, and the current debt total. |
| `GET /api/v1/dashboard/insights` | Weekly trends, open debt per class at each week end, teacher rankings, and planned minutes per class up to today. |

The frontend requests the insights only when the main payload is in `OPERATIONAL` mode.
Both responses use the active school year and the active (published) v1 schedule version.
[`OperationalDashboardResponse` and `DashboardInsightsResponse`](../../backend/app/schemas.py) define the fields.

## Sections

1. **A requerer atenção**: pending absence decisions, submitted timesheets, and schedule drafts.
   An absence decision is urgent (red) when its lesson is today or later.
   Each task shows the age of its oldest item and opens the filtered page.
   A list of facts, such as the share of this week's lessons with a log, appears below the tasks.
2. **Esta semana**: four indicators for the current week so far, each with a line of the last 12 weeks.
3. **Horas em dívida ao longo do ano**: a line of the open debt at the end of each school week.
   The administrator can filter it by course or class. "Ver detalhes" opens the debt tab with the same class.
4. **Progresso curricular**: class progress with a vertical mark where the class should be today.
5. **Rankings**: classes furthest behind their expected progress, classes with the most debt, teachers with the most absence time, and teachers with the most missing lesson logs.
6. **Disponibilidade**: the teacher availability heatmap.
7. **A escola e o horário**: resource counts, ratios per class, and the approved schedule period and averages.

The dashboard does not show schedule conflicts. The generator does not produce them.

## Metric Definitions

[`dashboard_insights.py`](../../backend/app/scheduler/domain/dashboard_insights.py) owns these rules.

| Indicator | Rule |
| :--- | :--- |
| Aulas dadas | Lessons that ended this week with a `COMPLETED` log or a `SUBSTITUTED` decision, divided by all lessons that ended this week. |
| Faltas de professores | Physical minutes of lessons with an `OCCURRENCE` log, in any decision state. A joint lesson counts once for its teacher. |
| Faltas cobertas por substituição | Minutes with a `SUBSTITUTED` decision, divided by the absence minutes of the same period. |
| Sumários em falta | Lessons that ended without a log, or whose occurrence was revoked. |
| Debt at a week end | For each debt claim: created minutes, plus revisions, minus settlements, dated up to that week end. A claim never goes below zero. |
| Expected progress | Credit minutes of the class's lessons up to today in the active version, divided by the class's required minutes. |

Debt movements use these dates in the school timezone:
the origin date for the created minutes, the record date for a revision, and the record date of the settling execution for a settlement.
A movement never counts before the origin date of its claim.
The line can differ from the "Hoje" total below it, because the total also includes debt for future lessons.

## Limits

- The current week is partial. Absolute values, such as absence time, show last week's value without a coloured trend.
- Classes that are archived count in the school-wide debt line, but not in the course and class filters or the class rankings.

## Verification Procedure

1. Open `/dashboard` as an administrator of a school with an approved schedule.
2. Record an absence, decide it as a gap, and refresh the dashboard.
3. Check that the absence time, the debt line, and the teacher ranking change.
4. Filter the debt line by the class of the absence, then open "Ver detalhes".

## Source Map

- `backend/app/scheduler/domain/dashboard_insights.py`
- `backend/app/services/dashboard_service.py`
- `backend/app/api/v1/endpoints/dashboard.py`
- `frontend/src/pages/Dashboard.jsx`
- `frontend/src/components/dashboard/`
- `frontend/src/features/dashboard/insights.js`
- Tests: `backend/tests/unit/test_dashboard_insights_rule.py`, `backend/tests/integration/committed/test_scheduler_v1_occurrences.py`, `backend/tests/integration/committed/test_query_budgets.py`, `frontend/src/test/Dashboard.test.jsx`, `frontend/src/test/dashboardInsights.test.js`

## Related Documents

- [Occurrences and Substitutions](OCCURRENCES_AND_SUBSTITUTIONS.md)
- [Timesheets and Progress](TIMESHEETS_AND_PROGRESS.md)
