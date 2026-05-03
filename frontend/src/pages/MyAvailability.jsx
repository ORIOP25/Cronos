import React, { useState, useEffect } from 'react';
import apiClient from '../apiClient';
import AvailabilityGrid from '../components/AvailabilityGrid';
import { useAuthStore } from '../store';
import { PREFERENCE_LEVELS, DEFAULT_PREFERENCE } from '../constants';


const mapAvailabilityApiMessage = (err, context) => {
  const status = err?.response?.status;

  if (status === 403) {
    if (context === 'load') {
      return 'Sem permissões para consultar preferências de disponibilidade.';
    }
    return 'Sem permissões para gravar disponibilidade desta conta.';
  }

  if (status === 404) {
    return 'Perfil de professor não encontrado na organização autenticada.';
  }

  if (status === 400) {
    return 'Dados de disponibilidade inválidos. Atualize a página e tente novamente.';
  }

  if (context === 'load') {
    return 'Falha ao carregar preferências de disponibilidade. Tente novamente.';
  }
  return 'Erro ao gravar disponibilidade. Tente novamente.';
};

const buildAvailabilityMap = (rows, validTimeslotIds) => {
  const nextMap = {};
  let ignoredCount = 0;

  for (const row of rows) {
    if (validTimeslotIds.has(row.timeslot_id)) {
      nextMap[row.timeslot_id] = Number(row.score);
    } else {
      ignoredCount += 1;
    }
  }

  return { map: nextMap, ignoredCount };
};

const MyAvailability = () => {
  const [timeslots, setTimeslots] = useState([]);
  const [availabilityMap, setAvailabilityMap] = useState({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [feedback, setFeedback] = useState(null);
  const [selectedMode, setSelectedMode] = useState(DEFAULT_PREFERENCE);
  const teacherId = useAuthStore((state) => state.user?.teacherId);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setError(null);
        setFeedback(null);

        const timeslotsRes = await apiClient.get('/timeslots/');
        const fetchedTimeslots = Array.isArray(timeslotsRes.data) ? timeslotsRes.data : [];
        setTimeslots(fetchedTimeslots);

        const myAvailabilityRes = await apiClient.get('/teachers/me/availability');
        const persistedRows = Array.isArray(myAvailabilityRes.data) ? myAvailabilityRes.data : [];
        const validTimeslotIds = new Set(fetchedTimeslots.map((slot) => slot.id));

        const { map, ignoredCount } = buildAvailabilityMap(persistedRows, validTimeslotIds);
        setAvailabilityMap(map);

        if (ignoredCount > 0) {
          setFeedback({
            type: 'info',
            message: `Foram ignoradas ${ignoredCount} preferências antigas em blocos já removidos.`,
          });
        } else if (persistedRows.length === 0) {
          setFeedback({
            type: 'info',
            message: 'Sem preferências gravadas. Pode começar a pintar a grelha.',
          });
        }
      } catch (err) {
        setError(mapAvailabilityApiMessage(err, 'load'));
      } finally {
        setLoading(false);
      }
    };

    void fetchData();
  }, []);

  const handleGridChange = (timeslotId, newScore) => {
    if (saving) {
      return;
    }

    setFeedback(null);
    setAvailabilityMap((prev) => ({
      ...prev,
      [timeslotId]: newScore,
    }));
  };

  const handleSave = async () => {
    if (!teacherId) {
      setFeedback({
        type: 'error',
        message: 'Esta conta não está associada a um perfil de professor.',
      });
      return;
    }

    setSaving(true);
    setFeedback(null);

    try {
      const validTimeslotIds = new Set(timeslots.map((slot) => slot.id));
      const payload = Object.entries(availabilityMap)
        .map(([tsId, score]) => ({
          timeslot_id: Number.parseInt(tsId, 10),
          score,
        }))
        .filter((item) => validTimeslotIds.has(item.timeslot_id));

      await apiClient.post(`/teachers/${teacherId}/availability`, payload);
      setFeedback({ type: 'success', message: 'Disponibilidade gravada com sucesso.' });
    } catch (err) {
      setFeedback({ type: 'error', message: mapAvailabilityApiMessage(err, 'save') });
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <div style={{ padding: '32px', color: 'var(--rs-muted)' }}>A carregar grelha...</div>;
  if (error) return <div style={{color: 'var(--rs-deep)', padding: '32px'}} role="alert">{error}</div>;

  return (
    <div>
      <h2 style={{ color: 'var(--rs-heading)', fontWeight: '700', marginBottom: '4px' }}>Minhas Preferências</h2>
      <p style={{ color: 'var(--rs-muted)', marginBottom: '16px' }}>Selecione uma ferramenta e clique (ou arraste) nas células para pintar.</p>

      {feedback ? (
        <div
          role={feedback.type === 'error' ? 'alert' : 'status'}
          className={`zen-alert zen-alert-${feedback.type === 'error' ? 'danger' : feedback.type}`}
        >
          {feedback.message}
        </div>
      ) : null}
      
      <div style={{ display: 'flex', gap: '8px', marginBottom: '20px', flexWrap: 'wrap' }}>
        {['-1', '0', '1', '2'].map((score) => {
          const info = PREFERENCE_LEVELS[score];
          const numScore = Number(score);
          const isActive = selectedMode === numScore;
          return (
            <button
              key={score}
              type="button"
              onClick={() => setSelectedMode(numScore)}
              disabled={saving}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                padding: '8px 16px',
                border: isActive ? '2px solid var(--rs-primary)' : '2px solid var(--rs-grid-cell-border)',
                borderRadius: '8px',
                backgroundColor: isActive ? info.color : 'transparent',
                cursor: saving ? 'not-allowed' : 'pointer',
                fontWeight: isActive ? '700' : '500',
                fontSize: '0.9rem',
                transition: 'all 0.15s ease',
                opacity: saving ? 0.5 : (isActive ? 1 : 0.7),
                boxShadow: isActive ? '0 2px 8px rgba(0,0,0,0.12)' : 'none',
              }}
            >
              <span style={{ width: '14px', height: '14px', borderRadius: '50%', backgroundColor: info.color, border: '1px solid var(--rs-grid-cell-border)', flexShrink: 0 }} />
              {info.label}
            </button>
          );
        })}
      </div>

      <div style={{ opacity: saving ? 0.7 : 1, pointerEvents: saving ? 'none' : 'auto' }}>
        <AvailabilityGrid 
          timeslots={timeslots} 
          availabilityMap={availabilityMap} 
          onChange={handleGridChange}
          selectedMode={selectedMode}
        />
      </div>

      <div style={{ marginTop: '24px', textAlign: 'right' }}>
        <button 
          onClick={handleSave} 
          disabled={saving}
          className="btn-zen btn-zen-primary"
        >
          {saving ? 'A guardar...' : 'Guardar Alterações'}
        </button>
      </div>
    </div>
  );
};

export default MyAvailability;