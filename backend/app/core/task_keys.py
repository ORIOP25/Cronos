"""Shared scheduler defaults that are still used by runtime services."""

DEFAULT_REPAIR_WINDOW_DAYS = 14


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
