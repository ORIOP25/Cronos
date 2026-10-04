import { useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { toast } from 'react-hot-toast'
import {
  CAlert,
  CBadge,
  CButton,
  CCard,
  CCardBody,
  CCardHeader,
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
  const [files, setFiles] = useState({})
  const [validation, setValidation] = useState(null)
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
    setLocalError('')
    setValidation(null)
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
    try {
      setValidation(await validateMutation.mutateAsync(files))
    } catch (error) {
      if (!attemptScope.isCurrent(attempt)) return
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

  const serverErrorContext = errorContext(validateMutation.error || commitMutation.error)
  const issues = validation?.issues || serverErrorContext.issues || []
  const errors = issues.filter((issue) => issue.severity === 'error')
  const warnings = issues.filter((issue) => issue.severity === 'warning')

  return (
    <div className="p-4">
      <PageHeader
        preTitle="Administração"
        title="Importar dados"
        description="Adicione várias salas, disciplinas, cursos, turmas e professores de uma só vez."
      />

      <section className="mb-4" aria-labelledby="import-steps-title">
        <h2 id="import-steps-title" className="h5">Como preparar os ficheiros</h2>
        <ol className="mb-2">
          <li>Descarregue o modelo da secção pretendida.</li>
          <li>Substitua a linha de exemplo sem alterar os títulos das colunas.</li>
          <li>Guarde como CSV, selecione o ficheiro e escolha “Verificar ficheiros”.</li>
        </ol>
        <p className="small text-muted mb-0">
          Pode utilizar Excel ou Google Sheets. São aceites ficheiros separados por vírgulas ou ponto e vírgula, até 1 MB cada.
        </p>
      </section>

      {localError && <div className="mb-3"><FeedbackBanner tone="warning">{localError}</FeedbackBanner></div>}

      <div className="row g-3">
        {IMPORT_RESOURCES.map((resource) => {
          const file = files[resource.key]
          return (
            <div className="col-12 col-xl-6" key={resource.key}>
              <CCard className="h-100">
                <CCardHeader className="d-flex justify-content-between align-items-center gap-2">
                  <span>{resource.label}</span>
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
                </CCardHeader>
                <CCardBody>
                  <ul className="small text-muted ps-3 mb-3">
                    {resource.instructions.map((instruction) => <li key={instruction}>{instruction}</li>)}
                  </ul>
                  <label className="form-label" htmlFor={`import-${resource.key}`}>
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
                </CCardBody>
              </CCard>
            </div>
          )
        })}
      </div>

      <div className="d-flex flex-wrap gap-2 align-items-center mt-4">
        <CButton
          color="primary"
          disabled={!Object.keys(files).length || validateMutation.isPending || commitMutation.isPending}
          onClick={() => void validate()}
        >
          {validateMutation.isPending ? <><CSpinner size="sm" className="me-2" />A verificar…</> : 'Verificar ficheiros'}
        </CButton>
        <CButton color="success" disabled={!validation?.can_commit || commitMutation.isPending} onClick={() => void commit()}>
          {commitMutation.isPending ? <><CSpinner size="sm" className="me-2" />A importar…</> : 'Confirmar importação'}
        </CButton>
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
        </section>
      )}
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
