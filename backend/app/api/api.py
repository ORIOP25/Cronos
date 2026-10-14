from fastapi import APIRouter

from app.api.v1.endpoints import (
    analytics,
    classes,
    client_errors,
    contact,
    courses,
    dashboard,
    foundation,
    health,
    imports,
    legal,
    members,
    occurrences,
    org_settings,
    readiness,
    rooms,
    schedule,
    scheduler,
    session,
    subjects,
    teachers,
    timesheets,
    timeslots,
    webhooks,
)

api_router = APIRouter()

api_router.include_router(contact.router, prefix="/contact", tags=["Contacto"])
api_router.include_router(client_errors.router, prefix="/client-errors", tags=["Client errors"])

# --- Registar Rotas ---
# Nota: Aqui definimos apenas o "caminho relativo".
# O prefixo "/api/v1" será adicionado no main.py, garantindo centralização.

api_router.include_router(members.router, prefix="/members", tags=["Equipa"])
api_router.include_router(imports.router, prefix="/imports", tags=["Importação CSV"])
api_router.include_router(teachers.router, prefix="/teachers", tags=["Teacher self-service/domain"])
api_router.include_router(classes.router, prefix="/classes", tags=["Turmas"])
api_router.include_router(subjects.router, prefix="/subjects", tags=["Disciplinas"])
api_router.include_router(rooms.router, prefix="/rooms", tags=["Salas"])
api_router.include_router(timeslots.router, prefix="/timeslots", tags=["timeslots"])
api_router.include_router(scheduler.router, prefix="/scheduler", tags=["Scheduler"])

api_router.include_router(schedule.router, prefix="/schedule", tags=["Gerador de Horários"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["Analytics"])
api_router.include_router(courses.router, prefix="/courses", tags=["courses"])
api_router.include_router(org_settings.router, prefix="/school", tags=["Configurações da Escola"])
api_router.include_router(occurrences.router, prefix="/occurrences", tags=["Ocorrências de Aulas"])
api_router.include_router(timesheets.router, prefix="/timesheets", tags=["Submissões Semanais"])
api_router.include_router(dashboard.router, tags=["Dashboard"])
api_router.include_router(readiness.router, prefix="/readiness", tags=["Prontidão"])
api_router.include_router(webhooks.router, prefix="/webhooks", tags=["Webhooks"])
api_router.include_router(foundation.router, tags=["Fundação"])
api_router.include_router(session.router, prefix="/session", tags=["Session"])
api_router.include_router(legal.router)

# Health Check (Geralmente não leva prefixo dentro da API ou usa /ops)
# Mas para ficar organizado, deixamos na raiz da API ou sob /ops
api_router.include_router(health.router, tags=["Operações (Health)"])
