async def test_professor_can_read_status_but_cannot_mutate_scheduler(
    async_client,
    clerk_teacher_headers,
):
    status = await async_client.get(
        "/api/v1/scheduler/status",
        headers=clerk_teacher_headers,
    )
    assert status.status_code == 200

    requests = [
        await async_client.post(
            "/api/v1/scheduler/generate",
            json={},
            headers=clerk_teacher_headers,
        ),
        await async_client.post(
            "/api/v1/scheduler/jobs/1/cancel",
            headers=clerk_teacher_headers,
        ),
        await async_client.post(
            "/api/v1/scheduler/drafts/1/approve",
            headers=clerk_teacher_headers,
        ),
        await async_client.post(
            "/api/v1/scheduler/drafts/1/reject",
            headers=clerk_teacher_headers,
        ),
        await async_client.post(
            "/api/v1/scheduler/reset-year",
            json={"confirmed": True},
            headers=clerk_teacher_headers,
        ),
    ]

    assert [response.status_code for response in requests] == [403] * len(requests)
