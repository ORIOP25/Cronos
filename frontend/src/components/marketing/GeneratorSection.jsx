import { useState, memo } from 'react'
import CIcon from '@coreui/icons-react'
import { cilList, cilCheckCircle, cilCheck } from '@coreui/icons'
import { generatorInputs, generatorOutputs } from '../../data/marketingData'

const GeneratorSection = memo(function GeneratorSection() {
  const [activeGenTab, setActiveGenTab] = useState('inputs')

  return (
    <section className="cronos-generator" id="gerador" aria-labelledby="cronos-generator-title">
      <div className="cronos-layout cronos-generator__grid">
        <div className="cronos-generator__copy">
          <h2 id="cronos-generator-title">Um gerador que pensa como um coordenador</h2>
          <p>
            Em vez de tentar adivinhar num quadrado em branco, diga ao Cronos o que tem na sua escola: salas disponíveis, dias preferidos dos professores e carga de cada UFCD. Nós fazemos as contas complexas por si.
          </p>
        </div>

        <div className="cronos-generator__card">
          <div className="cronos-gen-toggle-bar">
            <button
              type="button"
              className={`cronos-gen-toggle-btn ${activeGenTab === 'inputs' ? 'is-active' : ''}`}
              onClick={() => setActiveGenTab('inputs')}
            >
              <CIcon icon={cilList} /> O Cronos recebe
            </button>
            <button
              type="button"
              className={`cronos-gen-toggle-btn ${activeGenTab === 'outputs' ? 'is-active' : ''}`}
              onClick={() => setActiveGenTab('outputs')}
            >
              <CIcon icon={cilCheckCircle} /> A escola recebe
            </button>
          </div>

          {activeGenTab === 'inputs' ? (
            <div className="cronos-gen-panel-block">
              <ul className="cronos-gen-list">
                {generatorInputs.map((item) => (
                  <li key={item}>
                    <CIcon icon={cilCheck} className="cronos-gen-icon" />
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <div className="cronos-gen-panel-block">
              <ul className="cronos-gen-list">
                {generatorOutputs.map((item) => (
                  <li key={item}>
                    <CIcon icon={cilCheckCircle} className="cronos-gen-icon" />
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </section>
  )
})

export default GeneratorSection
