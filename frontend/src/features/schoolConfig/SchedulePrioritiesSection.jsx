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
      <h2 id="schedule-priorities-intro" className="h5">O que valoriza num horário?</h2>
      <p className="text-body-secondary">Ajuste os níveis e guarde. As regras obrigatórias mantêm-se sempre.</p>
      <details className="context-details mb-4">
      <summary>Como são usadas estas prioridades?</summary>
      <p className="mt-2">
        Escolha a importância de cada critério. O Cronos equilibra-os segundo estes valores. As regras obrigatórias (Impossível, presença mínima, almoço, tipo de sala e datas do ano letivo) nunca se quebram. O Cronos acaba sempre os módulos o mais cedo possível, para deixar margem para recuperar faltas e ocorrências. Os critérios abaixo decidem como, e alguns podem atrasar o fim do ano.
      </p>
      </details>

      <div className="priority-list">
        {SCHEDULE_PRIORITY_CRITERIA.map((criterion) => {
          const selectedLevel = levels[criterion.key]
          const recommendedLevel = response.defaults[criterion.key]
          const criterionId = `schedule-priority-${criterion.key}`

          return (
            <fieldset key={criterion.key} className="priority-row" disabled={updateMutation.isPending}>
              <legend className="float-none w-auto fs-6 fw-semibold mb-2">{criterion.title}</legend>
              <div className="priority-levels" role="radiogroup" aria-label={`Importância: ${criterion.title}`}>
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
              <details className="context-details mt-2">
                <summary>O que muda?</summary>
                <p className="mt-2">{criterion.description}</p>
                <p className="mb-2"><strong>Ignorar:</strong> {criterion.lowest}</p>
                <p className="mb-3"><strong>Prioridade máxima:</strong> {criterion.highest}</p>
                {criterion.warning && <p className="small text-body-secondary">Atenção: {criterion.warning}</p>}
                <p className="small text-body-secondary">Nível recomendado: {SCHEDULE_PRIORITY_LEVELS[recommendedLevel]}</p>
              </details>
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
