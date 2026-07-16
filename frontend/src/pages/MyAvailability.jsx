import { useState, useMemo, useCallback } from 'react';
import AvailabilityGrid from '../components/AvailabilityGrid';
import PageHeader from '../components/PageHeader';
import { useCurrentMember } from '../features/members/data';
import { useTimeslots } from '../features/catalog/data';
import { useMyAvailability, useSaveAvailability } from '../features/operations/data';
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
  const [userEdits, setUserEdits] = useState({});
  const [feedback, setFeedback] = useState(null);
  const [selectedMode, setSelectedMode] = useState(DEFAULT_PREFERENCE);
  const { data: currentMember } = useCurrentMember()
  const teacherId = currentMember?.teacher_id;

  const { data: timeslots = [], isLoading: loading } = useTimeslots();
  const { data: persistedRows = [], isLoading: availLoading } = useMyAvailability({ enabled: Boolean(teacherId) });

  const saveMutation = useSaveAvailability();

  const { dbMap, derivedFeedback } = useMemo(() => {
    if (timeslots.length === 0 || loading || availLoading) {
      return { dbMap: {}, derivedFeedback: null };
    }
    const validTimeslotIds = new Set(timeslots.map((slot) => slot.id));
    const rows = Array.isArray(persistedRows) ? persistedRows : [];

    const { map, ignoredCount } = buildAvailabilityMap(rows, validTimeslotIds);

    let feedbackResult = null;
    if (ignoredCount > 0) {
      feedbackResult = {
        type: 'info',
        message: `Foram ignoradas ${ignoredCount} preferências antigas em blocos já removidos.`,
      };
    } else if (rows.length === 0) {
      feedbackResult = {
        type: 'info',
        message: 'Sem preferências gravadas. Pode começar a pintar a grelha.',
      };
    }
    return { dbMap: map, derivedFeedback: feedbackResult };
  }, [timeslots, persistedRows, loading, availLoading]);

  const availabilityMap = useMemo(
    () => ({ ...dbMap, ...userEdits }),
    [dbMap, userEdits],
  );

  const effectiveFeedback = feedback ?? derivedFeedback;

  const handleGridChange = (timeslotId, newScore) => {
    if (saveMutation.isPending) return;

    setFeedback(null);
    setUserEdits((prev) => ({
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
      <PageHeader preTitle="Professor" title={<span>Minhas <span className="text-editorial">Preferências</span></span>} />
      <p style={{ color: 'var(--rs-muted)', marginBottom: '16px', marginTop: '-1rem' }}>Selecione uma ferramenta e clique (ou arraste) nas células para pintar.</p>

      {effectiveFeedback ? (
        <div
          role={effectiveFeedback.type === 'error' ? 'alert' : 'status'}
          className={`zen-alert zen-alert-${effectiveFeedback.type === 'error' ? 'danger' : effectiveFeedback.type}`}
        >
          {effectiveFeedback.message}
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
