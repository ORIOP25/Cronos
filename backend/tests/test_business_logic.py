# Ficheiro: backend/tests/test_business_logic.py
#
# DEPRECATED: Este ficheiro foi dividido nos seguintes módulos:
#   test_business_logic_shared.py   — Helpers partilhados
#   test_teacher_competencies.py    — TestCompetencies
#   test_module_progress.py         — TestModuleProgress
#   test_availability_paintbrush.py — TestTeacherAvailability
#   test_tenant_isolation_business.py — TestTenantIsolation
#
# Reexporta todas as classes para manter compatibilidade.

from test_business_logic_shared import *
from test_teacher_competencies import TestCompetencies
from test_module_progress import TestModuleProgress
from test_availability_paintbrush import TestTeacherAvailability
from test_tenant_isolation_business import TestTenantIsolation
