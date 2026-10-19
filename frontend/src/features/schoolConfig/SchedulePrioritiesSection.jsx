import { useState } from 'react'
import { useOrganization } from '@clerk/react'
import { getApiErrorMessage } from '../../utils/apiErrors'
import {
  useSchedulePriorities,
  useUpdateSchedulePriorities,
} from './data'
import { SCHEDULE_PRIORITY_CRITERIA, SCHEDULE_PRIORITY_LEVELS } from './schedulePriorities'

export default function SchedulePrioritiesSection() {
  const { organization } = useOrganization()
  const prioritiesQuery = useSchedulePriorities()
  const updateMutation = useUpdateSchedulePriorities()
  const [draft, setDraft] = useState(null)
  const response = prioritiesQuery.data
  const levels = draft?.organizationId === organization?.id ? draft.levels : response?.levels

  const changeLevel = (key, value) => {
    updateMutation.reset()
    setDraft({
      organizationId: organization?.id,
      levels: { ...levels, [key]: value },
    })
  }

  const resetRecommended = () => {
    updateMutation.reset()
    setDraft({ organizationId: organization?.id, levels: response.defaults })
  }

  const save = () => updateMutation.mutate({ levels })

  if (prioritiesQuery.isLoading) {
    return <div className="d-flex justify-content-center p-5" role="status">A carregar prioridades…</div>
  }

  if (prioritiesQuery.isError) {
    return <div className="alert alert-danger" role="alert">
      {getApiErrorMessage(prioritiesQuery.error, 'Erro ao carregar prioridades do horário.')}
    </div>
  }

  if (!response || !levels) return null

  return (
    <section aria-labelledby="schedule-priorities-intro">
      <p id="schedule-priorities-intro" className="mb-4">
        Escolha a importância de cada critério. O Cronos equilibra-os segundo estes valores. As regras obrigatórias (Impossível, presença mínima, almoço, tipo de sala e datas do ano letivo) nunca se quebram.
      </p>

      <div className="d-flex flex-column gap-4">
        {SCHEDULE_PRIORITY_CRITERIA.map((criterion) => {
          const selectedLevel = levels[criterion.key]
          const recommendedLevel = response.defaults[criterion.key]
          const criterionId = `schedule-priority-${criterion.key}`

          return (
            <fieldset key={criterion.key} className="border rounded p-3" disabled={updateMutation.isPending}>
              <legend className="float-none w-auto px-2 fs-5 mb-2">{criterion.title}</legend>
              <p>{criterion.description}</p>
              <p className="mb-2"><strong>Ignorar:</strong> {criterion.lowest}</p>
              <p className="mb-3"><strong>Prioridade máxima:</strong> {criterion.highest}</p>
              <p className="small text-body-secondary">
                Nível recomendado: {SCHEDULE_PRIORITY_LEVELS[recommendedLevel]}
              </p>
              <div className="d-flex flex-wrap gap-2" role="radiogroup" aria-label={`Importância: ${criterion.title}`}>
                {SCHEDULE_PRIORITY_LEVELS.map((levelName, level) => {
                  const inputId = `${criterionId}-${level}`
                  const checked = selectedLevel === level
                  return (
                    <span key={level}>
                      <input
                        id={inputId}
                        className="btn-check"
                        type="radio"
                        name={criterionId}
                        value={level}
                        checked={checked}
                        aria-checked={checked}
                        onChange={() => changeLevel(criterion.key, level)}
                      />
                      <label className="btn btn-outline-primary" htmlFor={inputId}>{levelName}</label>
                    </span>
                  )
                })}
              </div>
            </fieldset>
          )
        })}
      </div>

      {updateMutation.isSuccess && (
        <div className="alert alert-success mt-4" role="status">
          Prioridades guardadas. A próxima geração ou atualização usa estes valores.
        </div>
      )}
      {updateMutation.isError && (
        <div className="alert alert-danger mt-4" role="alert">
          {getApiErrorMessage(updateMutation.error, 'Erro ao guardar prioridades do horário.')}
        </div>
      )}

      <div className="d-flex flex-wrap gap-2 mt-4">
        <button
          className="btn btn-primary"
          type="button"
          disabled={updateMutation.isPending}
          onClick={save}
        >
          Guardar prioridades
        </button>
        <button
          className="btn btn-outline-secondary"
          type="button"
          disabled={updateMutation.isPending}
          onClick={resetRecommended}
        >
          Repor valores recomendados
        </button>
      </div>
    </section>
  )
}
