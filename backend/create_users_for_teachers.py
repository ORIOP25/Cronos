import asyncio
import sys
import os
from sqlalchemy import select

# Setup do path
sys.path.insert(0, os.getcwd())

from app.db.database import SessionLocal 
from app.models import User, Teacher, UserRole
from app.services.user_service import hash_password

async def onboard_teachers():
    print("🚀 A criar logins para os professores...")
    
    async with SessionLocal() as db:
        # 1. Buscar todos os professores
        result = await db.execute(select(Teacher))
        teachers = result.scalars().all()
        
        for teacher in teachers:
            # Gerar um email baseado no nome (ex: Professor Pardal -> p.pardal@escola.com)
            # Simplificação: nome sem espaços + @escola.com
            safe_name = teacher.name.lower().replace(" ", ".")
            email = f"{safe_name}@escola.com"
            
            # Verificar se já existe user com este email
            user_exists = await db.execute(select(User).where(User.email == email))
            if user_exists.scalars().first():
                print(f"⚠️ {teacher.name} já tem login ({email}).")
                continue

            # Verificar se já existe user ligado a este teacher_id (mesmo com outro email)
            link_exists = await db.execute(select(User).where(User.teacher_id == teacher.id))
            if link_exists.scalars().first():
                print(f"⚠️ {teacher.name} já está ligado a um utilizador.")
                continue

            # CRIAR O USER
            print(f"👤 A criar conta para {teacher.name} ({email} / 1234)...")
            new_user = User(
                email=email,
                hashed_password=hash_password("1234"), # Password padrão
                role=UserRole.teacher,
                organization_id=teacher.organization_id,
                teacher_id=teacher.id # <--- A LIGAÇÃO MÁGICA
            )
            db.add(new_user)
        
        await db.commit()
        print("✅ Concluído! Agora os professores podem fazer login.")

if __name__ == "__main__":
    asyncio.run(onboard_teachers())