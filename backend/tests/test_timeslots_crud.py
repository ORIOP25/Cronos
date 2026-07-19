# Ficheiro: backend/tests/test_timeslots_crud.py
"""
TESTES CRUD DE BLOCOS HORÁRIOS (Timeslots)
==========================================
Valida endpoints da API:
- POST /timeslots/generate (gerar em massa com configuração da escola)
- GET /timeslots/ (listar)
- Verificar contagem correta de slots gerados
"""

from httpx import AsyncClient

from app.config import settings

API = settings.API_V1_STR


class TestTimeslotsCRUD:
    # ---------- GENERATE (Bulk Create) ----------

    async def test_generate_timeslots_basic(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        """✅ Gerar timeslots com configuração mínima (2 dias, 50min slots, 10min intervalo)"""
        payload = {
            "start_time": "08:00",
            "end_time": "10:00",
            "slot_duration_minutes": 50,
            "break_duration_minutes": 10,
            "days_of_week": [0, 1],  # Seg + Ter
        }
        resp = await async_client.post(
            f"{API}/timeslots/generate", json=payload, headers=clerk_admin_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "message" in data
        # 08:00-08:50 (slot 1), 09:00-09:50 (slot 2) → 2 slots x 2 dias = 4
        assert "4" in data["message"]

    async def test_generate_timeslots_five_days(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        """✅ Gerar timeslots para semana completa (Seg-Sex)"""
        payload = {
            "start_time": "08:30",
            "end_time": "13:30",
            "slot_duration_minutes": 50,
            "break_duration_minutes": 10,
            "days_of_week": [0, 1, 2, 3, 4],
        }
        resp = await async_client.post(
            f"{API}/timeslots/generate", json=payload, headers=clerk_admin_headers
        )
        assert resp.status_code == 200
        # 08:30-09:20, 09:30-10:20, 10:30-11:20, 11:30-12:20, 12:30-13:20 → 5 slots x 5 dias = 25
        assert "25" in resp.json()["message"]

    async def test_generate_timeslots_replaces_existing(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        """✅ Gerar novos timeslots apaga os antigos (hard reset)"""
        base_payload = {
            "start_time": "08:00",
            "end_time": "09:00",
            "slot_duration_minutes": 50,
            "break_duration_minutes": 10,
            "days_of_week": [0],
        }
        # 1ª geração: 1 slot x 1 dia = 1
        await async_client.post(
            f"{API}/timeslots/generate", json=base_payload, headers=clerk_admin_headers
        )
        # 2ª geração: com 3 dias
        base_payload["days_of_week"] = [0, 1, 2]
        resp = await async_client.post(
            f"{API}/timeslots/generate", json=base_payload, headers=clerk_admin_headers
        )
        assert resp.status_code == 200
        # Verificar listagem: deve ter 3, não 4
        list_resp = await async_client.get(f"{API}/timeslots/", headers=clerk_admin_headers)
        assert len(list_resp.json()) == 3

    async def test_generate_timeslots_no_break(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        """✅ Gerar timeslots sem intervalo entre aulas"""
        payload = {
            "start_time": "08:00",
            "end_time": "10:00",
            "slot_duration_minutes": 60,
            "break_duration_minutes": 0,
            "days_of_week": [0],
        }
        resp = await async_client.post(
            f"{API}/timeslots/generate", json=payload, headers=clerk_admin_headers
        )
        assert resp.status_code == 200
        # 08:00-09:00, 09:00-10:00 → 2 slots x 1 dia = 2
        assert "2" in resp.json()["message"]

    async def test_generate_timeslots_missing_days_422(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        """❌ Falta days_of_week → 422"""
        payload = {
            "start_time": "08:00",
            "end_time": "10:00",
            "slot_duration_minutes": 50,
            "break_duration_minutes": 10,
        }
        resp = await async_client.post(
            f"{API}/timeslots/generate", json=payload, headers=clerk_admin_headers
        )
        assert resp.status_code == 422

    # ---------- READ ----------

    async def test_list_timeslots_empty(self, async_client: AsyncClient, clerk_admin_headers: dict):
        """✅ Listar timeslots quando não existem"""
        resp = await async_client.get(f"{API}/timeslots/", headers=clerk_admin_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_timeslots_after_generate(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        """✅ Listar timeslots devolvidos com campos corretos"""
        payload = {
            "start_time": "09:00",
            "end_time": "10:00",
            "slot_duration_minutes": 50,
            "break_duration_minutes": 10,
            "days_of_week": [2],  # Quarta
        }
        await async_client.post(
            f"{API}/timeslots/generate", json=payload, headers=clerk_admin_headers
        )
        resp = await async_client.get(f"{API}/timeslots/", headers=clerk_admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        slot = data[0]
        assert slot["day_of_week"] == 2
        assert "start_time" in slot
        assert "end_time" in slot
        assert "id" in slot
