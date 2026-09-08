import { Link } from 'react-router-dom'
import { LEGAL_EFFECTIVE_DATE, LEGAL_VERSION, documents, subprocessors } from './content.jsx'

export default function LegalDocumentLayout({ kind }) {
  const document = documents[kind]
  return (
    <article className="cronos-legal" aria-labelledby="legal-document-title">
      <div className="cronos-legal__inner">
        <Link className="cronos-legal__back" to="/">← Voltar ao Cronos</Link>
        <header className="cronos-legal__header">
          <p className="cronos-eyebrow">Documentação jurídica</p>
          <h1 id="legal-document-title">{document.title}</h1>
          <p>{document.intro}</p>
          <dl className="cronos-legal__meta">
            <div><dt>Versão</dt><dd>{LEGAL_VERSION}</dd></div>
            <div><dt>Vigência</dt><dd>{LEGAL_EFFECTIVE_DATE}</dd></div>
          </dl>
        </header>
        <nav className="cronos-legal__toc" aria-label="Índice">
          <strong>Índice</strong>
          <ol>{document.sections.map(([title]) => <li key={title}><a href={`#${slugify(title)}`}>{title}</a></li>)}</ol>
        </nav>
        <div className="cronos-legal__body">
          {document.sections.map(([title, content]) => <section key={title} id={slugify(title)}><h2>{title}</h2><p>{content}</p></section>)}
          {kind === 'dpa' && <section id="subprocessadores"><h2>Anexo A — Subprocessadores</h2><div className="cronos-legal__table-wrap"><table><thead><tr><th>Fornecedor</th><th>Finalidade</th><th>Localização</th></tr></thead><tbody>{subprocessors.map((item) => <tr key={item.name}><td>{item.name}</td><td>{item.purpose}</td><td>{item.location}</td></tr>)}</tbody></table></div></section>}
          {kind === 'dpa' && <section id="security-measures"><h2>Anexo B — Medidas de segurança</h2><p>O Cronos aplica autenticação Clerk, tokens de organização, autorização por capacidade, RLS forçado, backups operacionais, limites de pedidos, gestão de segredos e logs estruturados sem conteúdo pessoal.</p></section>}
          {kind === 'privacy' && <section id="cookies"><h2>Cookies</h2><p>Consulte também a <Link to="/cookies">página de cookies</Link> para o resumo das tecnologias estritamente necessárias.</p></section>}
        </div>
      </div>
    </article>
  )
}

function slugify(value) {
  return value.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
}
