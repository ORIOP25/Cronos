import React from 'react';
import { PREFERENCE_LEVELS, DEFAULT_PREFERENCE } from '../constants';

const AvailabilityGrid = ({ timeslots, availabilityMap, onChange }) => {
  // timeslots: Lista vinda da BD (ex: day_of_week: 0, start_time: "08:00:00")
  
  // Agrupar timeslots por Dias da Semana para desenhar a tabela
  const days = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta"];
  
  // Extrair as horas únicas e ordenar (ex: "08:00:00", "09:00:00")
  const uniqueTimes = [...new Set(timeslots.map(t => t.start_time))].sort();

  const getScore = (timeslotId) => {
    return availabilityMap[timeslotId] !== undefined 
      ? availabilityMap[timeslotId] 
      : DEFAULT_PREFERENCE;
  };

  const handleCellClick = (timeslot) => {
    const currentScore = getScore(timeslot.id);
    const nextScore = PREFERENCE_LEVELS[currentScore].next;
    onChange(timeslot.id, nextScore);
  };

  const styles = {
    grid: {
      display: 'grid',
      gridTemplateColumns: `100px repeat(${days.length}, 1fr)`,
      gap: '4px',
      marginTop: '20px'
    },
    headerCell: {
      fontWeight: '600',
      textAlign: 'center',
      padding: '10px',
      backgroundColor: 'var(--rs-grid-header-bg)',
      color: 'var(--rs-grid-header-text)',
      fontSize: '0.85rem',
      borderRadius: '6px',
    },
    timeLabel: {
      fontWeight: '600',
      textAlign: 'center',
      padding: '10px',
      backgroundColor: 'var(--rs-grid-time-bg)',
      color: 'var(--rs-grid-time-text)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      borderRadius: '6px',
      fontSize: '0.85rem',
    },
    cell: (score) => ({
      height: '60px',
      backgroundColor: PREFERENCE_LEVELS[score].color,
      cursor: 'pointer',
      border: '1px solid var(--rs-grid-cell-border)',
      borderRadius: '8px',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      fontSize: '0.8rem',
      fontWeight: '500',
      transition: 'all 0.2s ease',
      userSelect: 'none',
    })
  };

  return (
    <div style={{ maxWidth: '100%', overflowX: 'auto' }}>
      {/* Legenda */}
      <div style={{ display: 'flex', gap: '15px', marginBottom: '15px' }}>
        {Object.entries(PREFERENCE_LEVELS).map(([score, info]) => (
          <div key={score} style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
            <div style={{ width: '20px', height: '20px', backgroundColor: info.color, border: '1px solid var(--rs-grid-cell-border)', borderRadius: '4px' }}></div>
            <span>{info.label}</span>
          </div>
        ))}
      </div>

      {/* A Grelha */}
      <div style={styles.grid}>
        {/* Cabeçalho */}
        <div style={styles.headerCell}>Hora</div>
        {days.map(day => (
          <div key={day} style={styles.headerCell}>{day}</div>
        ))}

        {/* Linhas (Horas) */}
        {uniqueTimes.map(time => (
          <React.Fragment key={time}>
            {/* Coluna da Hora (com slice para tirar os segundos :00) */}
            <div style={styles.timeLabel}>{time.slice(0, 5)}</div>
            
            {/* Células dos Dias */}
            {days.map((dayName, index) => {
              // CORREÇÃO CRÍTICA AQUI:
              // Usamos 'index' (0-4) em vez de 'dayName' ("Segunda")
              // para bater certo com o 'day_of_week' da base de dados.
              const slot = timeslots.find(t => t.day_of_week === index && t.start_time === time);
              
              // Se não houver slot na BD para esta hora/dia, desenha um buraco cinzento
              if (!slot) return <div key={`${index}-${time}`} style={{ background: 'var(--rs-grid-empty-bg)', border: '1px dashed var(--rs-grid-empty-border)', borderRadius: '8px' }} title="Sem horário definido" />; 

              const score = getScore(slot.id);
              
              return (
                <div 
                  key={slot.id}
                  style={styles.cell(score)}
                  onClick={() => handleCellClick(slot)}
                  title={`Clique para mudar: ${dayName} às ${time}`}
                >
                  {PREFERENCE_LEVELS[score].label}
                </div>
              );
            })}
          </React.Fragment>
        ))}
      </div>
    </div>
  );
};

export default AvailabilityGrid;