#!/usr/bin/env python3
"""
Script COMPLETO: Limpar BD + Preencher dados de teste
Usa: python init_db.py (com venv já ativado)
"""
import sys
import os
from sqlalchemy import text
from app.db.database import engine, SessionLocalSync, Base
from app import models

def init_database():
    """Limpar + Recria + Popula"""
    
    print("=" * 60)
    print("🗑️  INICIANDO BASE DE DADOS (Clean + Seed)")
    print("=" * 60)
    
    # 1. DROP ALL TABLES
    print("\n1️⃣  A eliminar todas as tabelas...")
    with engine.begin() as connection:
        # Disable FK constraints temporariamente
        connection.execute(text("PRAGMA foreign_keys=OFF;"))
        
        # Get all table names
        result = connection.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"
        ))
        tables = [row[0] for row in result.fetchall()]
        
        for table in tables:
            try:
                connection.execute(text(f"DROP TABLE IF EXISTS {table};"))
                print(f"   ✓ {table}")
            except Exception as e:
                print(f"   ✗ Erro: {e}")
        
        connection.execute(text("PRAGMA foreign_keys=ON;"))
    
    # 2. CREATE ALL TABLES
    print("\n2️⃣  A criar tabelas novas...")
    Base.metadata.create_all(bind=engine)
    print("   ✓ Todas as tabelas criadas!")
    
    # 3. SEED DATA
    print("\n3️⃣  A preencher dados de teste...")
    from seed_data import run_seed
    run_seed()
    
    print("\n" + "=" * 60)
    print("✅ BASE DE DADOS INICIALIZADA COM SUCESSO!")
    print("=" * 60)

if __name__ == "__main__":
    init_database()
