import { BreakTimelineEditor } from '../../timetable/BreakTimelineEditor'

export function BreakDurationStep({ values, fieldErrors, onChange }) {
  return (
    <BreakTimelineEditor
      values={values}
      fieldErrors={fieldErrors}
      onChange={onChange}
      title="5. Intervalos entre Blocos"
      description="Indique a duração padrão dos intervalos entre blocos de aulas consecutivos."
    />
  )
}
