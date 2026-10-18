import re
import uuid
from dataclasses import dataclass, field
from typing import Any

REQUEST_ID_HEADER = "X-Request-ID"
REQUEST_ID_PATTERN = re.compile(r"^[A-Z0-9]{12}$")


# Only these messages can cross the API boundary.  Exception text and provider
# responses are diagnostics, never presentation data.
PUBLIC_ERROR_CATALOG: dict[str, dict[str, Any]] = {
    "authentication_required": {
        "message": "A sua sessão terminou. Entre novamente.",
        "retryable": True,
    },
    "access_forbidden": {
        "message": "Não tem permissão para realizar esta ação.",
    },
    "resource_not_found": {"message": "O recurso pedido não foi encontrado."},
    "conflict": {"message": "Não foi possível concluir a operação porque os dados mudaram."},
    "resource_in_use": {
        "message": "Este recurso está a ser utilizado no horário atual. Remova ou republique o horário primeiro.",
    },
    "validation_error": {"message": "Reveja os dados indicados e tente novamente."},
    "bad_request": {"message": "Não foi possível processar o pedido."},
    "course_has_classes": {"message": "Apague primeiro as turmas deste curso."},
    "room_type_name_taken": {"message": "Já existe um tipo de sala com este nome."},
    "room_type_fixed": {
        "message": "O tipo Normal é fixo: não pode mudar de nome nem ser removido.",
    },
    "home_room_capacity": {
        "message": "A sala da turma não tem lugares para todos os alunos da turma.",
    },
    "too_many_requests": {
        "message": "Foram efetuadas demasiadas tentativas. Aguarde e tente novamente.",
        "retryable": True,
    },
    "service_unavailable": {
        "message": "O serviço está temporariamente indisponível. Tente novamente.",
        "retryable": True,
    },
    "unexpected_error": {
        "message": "Ocorreu um erro inesperado. Tente novamente.",
        "retryable": True,
        "support_required": True,
    },
    "request_body_too_large": {
        "message": "O pedido excede o limite permitido.",
    },
    "preflight_failed": {
        "message": "Não é possível iniciar a geração. Reveja os bloqueios indicados.",
    },
    "TEACHER_PRESENCE_IMPOSSIBLE": {
        "message": (
            "O mínimo de presença de um professor não cabe em nenhum dia disponível. "
            "Reveja o mínimo, o furo máximo ou a disponibilidade na Equipa."
        ),
    },
    "NO_ELIGIBLE_ROOM": {
        "message": (
            "Existem turmas sem sala compatível com o tipo e a lotação. "
            "Corrija as salas e volte a tentar."
        ),
    },
    "generation_dispatch_failed": {
        "message": "Não foi possível iniciar a geração do horário. Tente novamente.",
        "retryable": True,
    },
    "generation_selection_failed": {
        "message": "Não foi possível preparar a geração do horário. Reveja a configuração.",
    },
    "scheduler_state_not_configured": {
        "message": "A configuração do horário ainda não está completa.",
    },
    "no_operational_trigger": {
        "message": "Não há alterações que exijam uma nova geração neste momento.",
    },
    "pending_draft_replacement_required": {
        "message": "Já existe um rascunho pendente. Confirme a substituição para continuar.",
    },
    "teacher_competency_missing": {
        "message": "O professor não tem competência para lecionar esta disciplina.",
    },
    "duplicate_timeslot": {
        "message": "A disponibilidade contém um horário duplicado.",
    },
    "proposal_preview_forbidden": {"message": "Só a direção pode ver a proposta pendente."},
    "proposal_not_found": {"message": "Proposta não encontrada."},
    "INTERNSHIP_FLOW_INVALID": {
        "message": "Verifique o ano letivo, as datas e se selecionou apenas turmas ativas da escola."
    },
    "FOUNDATION_DRAFT_VERSION_CONFLICT": {
        "message": "O rascunho foi alterado por outro administrador. Atualize e tente novamente.",
        "retryable": True,
    },
    "FOUNDATION_ALREADY_COMPLETED": {
        "message": "A configuração inicial desta escola já foi concluída.",
    },
    "FOUNDATION_INCOMPLETE": {
        "message": "Conclua os dados obrigatórios antes de terminar a configuração.",
    },
    "HOLIDAY_SYNC_FAILED": {
        "message": "Não foi possível sincronizar os feriados. Tente novamente.",
        "retryable": True,
    },
    "CLERK_DIRECTORY_UNAVAILABLE": {
        "message": "Não foi possível confirmar os dados da sessão. Tente novamente.",
        "retryable": True,
    },
    "ACTIVE_ORGANIZATION_REQUIRED": {
        "message": "Selecione uma organização antes de continuar.",
    },
    "ACTIVE_ORGANIZATION_ACCESS_DENIED": {
        "message": "Não tem acesso à organização selecionada.",
    },
    "scheduler_state_invalid": {
        "message": "O estado da configuração do horário precisa de ser revisto.",
    },
    "CANCELED": {
        "message": "A geração foi cancelada. Pode iniciar uma nova geração.",
        "retryable": True,
    },
    "TIMED_OUT": {
        "message": "A geração demorou demasiado tempo. Os dados e o horário aprovado foram preservados.",
        "retryable": True,
    },
    "NO_VALID_OUTPUT": {
        "message": "As restrições atuais não permitiram gerar um horário válido. Reveja a disponibilidade e as regras.",
    },
    "FAILED_VALIDATION": {
        "message": "O rascunho gerado foi rejeitado antes da publicação. Reveja a configuração e tente novamente.",
    },
    "SYSTEM_ERROR": {
        "message": "Ocorreu um problema inesperado durante a geração. Tente novamente.",
        "retryable": True,
        "support_required": True,
    },
    "DISPATCH_STALLED": {
        "message": "A geração não chegou ao serviço de execução. Tente novamente.",
        "retryable": True,
        "support_required": True,
    },
    "WORKER_STALLED": {
        "message": "A execução da geração foi interrompida. Tente novamente.",
        "retryable": True,
        "support_required": True,
    },
    "member_sync_error": {
        "message": "A sincronização do acesso está pendente. Tente novamente dentro de instantes.",
        "retryable": True,
        "support_required": True,
    },
    "invitation_delivery_failed": {
        "message": "Não foi possível enviar o convite. Tente novamente dentro de instantes.",
        "retryable": True,
    },
    "contact_delivery_unavailable": {
        "message": "Não foi possível enviar a mensagem. Tente novamente dentro de instantes.",
        "retryable": True,
    },
    "turnstile_rejected": {"message": "A verificação anti-spam não foi aceite."},
    "turnstile_unavailable": {
        "message": "Não foi possível validar o pedido neste momento.",
        "retryable": True,
    },
}


