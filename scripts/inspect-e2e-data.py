"""Inspect owner-supplied CSV bytes independently of the application parser."""

import csv
import hashlib
import io
import json
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

FILES = {
    "rooms": ("Folha de cálculo sem nome - Cronos_Salas_Template_Maior.csv", ",", 48),
    "teachers": ("Cronos_ProfessoresECompetencias_Template_Maior.csv", ";", 72),
    "subjects": ("Cronos_DisciplinasEModulos_Template_Maior.csv", ";", 208),
    "courses": ("Cronos_CursosETurmas_Template_Maior.csv", ";", 48),
    "assignments": ("Cronos_Atribuicoes_Template_Maior.csv", ";", 336),
}


def minutes(hours):
    try:
        value = Decimal(hours.replace(",", ".")) * 60
        if not value.is_finite() or value <= 0 or value != value.to_integral_value():
            raise ValueError("Module minutes must be positive and integral")
        return int(value)
    except InvalidOperation as error:
        raise ValueError("Invalid module hours") from error


def inspect(directory):
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8-sig"))
    if manifest.get("schema_version") != 1 or set(manifest.get("files", {})) != {
        item[0] for item in FILES.values()
    }:
        raise ValueError("Invalid original data manifest")
    resources = {}
    for resource, (name, delimiter, count) in FILES.items():
        raw = (directory / name).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if manifest["files"][name] != {"bytes": len(raw), "sha256": digest}:
            raise ValueError(f"Original data integrity failed: {name}")
        reader = csv.DictReader(
            io.StringIO(raw.decode("utf-8-sig")), delimiter=delimiter, strict=True
        )
        rows = list(reader)
        if len(rows) != count or any(
            None in row
            or any(value is None or not value.strip() for value in row.values())
            for row in rows
        ):
            raise ValueError(f"Incomplete original CSV: {name}")
        resources[resource] = rows
    subjects = {}
    for row in resources["subjects"]:
        name = row["Nome da disciplina"]
        subject = subjects.setdefault(
            name, {"room_type": row["Tipo de sala"], "modules": []}
        )
        if subject["room_type"] != row["Tipo de sala"]:
            raise ValueError("Inconsistent subject room type")
        subject["modules"].append(
            {
                "code": row["Código do módulo"],
                "order": int(row["Ordem do módulo"]),
                "minutes": minutes(row["Horas do módulo"]),
            }
        )
    for subject in subjects.values():
        if (
            sorted(module["order"] for module in subject["modules"]) != [1, 2, 3, 4]
            or len({module["code"] for module in subject["modules"]}) != 4
        ):
            raise ValueError("Incomplete or duplicate subject modules")
    teachers = {}
    for row in resources["teachers"]:
        email = row["Email do professor"]
        subject = row["Nome da disciplina"]
        if subject not in subjects:
            raise ValueError("Unknown teacher competency")
        teacher = teachers.setdefault(
            email, {"name": row["Nome do professor"], "subjects": []}
        )
        if (
            teacher["name"] != row["Nome do professor"]
            or subject in teacher["subjects"]
        ):
            raise ValueError("Conflicting teacher identity or duplicate competency")
        teacher["subjects"].append(subject)
    classes = {}
    for row in resources["courses"]:
        key = (row["Sigla do curso"], row["Nome da turma"])
        if key in classes:
            raise ValueError("Duplicate class")
        classes[key] = row
    demand = []
    seen = set()
    for row in resources["assignments"]:
        course, class_name, subject, email = (
            row[field]
            for field in [
                "Sigla do curso",
                "Nome da turma",
                "Nome da disciplina",
                "Email do professor",
            ]
        )
        key = (course, class_name, subject)
        if (
            (course, class_name) not in classes
            or subject not in subjects
            or email not in teachers
            or subject not in teachers[email]["subjects"]
        ):
            raise ValueError("Unknown assignment reference or competency")
        if key in seen:
            raise ValueError("Duplicate class/subject assignment")
        seen.add(key)
        demand.append(
            {
                "course": course,
                "class": class_name,
                "subject": subject,
                "teacher": email,
                "minutes": sum(
                    module["minutes"] for module in subjects[subject]["modules"]
                ),
            }
        )
    counts = {
        "rooms": len(resources["rooms"]),
        "teachers": len(teachers),
        "subjects": len(subjects),
        "modules": sum(len(item["modules"]) for item in subjects.values()),
        "classes": len(classes),
        "courses": len({key[0] for key in classes}),
        "assignments": len(demand),
    }
    if counts != {
        "rooms": 48,
        "teachers": 40,
        "subjects": 52,
        "modules": 208,
        "classes": 48,
        "courses": 16,
        "assignments": 336,
    }:
        raise ValueError("Original entity counts do not match the agreed data")
    if len({row["Nome da sala"] for row in resources["rooms"]}) != counts[
        "rooms"
    ] or any(int(row["Capacidade"]) <= 0 for row in resources["rooms"]):
        raise ValueError("Invalid or duplicate room")
    return {
        "schema_version": 1,
        "files": manifest["files"],
        "counts": counts,
        "subjects": subjects,
        "rooms": {
            row["Nome da sala"]: {
                "type": row["Tipo de sala"],
                "capacity": int(row["Capacidade"]),
            }
            for row in resources["rooms"]
        },
        "classes": [
            {"course": course, "class": name, "size": int(row["Número de alunos"])}
            for (course, name), row in classes.items()
        ],
        "teachers": teachers,
        "demand": demand,
        "required_minutes": sum(item["minutes"] for item in demand),
    }


if __name__ == "__main__":
    result = inspect(
        sys.argv[1]
        if len(sys.argv) > 1
        else Path(__file__).resolve().parents[1] / "frontend/e2e/data/originals"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
