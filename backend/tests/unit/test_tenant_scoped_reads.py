"""Leituras de resposta continuam a filtrar a escola, sem contar com o RLS.

I02: toda a consulta a uma tabela de escola filtra ``organization_id``, mesmo
com o RLS ativo. Estas consultas alimentam a resposta depois de uma escrita; sem
o predicado da escola leem a linha de outra escola que partilhe o identificador.
"""

import asyncio

from sqlalchemy.dialects import postgresql

from app.services import room_service, subject_service


class _CapturingSession:
    def __init__(self):
        self.statements = []

    async def scalar(self, statement):
        self.statements.append(statement)
        return None


def _sql(statement) -> str:
    return str(statement.compile(dialect=postgresql.dialect()))


def test_room_response_query_filters_the_school():
    db = _CapturingSession()
    asyncio.run(room_service._room_with_type(db, room_id=5, organization_id=9))

    sql = _sql(db.statements[0])
    assert "room.id = " in sql
    assert "room.organization_id = " in sql


def test_subject_response_query_filters_the_school():
    sql = _sql(subject_service._subject_response_stmt(subject_id=5, organization_id=9))

    assert "subject.id = " in sql
    assert "subject.organization_id = " in sql