STATUS_FALLBACK_CODES = {
    400: "bad_request",
    401: "authentication_required",
    403: "access_forbidden",
    404: "resource_not_found",
    409: "conflict",
    422: "validation_error",
    429: "too_many_requests",
    500: "unexpected_error",
    502: "service_unavailable",
    503: "service_unavailable",
    504: "service_unavailable",
}


@dataclass(slots=True)
class AppError(Exception):
    kind: str
    code: str
    detail: str
    metadata: dict[str, Any] = field(default_factory=dict)
    public_context: dict[str, Any] = field(default_factory=dict)
    public_fields: dict[str, str] = field(default_factory=dict)
    public_retryable: bool | None = None
    public_support_required: bool | None = None
    diagnostic_metadata: dict[str, Any] = field(default_factory=dict)


def new_error_reference() -> str:
    """Return the short opaque identifier shown to a user and support staff."""
    return uuid.uuid4().hex[:12].upper()


def request_reference(request: Any) -> str:
    """Reuse a safe request id, or create one at the API boundary."""
    current = getattr(request, "state", None)
    state_reference = getattr(current, "request_reference", None)
    if isinstance(state_reference, str) and REQUEST_ID_PATTERN.fullmatch(state_reference):
        return state_reference
    headers = getattr(request, "headers", {}) or {}
    incoming = headers.get(REQUEST_ID_HEADER)
    reference = (
        incoming
        if isinstance(incoming, str) and REQUEST_ID_PATTERN.fullmatch(incoming)
        else new_error_reference()
    )
    if current is not None:
        current.request_reference = reference
    return reference


def public_error_detail(
    *,
    code: str,
    reference: str,
    status_code: int,
    public_context: dict[str, Any] | None = None,
    fields: dict[str, str] | None = None,
    retryable: bool | None = None,
    support_required: bool | None = None,
) -> dict[str, Any]:
    """Build the only error shape allowed to leave the backend."""
    fallback_code = STATUS_FALLBACK_CODES.get(status_code, "unexpected_error")
    catalog = PUBLIC_ERROR_CATALOG.get(code) or PUBLIC_ERROR_CATALOG[fallback_code]
    return {
        "code": code or fallback_code,
        "message": catalog["message"],
        "reference": reference,
        "retryable": catalog.get("retryable", False) if retryable is None else retryable,
        "support_required": catalog.get("support_required", False)
        if support_required is None
        else support_required,
        "fields": fields or {},
        "context": public_context or {},
    }


def status_code_for_kind(kind: str, code: str | None = None) -> int:
    if code == "preflight_failed":
        return 400
    return {
        "bad_request": 400,
        "validation": 422,
        "not_found": 404,
        "conflict": 409,
        "forbidden": 403,
        "unauthorized": 401,
        "too_many_requests": 429,
        "unavailable": 503,
    }.get(kind, 500)
