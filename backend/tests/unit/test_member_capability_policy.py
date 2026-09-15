import pytest

from app import models
from app.core.exceptions import AppError
from app.services.member_service import _normalize_capability_policy


@pytest.mark.parametrize(
    ("capabilities", "mode", "expected_role"),
    [
        ({models.MembershipCapability.admin}, None, models.ClerkOrganizationRole.admin),
        (
            {models.MembershipCapability.teacher},
            models.TeacherAccessMode.platform,
            models.ClerkOrganizationRole.member,
        ),
        ({models.MembershipCapability.teacher}, models.TeacherAccessMode.scheduler_only, None),
    ],
)
def test_capability_policy_normalizes_supported_access_modes(capabilities, mode, expected_role):
    normalized, normalized_mode, role = _normalize_capability_policy(capabilities, mode)

    assert normalized == capabilities
    assert normalized_mode == mode
    assert role == expected_role


@pytest.mark.parametrize(
    ("capabilities", "mode"),
    [
        ({models.MembershipCapability.teacher}, None),
        ({models.MembershipCapability.admin}, models.TeacherAccessMode.scheduler_only),
        (set(), models.TeacherAccessMode.platform),
    ],
)
def test_capability_policy_rejects_invalid_combinations(capabilities, mode):
    with pytest.raises(AppError) as raised:
        _normalize_capability_policy(capabilities, mode)

    assert raised.value.kind == "validation"
    assert raised.value.code == "validation_error"


def test_capability_policy_rejects_platform_access_during_accessless_restore():
    with pytest.raises(AppError):
        _normalize_capability_policy(
            {models.MembershipCapability.admin},
            None,
            allow_platform_access=False,
        )
