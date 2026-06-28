import asyncio
import httpx
from app.main import app
from fastapi.testclient import TestClient

def test_endpoints():
    client = TestClient(app)
    
    # We need a valid token or bypass auth.
    # The easiest is to override deps.get_current_active_admin and deps.get_current_user
    from app.api import deps
    from app.models import User, UserRole
    
    dummy_user = User(
        id=1,
        organization_id=1,
        clerk_user_id="fake_user",
        email="fake@fake.com",
        role=UserRole.admin,
        is_active=True,
    )

    app.dependency_overrides[deps.get_current_active_admin] = lambda: dummy_user
    app.dependency_overrides[deps.get_current_user] = lambda: dummy_user

    print("Testing /api/v1/dashboard...")
    try:
        response = client.get("/api/v1/dashboard")
        print("Status Code:", response.status_code)
        if response.status_code == 500:
            print("Response:", response.text)
    except Exception as e:
        import traceback
        traceback.print_exc()

    print("\nTesting /api/v1/analytics/availability-heatmap...")
    try:
        response = client.get("/api/v1/analytics/availability-heatmap")
        print("Status Code:", response.status_code)
        if response.status_code == 500:
            print("Response:", response.text)
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_endpoints()
