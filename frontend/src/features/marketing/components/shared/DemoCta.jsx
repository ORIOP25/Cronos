import { Link } from 'react-router-dom'

export default function DemoCta({ title = 'Veja o Cronos a funcionar na sua escola', body = 'Mostre-nos como organiza os horários e preparamos uma demonstração à medida.', source }) {
  return (
    <section className="cronos-demo-cta" data-analytics-source={source}>
      <div className="cronos-container cronos-demo-cta__inner">
        <div className="cronos-demo-cta__copy">
          <h2>{title}</h2>
          <p>{body}</p>
        </div>
        <Link to="/contacto" className="cronos-button cronos-button--light">Pedir demonstração</Link>
      </div>
    </section>
  )
}
