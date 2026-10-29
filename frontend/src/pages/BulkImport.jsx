import { useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { toast } from 'react-hot-toast'
import {
  CAlert,
  CBadge,
  CButton,
  CFormInput,
  CSpinner,
} from '@coreui/react'
import FeedbackBanner from '../components/FeedbackBanner'
import PageHeader from '../components/PageHeader'
import { useApiClient } from '../ApiClientContext'
import { useAttemptScope } from '../hooks/useAttemptScope'
import { getApiErrorMessage } from '../utils/apiErrors'
import {
  createBulkImportReport,
  downloadBlob,
  downloadBulkImportTemplate,
  formatImportIssue,
  getImportCountLabel,
  IMPORT_RESOURCES,
  useCommitBulkImport,
  useValidateBulkImport,
} from '../features/imports/data'

function formatMegabytes(bytes) {
  return `${(bytes / 1_000_000).toFixed(2)} MB`
}

function changedBlocksLabel(changedBlocks) {
  return changedBlocks || 'Sem alterações'
}

const CLASS_AVAILABILITY_COLUMNS = [
  { header: 'Sigla do curso', value: (item) => item.course_abbreviation },
  { header: 'Nome da turma', value: (item) => item.class_name },
  { header: 'Blocos que mudam', value: (item) => changedBlocksLabel(item.changed_blocks) },
]

const TEACHER_AVAILABILITY_COLUMNS = [
  { header: 'Nome do professor', value: (item) => item.teacher_name },
  { header: 'Email do professor', value: (item) => item.teacher_email },
  { header: 'Blocos que mudam', value: (item) => changedBlocksLabel(item.changed_blocks) },
]

function errorContext(error) {
  return error?.response?.data?.detail?.context || {}
}

const BulkImport = () => {
  const location = useLocation()
  const navigate = useNavigate()
  const apiClient = useApiClient()
  const initialResource = useMemo(() => {
    const candidate = new URLSearchParams(location.search).get('resource')
    return IMPORT_RESOURCES.some((item) => item.key === candidate) ? candidate : 'rooms'
  }, [location.search])
  const initialInput = useRef(null)
  const validationVersion = useRef(0)
  const [files, setFiles] = useState({})
  const [validation, setValidation] = useState(null)
  const [validationError, setValidationError] = useState(null)
  const [localError, setLocalError] = useState('')
  const [downloadingResource, setDownloadingResource] = useState('')
  const validateMutation = useValidateBulkImport()
  const commitMutation = useCommitBulkImport()
  const attemptScope = useAttemptScope()

  const downloadTemplate = async (resourceKey) => {
    if (downloadingResource) return
    setLocalError('')
    setDownloadingResource(resourceKey)
    const attempt = attemptScope.capture()
    try {
      await downloadBulkImportTemplate(apiClient, resourceKey)
      if (!attemptScope.isCurrent(attempt)) return
      toast.success('Transferência iniciada. Verifique a pasta de transferências.')
    } catch (error) {
      if (!attemptScope.isCurrent(attempt)) return
      toast.error(getApiErrorMessage(error, 'Não foi possível preparar o modelo.'))
    } finally {
      setDownloadingResource('')
    }
  }

  useEffect(() => {
    initialInput.current?.focus()
  }, [])

  const selectFile = (resource, file) => {
    validationVersion.current += 1
    setLocalError('')
    setValidation(null)
    setValidationError(null)
    if (!file) document.getElementById(`import-${resource}`).value = ''
    setFiles((current) => {
      const next = { ...current }
      if (file) next[resource] = file
      else delete next[resource]
      return next
    })
  }

  const validate = async () => {
    if (!Object.keys(files).length) {
      setLocalError('Selecione pelo menos um ficheiro CSV.')
      return
    }
    setLocalError('')
    const attempt = attemptScope.capture()
    const version = ++validationVersion.current
    setValidation(null)
    setValidationError(null)
    try {
      const result = await validateMutation.mutateAsync(files)
      if (!attemptScope.isCurrent(attempt) || version !== validationVersion.current) return
      setValidation(result)
    } catch (error) {
      if (!attemptScope.isCurrent(attempt) || version !== validationVersion.current) return
      setValidationError(error)
      toast.error(getApiErrorMessage(error, 'Não foi possível verificar os ficheiros. Tente novamente.'))
    }
  }

  const commit = async () => {
    if (!validation?.can_commit) return
    const attempt = attemptScope.capture()
    try {
      await commitMutation.mutateAsync(files)
      if (!attemptScope.isCurrent(attempt)) return
      toast.success('Importação concluída.')
      const origin = IMPORT_RESOURCES.find((item) => item.key === initialResource)?.origin || '/courses'
      navigate(origin)
    } catch (error) {
      if (!attemptScope.isCurrent(attempt)) return
      toast.error(getApiErrorMessage(error, 'Não foi possível concluir a importação. Tente novamente.'))
    }
  }

  const serverErrorContext = errorContext(validationError || commitMutation.error)
  const issues = validation?.issues || serverErrorContext.issues || []
  const errors = issues.filter((issue) => issue.severity === 'error')
  const warnings = issues.filter((issue) => issue.severity === 'warning')
  const newRoomTypes = (validation?.preview?.items || [])
    .filter((item) => item.resource === 'room_types')
    .map((item) => item.name)
  const classAvailabilityPreview = (validation?.preview?.items || []).filter(
    (item) => item.resource === 'class_availability',
  )
  const teacherAvailabilityPreview = (validation?.preview?.items || []).filter(
    (item) => item.resource === 'teacher_availability',
  )

  return (
    <div className="p-4">
      <PageHeader
        title="Importar dados"
        description="Descarregue um modelo, preencha e escolha os ficheiros a importar."
      />

      <details className="context-details mb-4">
        <summary>Como preparar os ficheiros</summary>
        <ol className="mb-2">
          <li>Descarregue o modelo da secção pretendida.</li>
          <li>Preencha as linhas sem alterar os títulos das colunas.</li>
          <li>Guarde como CSV, selecione o ficheiro e escolha “Verificar ficheiros”.</li>
        </ol>
        <p className="small text-muted mb-0">
          Pode utilizar Excel ou Google Sheets. São aceites ficheiros separados por vírgulas ou ponto e vírgula, até 1 MB cada.
        </p>
      </details>

      {localError && <div className="mb-3"><FeedbackBanner tone="warning">{localError}</FeedbackBanner></div>}

      <section className="import-resources" aria-label="Ficheiros a importar">
        {IMPORT_RESOURCES.map((resource) => {
          const file = files[resource.key]
          return (
            <div className="import-resource" key={resource.key}>
                <div className="import-resource__heading">
                  <h2 className="h6 mb-0">{resource.label}</h2>
                  <CButton
                    color="link"
                    size="sm"
                    disabled={Boolean(downloadingResource)}
                    onClick={() => void downloadTemplate(resource.key)}
                  >
                    {downloadingResource === resource.key ? (
                      <><CSpinner size="sm" className="me-1" />A preparar…</>
                    ) : (
                      'Descarregar modelo'
                    )}
                  </CButton>
                </div>
                <div className="import-resource__file">
                  <label className="visually-hidden" htmlFor={`import-${resource.key}`}>
                    Selecionar ficheiro CSV de {resource.label.toLowerCase()}
                  </label>
                  <CFormInput
                    ref={resource.key === initialResource ? initialInput : undefined}
                    id={`import-${resource.key}`}
                    type="file"
                    accept=".csv,text/csv"
                    onChange={(event) => selectFile(resource.key, event.target.files?.[0])}
                  />
                  {file && (
                    <div className="d-flex align-items-center justify-content-between mt-2 small">
                      <span>{file.name} · {formatMegabytes(file.size)}</span>
                      <CButton color="link" size="sm" onClick={() => selectFile(resource.key, null)}>
                        Remover
                      </CButton>
                    </div>
                  )}
                </div>
                <details className="context-details import-resource__guidance">
                  <summary>Como preencher</summary>
                  <ul className="small text-muted ps-3 mt-2 mb-0">
                    {resource.instructions.map((instruction) => <li key={instruction}>{instruction}</li>)}
                  </ul>
                </details>
            </div>
          )
        })}
      </section>

      <div className="d-flex flex-wrap gap-2 align-items-center mt-4">
        <CButton
          color="primary"
          disabled={!Object.keys(files).length || validateMutation.isPending || commitMutation.isPending}
          onClick={() => void validate()}
        >
          {validateMutation.isPending ? <><CSpinner size="sm" className="me-2" />A verificar…</> : 'Verificar ficheiros'}
        </CButton>
        {validation?.can_commit && <CButton color="primary" disabled={validateMutation.isPending || commitMutation.isPending} onClick={() => void commit()}>
          {commitMutation.isPending ? <><CSpinner size="sm" className="me-2" />A importar…</> : 'Confirmar importação'}
        </CButton>}
        {issues.length > 0 && (
          <CButton
            color="secondary"
            variant="outline"
            onClick={() => downloadBlob(createBulkImportReport(issues), 'Cronos_Relatorio_Importacao.csv')}
          >
            Descarregar relatório
          </CButton>
        )}
      </div>

      {validation && (
        <section className="mt-4" aria-live="polite" aria-labelledby="import-result-title">
          <h2 id="import-result-title" className="h5">Resultado da verificação</h2>
          <div className="d-flex flex-wrap gap-2 mb-3">
            {Object.entries(validation.preview?.counts || {}).map(([key, value]) => (
              <CBadge color="info" key={key}>{getImportCountLabel(key)}: {value}</CBadge>
            ))}
            <CBadge color={errors.length ? 'danger' : 'success'}>
              {errors.length ? `${errors.length} erros` : 'Sem erros'}
            </CBadge>
            {warnings.length > 0 && <CBadge color="warning">{warnings.length} avisos</CBadge>}
          </div>
          {errors.length > 0 && (
            <CAlert color="danger">
              <strong>Corrija estes problemas antes de importar</strong>
              <IssueList issues={errors} />
            </CAlert>
          )}
          {warnings.length > 0 && (
            <CAlert color="warning">
              <strong>Pode importar, mas tenha atenção a estes avisos</strong>
              <IssueList issues={warnings} />
            </CAlert>
          )}
          {newRoomTypes.length > 0 && (
            <div className="mt-3">
              <p className="mb-1 fw-semibold">Tipos de sala novos</p>
              <ul aria-label="Tipos de sala novos" className="mb-0">
                {newRoomTypes.map((name) => <li key={name}>{name}</li>)}
              </ul>
            </div>
          )}
          {classAvailabilityPreview.length > 0 && (
            <AvailabilityPreviewTable
              caption="Disponibilidade das turmas por turma"
              columns={CLASS_AVAILABILITY_COLUMNS}
              items={classAvailabilityPreview}
              rowKey={(item) => `${item.course_abbreviation}-${item.class_name}`}
            />
          )}
          {teacherAvailabilityPreview.length > 0 && (
            <AvailabilityPreviewTable
              caption="Disponibilidade dos professores por professor"
              columns={TEACHER_AVAILABILITY_COLUMNS}
              items={teacherAvailabilityPreview}
              rowKey={(item) => item.teacher_email}
            />
          )}
        </section>
      )}
    </div>
  )
}

function AvailabilityPreviewTable({ caption, columns, items, rowKey }) {
  return (
    <div className="table-responsive mt-3">
      <table className="table table-sm mb-0">
        <caption className="small text-muted">{caption}</caption>
        <thead>
          <tr>
            {columns.map((column) => <th scope="col" key={column.header}>{column.header}</th>)}
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={rowKey(item)}>
              {columns.map((column) => <td key={column.header}>{column.value(item)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function IssueList({ issues }) {
  return (
    <ul className="mb-0 mt-2">
      {issues.map((issue, index) => <li key={`${issue.code}-${issue.line}-${index}`}>{formatImportIssue(issue)}</li>)}
    </ul>
  )
}

export default BulkImport
