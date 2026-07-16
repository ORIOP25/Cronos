import React, { useRef, useCallback, useEffect } from 'react';
import { PREFERENCE_LEVELS, DEFAULT_PREFERENCE } from '../constants';

const AvailabilityGrid = ({ timeslots, availabilityMap, onChange, selectedMode }) => {
  // timeslots: Lista vinda da BD (ex: day_of_week: 0, start_time: "08:00:00")
  
  // Agrupar timeslots por Dias da Semana para desenhar a tabela
  const days = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta"];
  
  // Extrair as horas únicas e ordenar (ex: "08:00:00", "09:00:00")
  const uniqueTimes = [...new Set(timeslots.map(t => t.start_time))].sort((a, b) => a.localeCompare(b));

  // --- Click-and-Drag (Paintbrush) ---
  const isDragging = useRef(false);

  const getScore = (timeslotId) => availabilityMap[timeslotId] ?? DEFAULT_PREFERENCE;

  const applyPaint = useCallback((timeslot) => {
    const currentScore = availabilityMap[timeslot.id] ?? DEFAULT_PREFERENCE;
    if (currentScore !== selectedMode) {
      onChange(timeslot.id, selectedMode);
    }
  }, [selectedMode, availabilityMap, onChange]);

  const handleCellMouseDown = (timeslot) => {
    isDragging.current = true;
    applyPaint(timeslot);
  };

  const handleCellMouseEnter = (timeslot) => {
    if (isDragging.current) {
      applyPaint(timeslot);
    }
  };

  const handleMouseUp = () => {
    isDragging.current = false;
  };

  // Captura a libertação do rato globalmente para não quebrar o drag quando
  // o cursor sai da janela antes de soltar o botão.
  useEffect(() => {
    globalThis.addEventListener('mouseup', handleMouseUp);
    return () => globalThis.removeEventListener('mouseup', handleMouseUp);
  }, []);

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
      width: '100%',
      height: '60px',
      padding: 0,
      fontFamily: 'inherit',
      color: 'inherit',
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
              const slot = timeslots.find(t => t.day_of_week === index && t.start_time === time);
              
              if (!slot) return <div key={`${index}-${time}`} style={{ background: 'var(--rs-grid-empty-bg)', border: '1px dashed var(--rs-grid-empty-border)', borderRadius: '8px' }} title="Sem horário definido" />; 

              const score = getScore(slot.id);
              
              return (
                <button
                  type="button"
                  key={slot.id}
                  style={styles.cell(score)}
                  onMouseDown={() => handleCellMouseDown(slot)}
                  onMouseEnter={() => handleCellMouseEnter(slot)}
                  onClick={() => applyPaint(slot)}
                  title={`${PREFERENCE_LEVELS[selectedMode].label}: ${dayName} às ${time}`}
                >
                  {PREFERENCE_LEVELS[score].label}
                </button>
              );
            })}
          </React.Fragment>
        ))}
      </div>
    </div>
  );
};

export default AvailabilityGrid;