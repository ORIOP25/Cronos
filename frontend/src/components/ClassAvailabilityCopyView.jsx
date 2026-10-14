import { useMemo } from 'react'
import { CFormCheck } from '@coreui/react'
import StatePanel from './StatePanel'
import { useClasses, useCourses } from '../features/catalog/data'

/**
 * Lista de turmas de destino para "Aplicar a outras turmas…".
 * Agrupa por curso, ordena por nome e omite a turma de origem e as arquivadas.
 */
const ClassAvailabilityCopyView = ({ originClassId, selectedIds, onToggle }) => {
  const classesQuery = useClasses()
  const coursesQuery = useCourses()
  const classes = useMemo(() => classesQuery.data ?? [], [classesQuery.data])
  const courses = useMemo(() => coursesQuery.data ?? [], [coursesQuery.data])
  const courseById = useMemo(() => new Map(courses.map((course) => [course.id, course])), [courses])

  const groups = useMemo(() => {
    const byCourse = new Map()
    for (const item of classes) {
      if (item.id === originClassId || item.is_archived) continue
      const key = item.course_id ?? 0
      if (!byCourse.has(key)) byCourse.set(key, [])
      byCourse.get(key).push(item)
    }
    return [...byCourse.entries()]
      .map(([courseId, items]) => ({
        courseId,
        label: courseById.get(courseId)?.abbreviation
          || courseById.get(courseId)?.name
          || `Curso ${courseId}`,
        items: [...items].sort((left, right) => left.name.localeCompare(right.name)),
      }))
      .sort((left, right) => left.label.localeCompare(right.label))
  }, [classes, courseById, originClassId])

  if (classesQuery.isLoading || coursesQuery.isLoading) {
    return <StatePanel state="loading" title="A carregar turmas" compact />
  }
  if (classesQuery.error || coursesQuery.error) {
    return (
      <StatePanel
        state="error"
        title="Não foi possível carregar as turmas"
        description="Verifique a ligação e tente novamente."
        compact
      />
    )
  }
  if (!groups.length) {
    return (
      <StatePanel
        state="empty"
        title="Sem outras turmas"
        description="Não há turmas disponíveis para receber esta grelha."
        compact
      />
    )
  }

  return (
    <div>
      {groups.map((group) => (
        <fieldset key={group.courseId} className="border rounded p-3 mb-3">
          <legend className="fs-6 fw-semibold">{group.label}</legend>
          {group.items.map((item) => (
            <CFormCheck
              key={item.id}
              id={`class-availability-target-${item.id}`}
              label={item.name}
              checked={selectedIds.includes(item.id)}
              onChange={() => onToggle(item.id)}
            />
          ))}
        </fieldset>
      ))}
    </div>
  )
}

export default ClassAvailabilityCopyView
