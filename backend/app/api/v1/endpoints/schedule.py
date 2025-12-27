from fastapi import APIRouter, Depends, HTTPException
from fastapi_cache.decorator import cache
from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession
from celery.result import AsyncResult
from typing import List
import json
import redis
from app import schemas, models
from app.api import deps
from app.services import schedule_service
from app.solver_tasks import generate_schedule_task
from app.config import settings

router = APIRouter()

# --- CONSTRAINTS (Regras) ---
@router.post("/constraints/", response_model=schemas.ConstraintRead)
async def create_constraint(
    item: schemas.ConstraintCreate, 
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_user)
):
    # Garante que usamos o org_id do utilizador logado
    return await schedule_service.create_constraint(db, item, current_user.organization_id)

@router.get("/constraints/", response_model=List[schemas.ConstraintRead])
async def read_constraints(
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_user)
):
    return await schedule_service.get_constraints_by_org(db, current_user.organization_id)

@router.delete("/constraints/{constraint_id}")
async def delete_constraint(
    constraint_id: int, 
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_user)
):
    success = await schedule_service.delete_constraint(db, constraint_id, current_user.organization_id)
    if not success:
        raise HTTPException(status_code=404, detail="Regra não encontrada")
    return {"ok": True}

# --- GERAÇÃO (Celery) ---
@router.post("/generate")
async def trigger_generation(
    current_user: models.User = Depends(deps.get_current_user)
):
    """Inicia a tarefa em background no Celery."""
    task = generate_schedule_task.delay(current_user.organization_id)
    return {"task_id": task.id, "status": "Processing started"}

@router.get("/status/{task_id}")
async def get_status(task_id: str):
    """Verifica o progresso da geração."""
    task_result = AsyncResult(task_id)
    response = {
        "task_id": task_id,
        "status": task_result.status,
        "result": task_result.result,
    }
    return response

# --- RESULTADOS ---
@router.get("/latest", response_model=List[schemas.ScheduleOutputRead])
async def get_schedule(
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_user)
):
    """
    Retorna o horário mais recente.
    Usa padrão 'Write-Through Cache' com Redis:
    1. Tenta ler do Redis.
    2. Se falhar, lê da BD e grava no Redis.
    """
    # Definimos a chave única para esta organização
    CACHE_KEY = f"schedule_latest_data_{current_user.organization_id}"
    
    # 1. Tentar ligar ao Redis
    try:
        r = redis.Redis.from_url(str(settings.REDIS_URL))
        cached_data = r.get(CACHE_KEY)
        
        if cached_data:
            # [CACHE HIT] - Encontrámos dados!
            print(f"⚡ Cache HIT para {CACHE_KEY}. A servir do Redis.")
            return json.loads(cached_data)
    except Exception as e:
        print(f"⚠️ Erro ao ler cache Redis: {e}. A seguir para a BD.")

    # 2. [CACHE MISS] - Não estava no Redis (ou foi apagado pelo Worker)
    print(f"🐢 Cache MISS para {CACHE_KEY}. A ler da Base de Dados...")
    
    # Vamos buscar à base de dados (Lento)
    latest_schedule = await schedule_service.get_latest_schedule_by_org(db, current_user.organization_id)
    
    # 3. Guardar no Redis para a próxima vez
    if latest_schedule:
        try:
            # Convertemos os objetos da BD para JSON puro
            json_data = jsonable_encoder(latest_schedule)
            
            # Guardamos no Redis com validade de 60 segundos (TTL)
            # Se ninguém apagar, expira sozinho.
            # Se o Worker gerar novo horário, ele apaga esta chave explicitamente.
            r.set(CACHE_KEY, json.dumps(json_data), ex=60)
        except Exception as e:
            print(f"⚠️ Erro ao gravar cache Redis: {e}")

    return latest_schedule

@router.delete("/reset")
async def reset_all_data(
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_user)
):
    await schedule_service.delete_all_schedule_data(db, current_user.organization_id)
    
    # [EXTRA] Se apagamos os dados, também devemos limpar a cache!
    try:
        r = redis.Redis.from_url(str(settings.REDIS_URL))
        CACHE_KEY = f"schedule_latest_data_{current_user.organization_id}"
        r.delete(CACHE_KEY)
    except:
        pass

    return {"msg": "Dados de horário apagados com sucesso."}