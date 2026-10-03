export function createClassDraft(initialData = {}, currentYear = new Date().getFullYear()) {
  initialData ??= {}
  return {
    name: initialData.name ?? '',
    size: initialData.size ?? 25,
    grade_level: initialData.grade_level ?? 10,
    start_year: initialData.start_year ?? currentYear,
    end_year: initialData.end_year ?? currentYear + 3,
  }
}

export function validateClassDraft(draft, existingClasses = []) {
  const value = {
    name: String(draft.name).trim(),
    size: Number(draft.size),
    grade_level: Number(draft.grade_level),
    start_year: Number(draft.start_year),
    end_year: Number(draft.end_year),
  }

  if (!value.name) return { error: 'Indique o nome da turma.', field: 'name' }
  if (!Number.isInteger(value.size) || value.size < 1 || value.size > 100) {
    return { error: 'O número de alunos tem de estar entre 1 e 100.', field: 'size' }
  }
  if (!Number.isInteger(value.grade_level) || value.grade_level < 10 || value.grade_level > 12) {
    return { error: 'O ano tem de estar entre 10 e 12.', field: 'grade_level' }
  }
  if (!Number.isInteger(value.start_year) || value.start_year < 2000 || value.start_year > 2100) {
    return { error: 'O ano de início tem de estar entre 2000 e 2100.', field: 'start_year' }
  }
  if (!Number.isInteger(value.end_year) || value.end_year < 2000 || value.end_year > 2100) {
    return { error: 'O ano de fim tem de estar entre 2000 e 2100.', field: 'end_year' }
  }
  if (value.end_year <= value.start_year) {
    return { error: 'O ano de fim tem de ser posterior ao ano de início.', field: 'date_range' }
  }
  if (existingClasses.some((item) => item.name.trim().toLocaleLowerCase('pt-PT') === value.name.toLocaleLowerCase('pt-PT'))) {
    return { error: `A turma "${value.name}" já foi adicionada neste curso.`, field: 'name' }
  }
  return { value }
}
