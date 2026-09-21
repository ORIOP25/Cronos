from app.schemas import ClassConfigCreate


def test_class_config_accepts_explicit_name_for_imports_and_keeps_it_optional():
    named = ClassConfigCreate(
        name="10.º A",
        grade_level=10,
        size=25,
        start_year=2025,
        end_year=2028,
    )
    generated = ClassConfigCreate(grade_level=10, start_year=2025, end_year=2028)

    assert named.name == "10.º A"
    assert generated.name is None
