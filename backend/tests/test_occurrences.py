# Ficheiro: backend/tests/test_occurrences.py
#
# DEPRECATED: Este ficheiro foi dividido nos seguintes módulos:
#   test_occurrence_shared.py    — Fixtures partilhadas
#   test_occurrence_schemas.py   — TestLessonOccurrenceSchemas + TestWeekSchedulePerformance
#   test_occurrence_auto_confirm.py — TestAutoConfirmService
#   test_occurrence_state_machine.py — TestOccurrenceStateMachineAndAccounting
#   test_occurrence_substitution.py  — TestSubstitutionEligibilityAndRanking
#   test_occurrence_endpoints.py     — TestOccurrenceEndpoints
#
# Reexporta todas as classes para manter compatibilidade.

from test_occurrence_shared import *
from test_occurrence_schemas import TestLessonOccurrenceSchemas, TestWeekSchedulePerformance
from test_occurrence_auto_confirm import TestAutoConfirmService
from test_occurrence_state_machine import TestOccurrenceStateMachineAndAccounting
from test_occurrence_substitution import TestSubstitutionEligibilityAndRanking
from test_occurrence_endpoints import TestOccurrenceEndpoints
