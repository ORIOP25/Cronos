import { Link } from 'react-router-dom'
import { LEGAL_EFFECTIVE_DATE, documents } from './content.jsx'
import LegalText from './LegalText.jsx'

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
            <div><dt>Versão</dt><dd>{document.version}</dd></div>
            <div><dt>Vigência</dt><dd>{LEGAL_EFFECTIVE_DATE}</dd></div>
          </dl>
        </header>
        <nav className="cronos-legal__toc" aria-label="Índice">
          <strong>Índice</strong>
          <ol>{[...document.sections.map(([title]) => title), ...(document.annexes ?? []).map(({ title }) => title)].map((title) => <li key={title}><a href={`#${slugify(title)}`}>{title}</a></li>)}</ol>
        </nav>
        <div className="cronos-legal__body">
          {document.sections.map(([title, content]) => <section key={title} id={slugify(title)}><h2>{title}</h2><p>{content}</p></section>)}
          {document.annexes?.map((annex) => (
            <section key={annex.title} id={slugify(annex.title)}>
              <h2>{annex.title}</h2>
              {annex.type === 'table' ? <LegalTable items={annex.items} /> : <p><LegalText text={annex.body} /></p>}
            </section>
          ))}
        </div>
      </div>
    </article>
  )
}

function LegalTable({ items }) {
  const hasSafeguards = items.some((item) => item.safeguards)
  return <div className="cronos-legal__table-wrap"><table><thead><tr><th>Fornecedor</th><th>Finalidade</th><th>Localização</th>{hasSafeguards && <th>Salvaguardas</th>}</tr></thead><tbody>{items.map((item) => <tr key={item.name}><td>{item.name}</td><td>{item.purpose}</td><td>{item.location}</td>{hasSafeguards && <td>{item.safeguards}</td>}</tr>)}</tbody></table></div>
}

function slugify(value) {
  return value.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
}
