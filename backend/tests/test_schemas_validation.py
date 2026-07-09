"""
TESTES DE VALIDAÇÃO DE SCHEMAS
==============================
Valida regras de negócio em Pydantic schemas.

4º Pilar - Security: Garantir que dados inválidos são rejeitados na camada de validação
"""

import pytest
from pydantic import ValidationError
from app.schemas import (
    ClassCreateInCourse,
    ClassUpdateInCourse,
    CourseUpdate,
    MemberCreate,
    RoomCreate,
    RoomUpdate,
    OrganizationSettingsUpsert,
    OnboardingRequest,
    ScheduleGenerateRequest,
    SubjectCreate,
    SubjectUpdate,
)
from app.models import RoomType


class TestSchedulerBaselineContract:
    def test_generate_request_rejects_public_mode_selection(self):
        with pytest.raises(ValidationError):
            ScheduleGenerateRequest(mode="repair")

    def test_settings_reject_target_end_date_and_accept_zero_stability_window(self):
        with pytest.raises(ValidationError):
            OrganizationSettingsUpsert(
                school_start_date="2025-09-15",
                school_target_end_date="2026-06-15",
                school_hard_end_date="2026-07-31",
            )

        settings = OrganizationSettingsUpsert(
            school_start_date="2025-09-15",
            school_hard_end_date="2026-07-31",
            repair_stability_window_days=0,
        )
        assert settings.repair_stability_window_days == 0

    def test_onboarding_rejects_target_end_date(self):
        with pytest.raises(ValidationError):
            OnboardingRequest(
                school_start_date="2025-09-15",
                school_target_end_date="2026-06-15",
                school_hard_end_date="2026-07-31",
                lunch_start="12:30",
                lunch_end="14:00",
                lunch_min_duration=60,
            )


class TestSubjectCreateValidation:
    """Testes de validação do SubjectCreate"""
    
    def test_subject_with_sequential_modules_valid(self):
        """✅ Subject com módulos sequenciais [0, 1, 2] deve ser aceite"""
        subject_data = {
            "name": "Programação",
            "required_room_type": RoomType.lab,
            "modules": [
                {"name": "Python Básico", "code": "P001", "hours_total": 40, "order": 0},
                {"name": "Python Avançado", "code": "P002", "hours_total": 40, "order": 1},
                {"name": "Projetos", "code": "P003", "hours_total": 20, "order": 2},
            ]
        }
        
        subject = SubjectCreate(**subject_data)
        
        assert subject.name == "Programação"
        assert len(subject.modules) == 3
        assert [m.order for m in subject.modules] == [0, 1, 2]
    
    def test_subject_without_modules_valid(self):
        """✅ Subject sem módulos deve ser aceite (criados depois)"""
        subject_data = {
            "name": "Matemática",
            "required_room_type": RoomType.normal,
        }
        
        subject = SubjectCreate(**subject_data)
        
        assert subject.name == "Matemática"
        assert len(subject.modules) == 0
    
    def test_subject_with_gaps_in_module_order_invalid(self):
        """❌ Subject com ordem [0, 2, 4] deve ser rejeitado"""
        subject_data = {
            "name": "Programação",
            "required_room_type": RoomType.lab,
            "modules": [
                {"name": "Python Básico", "code": "P001", "hours_total": 40, "order": 0},
                {"name": "Python Avançado", "code": "P002", "hours_total": 40, "order": 2},
                {"name": "Projetos", "code": "P003", "hours_total": 20, "order": 4},
            ]
        }
        
        with pytest.raises(ValidationError) as exc_info:
            SubjectCreate(**subject_data)
        
        # Verificar que a mensagem menciona ordem sequencial
        error_msg = str(exc_info.value)
        assert "sequencial" in error_msg.lower() or "sequential" in error_msg.lower()
        assert "[0, 1, 2]" in error_msg
        assert "[0, 2, 4]" in error_msg
    
    def test_subject_with_out_of_order_modules_accepted_and_ordered(self):
        """✅ Subject com módulos fora de ordem [1, 0, 2] é aceite pois o schema reordena"""
        subject_data = {
            "name": "Programação",
            "required_room_type": RoomType.lab,
            "modules": [
                {"name": "Python Avançado", "code": "P002", "hours_total": 40, "order": 1},
                {"name": "Python Básico", "code": "P001", "hours_total": 40, "order": 0},
                {"name": "Projetos", "code": "P003", "hours_total": 20, "order": 2},
            ]
        }

        subject = SubjectCreate(**subject_data)

        assert len(subject.modules) == 3
        assert {m.order for m in subject.modules} == {0, 1, 2}
    
    def test_subject_with_duplicate_order_invalid(self):
        """❌ Subject com ordem duplicada [0, 0, 1] deve ser rejeitado"""
        subject_data = {
            "name": "Programação",
            "required_room_type": RoomType.lab,
            "modules": [
                {"name": "Python Básico A", "code": "P001", "hours_total": 40, "order": 0},
                {"name": "Python Básico B", "code": "P002", "hours_total": 40, "order": 0},
                {"name": "Python Avançado", "code": "P003", "hours_total": 20, "order": 1},
            ]
        }
        
        with pytest.raises(ValidationError) as exc_info:
            SubjectCreate(**subject_data)
        
        error_msg = str(exc_info.value)
        assert "sequencial" in error_msg.lower() or "sequential" in error_msg.lower()
    
    def test_subject_with_zero_order_invalid(self):
        """❌ Ordem começando em 1 em vez de 0 deve ser rejeitada"""
        subject_data = {
            "name": "Programação",
            "required_room_type": RoomType.lab,
            "modules": [
                {"name": "Python Básico", "code": "P001", "hours_total": 40, "order": 1},
                {"name": "Python Avançado", "code": "P002", "hours_total": 40, "order": 2},
            ]
        }
        
        with pytest.raises(ValidationError) as exc_info:
            SubjectCreate(**subject_data)
        
        # Erro: esperava [0, 1], recebeu [1, 2]
        error_msg = str(exc_info.value)
        assert "come\u00e7ando em 0" in error_msg.lower() or "0, 1" in error_msg
    
    def test_subject_single_module_valid(self):
        """✅ Subject com um módulo (order=0) deve ser aceite"""
        subject_data = {
            "name": "Iniciação",
            "required_room_type": RoomType.normal,
            "modules": [
                {"name": "Aula 1", "code": "A001", "hours_total": 20, "order": 0},
            ]
        }
        
        subject = SubjectCreate(**subject_data)
        
        assert len(subject.modules) == 1
        assert subject.modules[0].order == 0
    
    def test_subject_order_must_start_at_zero(self):
        """❌ Ordem DEVE começar em 0, não em 5 ou 32"""
        subject_data = {
            "name": "Programação",
            "required_room_type": RoomType.lab,
            "modules": [
                {"name": "Python Básico", "code": "P001", "hours_total": 40, "order": 5},
                {"name": "Python Avançado", "code": "P002", "hours_total": 40, "order": 6},
            ]
        }
        
        with pytest.raises(ValidationError) as exc_info:
            SubjectCreate(**subject_data)
        
        error_msg = str(exc_info.value)
        assert "[0, 1]" in error_msg
        assert "[5, 6]" in error_msg


