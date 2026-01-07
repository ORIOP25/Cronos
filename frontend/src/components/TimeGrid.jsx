import React from 'react'

const TimeGrid = ({ timeslots }) => {
  // 1. Extrair tempos únicos ordenados para o eixo Y
  const uniqueTimes = [...new Set(timeslots.map(t => t.start_time))].sort()
  
  // 2. Mapeamento de dias
  const days = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
  // Descobrir quais dias existem nos dados
  const activeDaysIndices = [...new Set(timeslots.map(t => t.day_of_week))].sort()

  if (!timeslots.length) return <div className="text-center p-5 text-muted">Sem horários configurados.</div>

  return (
    <div className="table-responsive">
      <table className="table table-bordered table-sm text-center align-middle" style={{tableLayout: 'fixed'}}>
        <thead className="table-light">
          <tr>
            <th style={{width: '100px'}}>Horário</th>
            {activeDaysIndices.map(d => (
              <th key={d}>{days[d]}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {uniqueTimes.map(time => (
            <tr key={time}>
              {/* Coluna da Hora */}
              <td className="fw-bold text-muted bg-light">{time.substring(0, 5)}</td>
              
              {/* Colunas dos Dias */}
              {activeDaysIndices.map(dayIdx => {
                // Encontrar o slot correspondente a este dia e hora
                const slot = timeslots.find(t => t.day_of_week === dayIdx && t.start_time === time)
                
                return (
                  <td key={`${dayIdx}-${time}`} className={slot ? "bg-white" : "bg-light"}>
                    {slot ? (
                      <div className="p-2 small text-muted border rounded border-dashed">
                        {/* AQUI APARECERÁ A AULA NO FUTURO */}
                        <span className="d-block text-uppercase" style={{fontSize: '0.75rem'}}>Livre</span>
                      </div>
                    ) : (
                        <span className="text-black-50">-</span>
                    )}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default TimeGrid