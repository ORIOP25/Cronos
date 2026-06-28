"""Constantes e utilitários partilhados de gestão de tasks do solver.

Este módulo centraliza valores e funções simples que antes estavam
duplicados entre o worker e os endpoints do scheduler,
eliminando o risco de dessincronização entre os dois.
"""

from app.config import settings

# ---------------------------------------------------------------------------
# Prefixos de chaves Redis
# ---------------------------------------------------------------------------

TASK_CANCEL_KEY_PREFIX = "schedule_task_cancel:"
ACTIVE_TASK_BY_ORG_KEY_PREFIX = "schedule_active_task_org:"

# ---------------------------------------------------------------------------
# Defaults de datas e janelas
# ---------------------------------------------------------------------------

DEFAULT_HARD_END_MONTH = 7
DEFAULT_HARD_END_DAY = 31
DEFAULT_REPAIR_WINDOW_DAYS = 14

# ---------------------------------------------------------------------------
# Funções utilitárias
# ---------------------------------------------------------------------------


def resolve_solver_engine_version() -> str:
    """Lê e valida a versão do engine solver configurada em SOLVER_ENGINE_VERSION.

    Devolve sempre 'v1' ou 'v2'. Qualquer valor inválido faz fallback para 'v1'.
    """
    version = str(getattr(settings, "SOLVER_ENGINE_VERSION", "v1")).lower()
    return version if version in {"v1", "v2"} else "v1"


def resolve_repair_window_days(org_settings) -> int:
    """Devolve a janela de estabilidade (dias) configurada na organização.

    Aceita qualquer objeto com o atributo `repair_stability_window_days`
    (tipicamente `models.OrganizationSettings`). Usa DEFAULT_REPAIR_WINDOW_DAYS
    como fallback quando o campo não está preenchido.
    """
    value = org_settings.repair_stability_window_days
    if value is None:
        return DEFAULT_REPAIR_WINDOW_DAYS
    return max(0, int(value))


def task_cancel_key(task_id: str) -> str:
    """Gera a chave Redis para o flag de cancelamento de uma task."""
    return f"{TASK_CANCEL_KEY_PREFIX}{task_id}"


def active_task_by_org_key(organization_id: int) -> str:
    """Gera a chave Redis para a task ativa de uma organização."""
    return f"{ACTIVE_TASK_BY_ORG_KEY_PREFIX}{organization_id}"
