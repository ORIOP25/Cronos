# 🔒 Guia de Boas Práticas para Endpoints - Apérius

## 📋 Resumo Executivo

Todos os endpoints devem seguir este padrão. As melhorias implementadas no `analytics.py` devem ser replicadas.

---

## 1️⃣ ESTRUTURA OBRIGATÓRIA DE CADA ENDPOINT

### Template Base
```python
import logging
from typing import List
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.api import deps
from app import models

logger = logging.getLogger(__name__)
router = APIRouter()

# --- SCHEMAS (Input/Output) ---
class ItemRead(BaseModel):
    id: int
    name: str
    
    class Config:
        json_schema_extra = {"example": {"id": 1, "name": "Item"}}

class ItemCreate(BaseModel):
    name: str

class PaginatedResponse(BaseModel):
    data: List[ItemRead]
    total: int
    skip: int
    limit: int

# --- ENDPOINTS ---
@router.get(
    "/items",
    response_model=PaginatedResponse,
    summary="Listar itens",
    tags=["Items"],
    responses={
        401: {"description": "Não autenticado"},
        500: {"description": "Erro servidor"}
    }
)
async def list_items(
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_user)],
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
):
    """Documentação detalhada do endpoint."""
    try:
        logger.info(f"List items: user={current_user.id}, org={current_user.organization_id}")
        
        # Implementação
        
        logger.info(f"Returned {len(items)} items")
        return PaginatedResponse(data=items, total=total, skip=skip, limit=limit)
        
    except Exception as e:
        logger.error(f"Error listing items: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao listar itens"
        )
```

---

## 2️⃣ CHECKLIST POR ENDPOINT

### 🔐 Segurança
- [ ] Autenticação: `current_user = Depends(deps.get_current_user)`
- [ ] Autorização: Validar `organization_id` do utilizador vs dados
- [ ] Validação de entrada: `Query(min=, max=)`, `Field(..., gt=0)`
- [ ] Rate limiting: Deve estar em `core/ratelimit.py`
- [ ] Sem hardcoding: Tudo vem de `config.py` ou do DB
- [ ] SQL injection: Usar SQLAlchemy parametrizado (não string format!)

### ⚡ Performance
- [ ] Paginação obrigatória: `skip` e `limit` com máximos
- [ ] Index-aware queries: Usar índices em `organization_id`, `timeslot_id`, etc.
- [ ] Sem N+1: Agregar em SQL com `func.count()`, não em Python
- [ ] Sem SELECT * desnecessários: Apenas colunas usadas
- [ ] Lazy loading evitado: Use `selectinload()` para relationships
- [ ] Cache considerado: Se dados mudam pouco, usar Redis

### 📊 Observabilidade
- [ ] Logging de entrada: User, org, parâmetros
- [ ] Logging de saída: Items retornados, tempo
- [ ] Logging de erro: Stack trace completo com `exc_info=True`
- [ ] Contexto estruturado: `extra={"user_id": current_user.id}`

### 📝 Documentação
- [ ] Docstring com descrição, lógica, segurança
- [ ] Response model definido (Pydantic schema)
- [ ] Status codes esperados (`responses={401: ..., 404: ..., 500: ...}`)
- [ ] Tags para agrupar no Swagger (`tags=["Resource"]`)
- [ ] Exemplos nos schemas (`json_schema_extra`)

### 🛡️ Tratamento de Erros
- [ ] Try/except em toda função
- [ ] HTTPException com status_code apropriado
- [ ] Mensagens de erro em português (seguras - sem dados sensíveis)
- [ ] 404 quando recurso não existe
- [ ] 403 quando utilizador sem permissão
- [ ] 400 quando input inválido
- [ ] 500 para erros inesperados (não exponha detalhes)

### 📋 Respostas Estruturadas
```python
# ❌ ERRADO
return items_list

# ✅ CERTO
return {
    "data": items,
    "total": total,
    "skip": skip,
    "limit": limit,
    "timestamp": datetime.utcnow()
}
```

---

## 3️⃣ PROBLEMAS CRÍTICOS A CORRIGIR

| Problema | Ficheiro | Impacto | Ação |
|----------|----------|--------|------|
| Sem paginação | `health.py`, `rooms.py`, `teachers.py` | Escalabilidade | Adicionar `skip`/`limit` |
| Sem logging | Todos | Observabilidade | Adicionar `logger.info/error` |
| Sem try/catch | `lessons.py`, `schedule.py` | Robustez | Wrapper try/except |
| Respostas soltas | `analytics.py` (original) | Inconsistência | Usar schemas com `data:` |
| Falta rate limit | Todos os endpoints | DDoS | Implementar decorator |
| Sem documentação | `import_data.py` | Manutenção | Docstrings detalhadas |
| N+1 queries | `teachers.py`, `classes.py` | Performance | Revisar JOINs |

---

## 4️⃣ RECOMENDAÇÕES POR ENDPOINT

### 🏥 health.py
- [x] ✅ Simples, sem DB
- [ ] Adicionar versão da API
- [ ] Adicionar status da DB (ping)
- [ ] Adicionar status do Redis (se usado)