class TestSubjectUpdateValidation:
    def test_subject_update_without_modules_is_valid(self):
        subject = SubjectUpdate(name="Nova disciplina")

        assert subject.name == "Nova disciplina"
        assert subject.modules is None

    def test_subject_update_accepts_sequential_modules(self):
        subject = SubjectUpdate(
            modules=[
                {"id": 1, "name": "M1", "code": "P001", "hours_total": 20, "order": 0},
                {"name": "M2", "code": "P002", "hours_total": 30, "order": 1},
            ]
        )

        assert [module.order for module in subject.modules] == [0, 1]

    def test_subject_update_rejects_gap_in_module_order(self):
        with pytest.raises(ValidationError) as exc_info:
            SubjectUpdate(
                modules=[
                    {"id": 1, "name": "M1", "code": "P001", "hours_total": 20, "order": 0},
                    {"name": "M2", "code": "P002", "hours_total": 30, "order": 2},
                ]
            )

        assert "[0, 1]" in str(exc_info.value)
        assert "[0, 2]" in str(exc_info.value)


class TestClassInCourseValidation:
    def test_class_create_rejects_invalid_year_window(self):
        with pytest.raises(ValidationError):
            ClassCreateInCourse(
                name="TGPSI 10A",
                size=25,
                grade_level=10,
                start_year=2028,
                end_year=2028,
            )

    def test_class_update_accepts_partial_year_fields(self):
        schema = ClassUpdateInCourse(start_year=2027)
        assert schema.start_year == 2027
        assert schema.end_year is None

    def test_class_update_rejects_invalid_year_window_when_both_present(self):
        with pytest.raises(ValidationError):
            ClassUpdateInCourse(start_year=2029, end_year=2028)


class TestRoomValidation:
    def test_room_create_accepts_positive_capacity(self):
        room = RoomCreate(name="Lab 1", type=RoomType.lab, capacity=1)

        assert room.capacity == 1

    @pytest.mark.parametrize("capacity", [0, -1])
    def test_room_create_rejects_non_positive_capacity(self, capacity):
        with pytest.raises(ValidationError):
            RoomCreate(name="Lab 1", type=RoomType.lab, capacity=capacity)

    @pytest.mark.parametrize("capacity", [0, -5])
    def test_room_update_rejects_non_positive_capacity(self, capacity):
        with pytest.raises(ValidationError):
            RoomUpdate(capacity=capacity)


class TestCourseUpdateValidation:
    @pytest.mark.parametrize("abbreviation", ["AI", "TGEI", "LONGTENCHR"])
    def test_course_update_accepts_valid_abbreviation_length(self, abbreviation):
        course = CourseUpdate(abbreviation=abbreviation)

        assert course.abbreviation == abbreviation

    @pytest.mark.parametrize("abbreviation", ["A", "TOO-LONG-CODE"])
    def test_course_update_rejects_invalid_abbreviation_length(self, abbreviation):
        with pytest.raises(ValidationError):
            CourseUpdate(abbreviation=abbreviation)


@pytest.mark.unit
class TestMemberValidationMessages:
    @pytest.mark.parametrize(
        ("capabilities", "teacher_access_mode", "expected_message"),
        [
            (["teacher"], None, "teacher_access_mode é obrigatório para professores"),
            (["admin"], "platform", "teacher_access_mode só pode ser usado para professores"),
            (["admin", "teacher"], "scheduler_only", "Administrador requer acesso à plataforma"),
        ],
    )
    def test_member_shape_errors_use_readable_portuguese(
        self,
        capabilities,
        teacher_access_mode,
        expected_message,
    ):
        with pytest.raises(ValidationError, match=expected_message):
            MemberCreate(
                organization_display_name="Professor Exemplo",
                email="professor@example.pt",
                capabilities=capabilities,
                teacher_access_mode=teacher_access_mode,
            )
