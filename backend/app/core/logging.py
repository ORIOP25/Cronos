# Ficheiro: app/core/logging.py
import logging
import sys
import structlog
from app.config import settings

def setup_logging():
    """
    Configura o sistema de logs para ser 'Enterprise Grade'.
    - Em 'local': Logs coloridos e fáceis de ler.
    - Em 'production': Logs em JSON para ferramentas como Datadog/Sentry/Render.
    """
    
    # 1. Decidir o formato base
    if settings.ENVIRONMENT == "local":
        # Desenvolvimento: Cores bonitas
        renderer = structlog.dev.ConsoleRenderer(colors=True)
        level = logging.DEBUG
    else:
        # Produção: JSON estruturado (Machine Readable)
        renderer = structlog.processors.JSONRenderer()
        level = logging.INFO

    # 2. Processadores (O que acontece a cada log)
    processors = [
        structlog.contextvars.merge_contextvars, # Junta variáveis de contexto (ex: user_id)
        structlog.processors.add_log_level,      # Adiciona "level": "info"
        structlog.processors.TimeStamper(fmt="iso"), # Adiciona timestamp ISO 8601
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,    # Formata exceções (tracebacks)
        renderer,                                # O renderizador escolhido acima
    ]

    # 3. Configurar o Structlog
    structlog.configure(
        processors=processors,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # 4. (Opcional) Intercetar logs do sistema (Uvicorn/FastAPI) para ficarem iguais
    # Isto garante que até os logs do servidor saem no nosso formato
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level,
    )

    # Define que estas bibliotecas só mostram logs se forem WARNING ou pior.
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("sentry_sdk").setLevel(logging.WARNING)