```python
@router.get("/health", response_model=dict)
async def health_check(db: Annotated[AsyncSession, Depends(deps.get_db)]):
    try:
        # Test DB
        await db.execute(select(1))
        db_status = "healthy"
    except:
        db_status = "unhealthy"
    
    return {
        "status": "ok",
        "version": settings.VERSION,
        "database": db_status,
        "timestamp": datetime.utcnow()
    }
```

### 👨‍🏫 teachers.py
```python
# PROBLEMA ATUAL
@router.post("/{teacher_id}/availability")
async def update_teacher_availability(
    teacher_id: int,
    availability_data: List[schemas.AvailabilityCreate],
    db: Annotated[AsyncSession, Depends(deps.get_db)]
):
    # ❌ Falta: Autenticação, validação de permissão, logging, tratamento erro
```

**Melhorias:**
- [ ] Adicionar `current_user` e validar permissão
- [ ] Validar que `teacher_id` pertence à org do utilizador
- [ ] Logging antes/depois
- [ ] Try/except com HTTPException
- [ ] Response model estruturado

### 📅 schedule.py
- [ ] Paginação em listagem
- [ ] Cache possível se horários não mudam frequentemente
- [ ] Rate limit severo em POST (évita spam de horários)
- [ ] Auditoria em UPDATE/DELETE

### 📊 analytics.py
- [x] ✅ Já refatorizado
- [ ] Considerar cache Redis (dados não mudam frequentemente)
- [ ] Adicionar endpoint de estatísticas por professor
- [ ] Validar e documentar fórmulas matemáticas

### 🔐 auth.py
- [x] ✅ Crítico, revisar completamente
- [ ] Rate limit agressivo no login (máx 5 tentativas/IP)
- [ ] Log de falhas de autenticação
- [ ] Invalidar tokens ao logout
- [ ] Renovação de tokens

### 📥 import_data.py
- [ ] Processamento async com Celery
- [ ] Feedback de progresso (WebSocket?)
- [ ] Validação completa antes de importar
- [ ] Rollback se erro
- [ ] Logging detalhado

---

## 5️⃣ PADRÃO DE AUTORIZAÇÃO OBRIGATÓRIO

```python
# SEMPRE fazer isto:
org_id = current_user.organization_id

# NUNCA permitir que user defina org_id no payload
# SEMPRE validar que recursos pertencem à org do user

stmt = select(models.Teacher).where(
    and_(
        models.Teacher.id == teacher_id,
        models.Teacher.organization_id == org_id  # ← CRÍTICO
    )
)
```

---

## 6️⃣ SEGURANÇA EM PRODUÇÃO

### Rate Limiting
```python
# Implementar em core/ratelimit.py
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@router.get("/expensive-operation")
@limiter.limit("10/minute")
async def expensive_op(request: Request):
    pass
```

### CORS
```python
# Em main.py
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### HTTPS
- [ ] Obrigatório em produção (via `nginx.conf`)
- [ ] HSTS headers
- [ ] Secure cookies

### Headers de Segurança
```python
# Middleware em main.py
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    return response
```

### Validação de JWT
```python
# Em core/security.py - REVISAR
# - Token deve ter expiry
# - Validar signature
# - Verificar claims obrigatórios
```

---

## 7️⃣ TESTING

Cada endpoint deve ter:
```python
# tests/test_teachers.py

@pytest.mark.asyncio
async def test_get_teachers_unauthorized(client):
    response = client.get("/api/v1/teachers/")
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_get_teachers_pagination(client, auth_header):
    response = client.get(
        "/api/v1/teachers/?skip=0&limit=10",
        headers=auth_header
    )
    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    assert "total" in data
    assert len(data["data"]) <= 10

@pytest.mark.asyncio
async def test_create_teacher_validation(client, auth_header):
    response = client.post(
        "/api/v1/teachers/",
        json={"name": ""},  # Invalid
        headers=auth_header
    )
    assert response.status_code == 422
```

---

## 8️⃣ DEPLOYMENT CHECKLIST

Antes de ir para produção:

- [ ] Todos endpoints têm logging
- [ ] Todos endpoints têm autenticação
- [ ] Todos endpoints validam organization_id
- [ ] Sem SQL injection vulnerabilities
- [ ] Rate limiting ativo
- [ ] Error handling completo
- [ ] HTTPS ativo
- [ ] CORS configurado corretamente
- [ ] JWT com expiry apropriado
- [ ] Database backups configurados
- [ ] Monitoring/Alerts ativo (Sentry)
- [ ] Testes passam 100%
- [ ] Code review completo
- [ ] Performance testado (load testing)

---

## 📚 Referências

- FastAPI Best Practices: https://fastapi.tiangolo.com/
- OWASP Top 10: https://owasp.org/
- SQLAlchemy Security: https://docs.sqlalchemy.org/
- JWT Security: https://tools.ietf.org/html/rfc7519

---

**Última atualização:** 2026-01-08  
**Autor:** Code Review  
**Status:** Implementação em progresso
