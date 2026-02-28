// src/pages/MyAvailability.jsx 

import React, { useState, useEffect } from 'react';
import apiClient from '../apiClient';
import AvailabilityGrid from '../components/AvailabilityGrid';
import { useAuthStore } from '../store';
import { PREFERENCE_LEVELS, DEFAULT_PREFERENCE } from '../constants';

const MyAvailability = () => {
  const [timeslots, setTimeslots] = useState([]);
  const [availabilityMap, setAvailabilityMap] = useState({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [selectedMode, setSelectedMode] = useState(DEFAULT_PREFERENCE);
  const teacherId = useAuthStore((state) => state.user?.teacherId);

  // 1. Carregar Dados Iniciais
  useEffect(() => {
    const fetchData = async () => {
      try {
        // Carregar slots de tempo
        const timeslotsRes = await apiClient.get('/timeslots/');
        setTimeslots(timeslotsRes.data);

        // Carregar disponibilidades já salvas do professor logado
        // (Assumindo que temos um endpoint 'me' ou usamos o ID do user)
        // Nota: Por agora, vamos simular que começamos do zero ou implementar o fetch depois
        // const myAvailRes = await apiClient.get('/teachers/me/availability');
        // setAvailabilityMap(converteParaMapa(myAvailRes.data)); 
        
      } catch (err) {
        console.error("Erro ao carregar dados", err);
        setError("Falha ao carregar horários. O backend está ligado?");
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  // 2. Lógica de Mudança (State Local)
  const handleGridChange = (timeslotId, newScore) => {
    setAvailabilityMap(prev => ({
      ...prev,
      [timeslotId]: newScore
    }));
  };

  // 3. Gravar no Backend
  const handleSave = async () => {
    // PROTEÇÃO: Se não houver ID (ex: é um Admin sem perfil de prof), avisa
    if (!teacherId) {
        alert("Erro: Esta conta não está associada a um perfil de Professor.");
        return;
    }

    setSaving(true);
    try {
      // Transformar o mapa {1: 2, 5: -1} numa lista para a API
      const payload = Object.entries(availabilityMap).map(([tsId, score]) => ({
        timeslot_id: Number.parseInt(tsId, 10),
        score: score,
      }));

      // Enviar para o endpoint de Bulk Update
      await apiClient.post(`/teachers/${teacherId}/availability`, payload);
      alert("Disponibilidade gravada com sucesso!");
    } catch (err) {
      console.error(err);
      alert("Erro ao gravar. Tente novamente.");
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <div style={{ padding: '32px', color: 'var(--rs-muted)' }}>A carregar grelha...</div>;
  if (error) return <div style={{color: 'var(--rs-deep)', padding: '32px'}}>{error}</div>;

  return (
    <div>
      <h2 style={{ color: 'var(--rs-heading)', fontWeight: '700', marginBottom: '4px' }}>Minhas Preferências</h2>
      <p style={{ color: 'var(--rs-muted)', marginBottom: '16px' }}>Selecione uma ferramenta e clique (ou arraste) nas células para pintar.</p>
      
      {/* Seletor de Modo (Paintbrush Toolbar) — Ordem: Impossível → Evitar → Neutro → Preferencial */}
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
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                padding: '8px 16px',
                border: isActive ? '2px solid var(--rs-primary)' : '2px solid var(--rs-grid-cell-border)',
                borderRadius: '8px',
                backgroundColor: isActive ? info.color : 'transparent',
                cursor: 'pointer',
                fontWeight: isActive ? '700' : '500',
                fontSize: '0.9rem',
                transition: 'all 0.15s ease',
                opacity: isActive ? 1 : 0.7,
                boxShadow: isActive ? '0 2px 8px rgba(0,0,0,0.12)' : 'none',
              }}
            >
              <span style={{ width: '14px', height: '14px', borderRadius: '50%', backgroundColor: info.color, border: '1px solid var(--rs-grid-cell-border)', flexShrink: 0 }} />
              {info.label}
            </button>
          );
        })}
      </div>

      <AvailabilityGrid 
        timeslots={timeslots} 
        availabilityMap={availabilityMap} 
        onChange={handleGridChange}
        selectedMode={selectedMode}
      />

      <div style={{ marginTop: '24px', textAlign: 'right' }}>
        <button 
          onClick={handleSave} 
          disabled={saving}
          style={{
            padding: '10px 24px',
            fontSize: '15px',
            backgroundColor: 'var(--rs-primary)',
            color: '#ffffff',
            border: 'none',
            borderRadius: '8px',
            cursor: saving ? 'not-allowed' : 'pointer',
            fontWeight: '600',
            transition: 'all 0.2s ease',
          }}
        >
          {saving ? 'A gravar...' : 'Gravar Alterações'}
        </button>
      </div>
    </div>
  );
};

export default MyAvailability;