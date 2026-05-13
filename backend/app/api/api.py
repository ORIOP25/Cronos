# Ficheiro: app/api/api.py

from fastapi import APIRouter
from app.api.v1.endpoints import (
    teachers,
    classes,
    subjects,
    rooms,
    schedule,
    analytics,
    import_data,
    lessons,
    timeslots,
    health,
    substitutions,
    courses,
    org_settings,
    occurrences,
    timesheets,
    dashboard,
    webhooks,
    onboarding,
)

api_router = APIRouter()

# --- Registar Rotas ---
# Nota: Aqui definimos apenas o "caminho relativo".
# O prefixo "/api/v1" será adicionado no main.py, garantindo centralização.

api_router.include_router(teachers.router, prefix="/teachers", tags=["Professores"])
api_router.include_router(classes.router, prefix="/classes", tags=["Turmas"])
api_router.include_router(subjects.router, prefix="/subjects", tags=["Disciplinas"])
api_router.include_router(rooms.router, prefix="/rooms", tags=["Salas"])
api_router.include_router(lessons.router, prefix="/lessons", tags=["Aulas"])
api_router.include_router(timeslots.router, prefix="/timeslots", tags=["timeslots"])
api_router.include_router(schedule.router, prefix="/schedule", tags=["Gerador de Horários"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["Analytics"])
api_router.include_router(import_data.router, prefix="/import", tags=["Importação de Dados"])
api_router.include_router(substitutions.router, prefix="/substitutions", tags=["substitutions"])
api_router.include_router(courses.router, prefix="/courses", tags=["courses"])
api_router.include_router(org_settings.router, prefix="/school", tags=["Configurações da Escola"])
api_router.include_router(occurrences.router, prefix="/occurrences", tags=["Ocorrências de Aulas"])
api_router.include_router(timesheets.router, prefix="/timesheets", tags=["Submissões Semanais"])
api_router.include_router(dashboard.router, tags=["Dashboard"])
api_router.include_router(webhooks.router, prefix="/webhooks", tags=["Webhooks"])
api_router.include_router(onboarding.router, tags=["Onboarding"])

# Health Check (Geralmente não leva prefixo dentro da API ou usa /ops)
# Mas para ficar organizado, deixamos na raiz da API ou sob /ops
api_router.include_router(health.router, tags=["Operações (Health)"])