// src/pages/MyAvailability.jsx 

import React, { useState, useEffect } from 'react';
import apiClient from '../apiClient';
import AvailabilityGrid from '../components/AvailabilityGrid';
import { useAuthStore } from '../store';

const MyAvailability = () => {
  const [timeslots, setTimeslots] = useState([]);
  const [availabilityMap, setAvailabilityMap] = useState({}); // { timeslot_id: score }
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
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
        timeslot_id: parseInt(tsId),
        score: score,
        teacher_id: teacherId
      }));

      // Enviar para o endpoint de Bulk Update
      await apiClient.post(`/teachers/${teacherId}/availability`, payload);
      alert("Disponibilidade gravada com sucesso! 💾");
    } catch (err) {
      console.error(err);
      alert("Erro ao gravar. Tente novamente.");
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <div>A carregar grelha...</div>;
  if (error) return <div style={{color: 'red'}}>{error}</div>;

  return (
    <div style={{ padding: '20px' }}>
      <h1>A Minha Disponibilidade 📅</h1>
      <p>Clique nas células para definir a sua preferência.</p>
      
      <AvailabilityGrid 
        timeslots={timeslots} 
        availabilityMap={availabilityMap} 
        onChange={handleGridChange} 
      />

      <div style={{ marginTop: '20px', textAlign: 'right' }}>
        <button 
          onClick={handleSave} 
          disabled={saving}
          style={{
            padding: '10px 20px',
            fontSize: '16px',
            backgroundColor: '#2563eb',
            color: 'white',
            border: 'none',
            borderRadius: '5px',
            cursor: saving ? 'not-allowed' : 'pointer'
          }}
        >
          {saving ? 'A gravar...' : 'Gravar Alterações'}
        </button>
      </div>
    </div>
  );
};

export default MyAvailability;