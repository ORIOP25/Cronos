# Data and Seed

Esta secção documenta o único seed operacional atual.

## Seed operacional

`backend/seed_data.py` cria dados operacionais determinísticos, gera e aprova
um horário por tenant. É idempotente: pode ser executado repetidamente sem
duplicar dados.

Antes de executar, aplique as migrações:

`alembic upgrade head`

Para executar o seed, a partir de `backend`:

`python seed_data.py`

Para validar a idempotência:

`pytest tests/test_operational_seed.py -q`

Se ocorrer `UndefinedColumn`, atualize primeiro o schema com `alembic upgrade head`.
