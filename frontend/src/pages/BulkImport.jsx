import { useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
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
import PageHeader from '../components/PageHeader'
import { useApiClient } from '../ApiClientContext'
import { getApiErrorMessage } from '../utils/apiErrors'
import {
  createBulkImportReport,
  downloadBlob,
  downloadBulkImportTemplate,
  IMPORT_RESOURCES,
  useCommitBulkImport,
  useValidateBulkImport,
} from '../features/imports/data'

const PAGE_SIZE = 20

function formatBytes(bytes) {
  return `${(bytes / 1024).toFixed(1)} KiB`
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
  const [page, setPage] = useState(0)
  const validateMutation = useValidateBulkImport()
  const commitMutation = useCommitBulkImport()

  useEffect(() => {
    initialInput.current?.focus()
  }, [])

  const selectFile = (resource, file) => {
    setLocalError('')
    setValidation(null)
    setPage(0)
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
    try {
      setValidation(await validateMutation.mutateAsync(files))
    } catch {
      // The mutation error is rendered below.
    }
  }

  const commit = async () => {
    if (!validation?.can_commit) return
    try {
      await commitMutation.mutateAsync(files)
      const origin = IMPORT_RESOURCES.find((item) => item.key === initialResource)?.origin || '/courses'
      navigate(origin)
    } catch {
      // The server revalidates the exact selected files.
    }
  }

  const serverErrorContext = errorContext(validateMutation.error || commitMutation.error)
  const issues = validation?.issues || serverErrorContext.issues || []
  const errors = issues.filter((issue) => issue.severity === 'error')
  const warnings = issues.filter((issue) => issue.severity === 'warning')
  const previewItems = validation?.preview?.items || []
  const pageCount = Math.max(1, Math.ceil(previewItems.length / PAGE_SIZE))
  const pageItems = previewItems.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)

  return (
    <div className="p-4">
      <PageHeader
        preTitle="Administração"
        title="Importar CSV"
        description="Importação aditiva e atómica. O backend valida novamente o lote antes de gravar."
      />

      <div className="mb-3" role="status" aria-live="polite">
        {localError && <CAlert color="warning">{localError}</CAlert>}
        {validateMutation.isError && <CAlert color="danger">{getApiErrorMessage(validateMutation.error, 'Não foi possível validar os ficheiros.')}</CAlert>}
        {commitMutation.isError && <CAlert color="danger">{getApiErrorMessage(commitMutation.error, 'Não foi possível concluir a importação.')}</CAlert>}
      </div>

      <div className="row g-3">
        {IMPORT_RESOURCES.map((resource) => {
          const file = files[resource.key]
          return (
            <div className="col-12 col-xl-6" key={resource.key}>
              <CCard className="h-100">
                <CCardHeader className="d-flex justify-content-between align-items-center gap-2">
                  <span>{resource.label}</span>
                  <CButton color="link" size="sm" onClick={() => void downloadBulkImportTemplate(apiClient, resource.key)}>
                    Descarregar template
                  </CButton>
                </CCardHeader>
                <CCardBody>
                  <p className="small text-muted mb-2">UTF-8 com BOM, separado por <code>;</code>, máximo 1 MiB.</p>
                  <label className="form-label" htmlFor={`import-${resource.key}`}>Ficheiro CSV de {resource.label.toLowerCase()}</label>
                  <CFormInput
                    ref={resource.key === initialResource ? initialInput : undefined}
                    id={`import-${resource.key}`}
                    type="file"
                    accept=".csv,text/csv"
                    onChange={(event) => selectFile(resource.key, event.target.files?.[0])}
                  />
                  {file && (
                    <div className="d-flex align-items-center justify-content-between mt-2 small">
                      <span>{file.name} · {formatBytes(file.size)}</span>
                      <CButton color="link" size="sm" onClick={() => selectFile(resource.key, null)}>Remover</CButton>
                    </div>
                  )}
                </CCardBody>
              </CCard>
            </div>
          )
        })}
      </div>

      <div className="d-flex flex-wrap gap-2 align-items-center mt-4">
        <CButton color="primary" disabled={!Object.keys(files).length || validateMutation.isPending || commitMutation.isPending} onClick={() => void validate()}>
          {validateMutation.isPending ? <><CSpinner size="sm" className="me-2" />A validar…</> : 'Validar lote'}
        </CButton>
        <CButton color="success" disabled={!validation?.can_commit || commitMutation.isPending} onClick={() => void commit()}>
          {commitMutation.isPending ? <><CSpinner size="sm" className="me-2" />A importar…</> : 'Confirmar importação'}
        </CButton>
        {issues.length > 0 && (
          <CButton color="secondary" variant="outline" onClick={() => downloadBlob(createBulkImportReport(issues), 'relatorio-importacao.csv')}>
            Descarregar relatório
          </CButton>
        )}
      </div>

      {validation && (
        <section className="mt-4" aria-live="polite" aria-labelledby="import-result-title">
          <h2 id="import-result-title" className="h5">Resultado da validação</h2>
          <div className="d-flex flex-wrap gap-2 mb-3">
            {Object.entries(validation.preview?.counts || {}).map(([key, value]) => <CBadge color="info" key={key}>{key}: {value}</CBadge>)}
            <CBadge color={errors.length ? 'danger' : 'success'}>{errors.length ? `${errors.length} erros` : 'Sem erros'}</CBadge>
            {warnings.length > 0 && <CBadge color="warning">{warnings.length} avisos</CBadge>}
          </div>
          {errors.length > 0 && <CAlert color="danger"><strong>Erros que bloqueiam a confirmação</strong><IssueList issues={errors} /></CAlert>}
          {warnings.length > 0 && <CAlert color="warning"><strong>Avisos que não bloqueiam a confirmação</strong><IssueList issues={warnings} /></CAlert>}
          {pageItems.length > 0 && (
            <>
              <h3 className="h6">Prévia</h3>
              <div className="table-responsive">
                <table className="table table-sm">
                  <thead><tr><th>Recurso</th><th>Dados</th><th>Linha</th></tr></thead>
                  <tbody>{pageItems.map((item, index) => <tr key={`${item.resource}-${item.line}-${index}`}><td>{item.resource}</td><td>{JSON.stringify(item)}</td><td>{item.line}</td></tr>)}</tbody>
                </table>
              </div>
              <div className="d-flex align-items-center gap-2">
                <CButton size="sm" color="secondary" variant="outline" disabled={page === 0} onClick={() => setPage((value) => value - 1)}>Anterior</CButton>
                <span className="small">Página {page + 1} de {pageCount}</span>
                <CButton size="sm" color="secondary" variant="outline" disabled={page + 1 >= pageCount} onClick={() => setPage((value) => value + 1)}>Seguinte</CButton>
              </div>
            </>
          )}
        </section>
      )}
    </div>
  )
}

function IssueList({ issues }) {
  return <ul className="mb-0 mt-2">{issues.map((issue, index) => <li key={`${issue.code}-${issue.line}-${index}`}>{issue.resource}{issue.line ? `, linha ${issue.line}` : ''}{issue.field ? `, ${issue.field}` : ''}: {issue.message}</li>)}</ul>
}

export default BulkImport
