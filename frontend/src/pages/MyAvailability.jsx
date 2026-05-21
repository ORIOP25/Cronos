import React, { useState, useEffect, useCallback } from 'react';
import AvailabilityGrid from '../components/AvailabilityGrid';
import { useUser } from '@clerk/react';
import { useTimeslots, useMyAvailability, useSaveAvailability } from '../hooks/useSchoolData';
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
  const [availabilityMap, setAvailabilityMap] = useState({});
  const [feedback, setFeedback] = useState(null);
  const [selectedMode, setSelectedMode] = useState(DEFAULT_PREFERENCE);
  const { user } = useUser()
  const teacherId = user?.publicMetadata?.teacher_id;

  const { data: timeslots = [], isLoading: loading } = useTimeslots();
  const { data: persistedRows = [] } = useMyAvailability({ enabled: Boolean(teacherId) });

  const saveMutation = useSaveAvailability();

  useEffect(() => {
    if (timeslots.length === 0 || loading) return;
    const validTimeslotIds = new Set(timeslots.map((slot) => slot.id));
    const rows = Array.isArray(persistedRows) ? persistedRows : [];

    const { map, ignoredCount } = buildAvailabilityMap(rows, validTimeslotIds);
    setAvailabilityMap(map);

    if (ignoredCount > 0) {
      setFeedback({
        type: 'info',
        message: `Foram ignoradas ${ignoredCount} preferências antigas em blocos já removidos.`,
      });
    } else if (rows.length === 0) {
      setFeedback({
        type: 'info',
        message: 'Sem preferências gravadas. Pode começar a pintar a grelha.',
      });
    }
  }, [timeslots, persistedRows, loading]);

  const handleGridChange = (timeslotId, newScore) => {
    if (saveMutation.isPending) {
      return;
    }

    setFeedback(null);
    setAvailabilityMap((prev) => ({
      ...prev,
      [timeslotId]: newScore,
    }));
  };

  const handleSave = useCallback(async () => {
    if (!teacherId) {
      setFeedback({
        type: 'error',
        message: 'Esta conta não está associada a um perfil de professor.',
      });
      return;
    }

    setFeedback(null);

    const validTimeslotIds = new Set(timeslots.map((slot) => slot.id));
    const payload = Object.entries(availabilityMap)
      .map(([tsId, score]) => ({
        timeslot_id: Number.parseInt(tsId, 10),
        score,
      }))
      .filter((item) => validTimeslotIds.has(item.timeslot_id));

    try {
      await saveMutation.mutateAsync({ teacherId, payload });
      setFeedback({ type: 'success', message: 'Disponibilidade gravada com sucesso.' });
    } catch (err) {
      setFeedback({ type: 'error', message: mapAvailabilityApiMessage(err, 'save') });
    }
  }, [teacherId, timeslots, availabilityMap, saveMutation]);

  if (loading) return <div style={{ padding: '32px', color: 'var(--rs-muted)' }}>A carregar grelha...</div>;

  const saving = saveMutation.isPending;

  return (
    <div>
      <div className="d-flex justify-content-between align-items-end mb-5 flex-wrap gap-3">
        <div>
          <span className="zen-caps" style={{ color: 'var(--brand-600)' }}>Professor</span>
          <h1 className="text-display mt-2" style={{ fontSize: '3rem', color: 'var(--brand-950)' }}>
            Minhas <span className="text-editorial">Preferências</span>
          </h1>
        </div>
        <div className="luxury-line" style={{ width: '100px', marginBottom: '14px' }} />
      </div>
      <p style={{ color: 'var(--rs-muted)', marginBottom: '16px', marginTop: '-1rem' }}>Selecione uma ferramenta e clique (ou arraste) nas células para pintar.</p>

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