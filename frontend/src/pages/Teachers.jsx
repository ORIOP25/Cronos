import React, { useState, useEffect } from 'react';
import apiClient from '../apiClient';

const Teachers = () => {
  const [teachers, setTeachers] = useState([]);
  const [name, setName] = useState('');
  const [loading, setLoading] = useState(true);

  // Carregar lista
  const fetchTeachers = async () => {
    try {
      const res = await apiClient.get('/teachers/');
      setTeachers(res.data);
    } catch (error) {
      console.error("Erro ao buscar professores:", error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTeachers();
  }, []);

  // Criar novo professor
  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!name) return;

    try {
      await apiClient.post('/teachers/', { name });
      setName('');
      fetchTeachers(); // Recarregar lista
      alert("Professor criado com sucesso!");
    } catch (error) {
      alert("Erro ao criar professor.");
    }
  };

  return (
    <div>
      <h1>Gestão de Professores</h1>

      {/* Formulário Simples */}
      <div style={{ background: 'white', padding: '20px', borderRadius: '8px', marginBottom: '20px' }}>
        <h3>Adicionar Novo</h3>
        <form onSubmit={handleSubmit} style={{ display: 'flex', gap: '10px' }}>
          <input 
            type="text" 
            placeholder="Nome do Professor" 
            value={name}
            onChange={(e) => setName(e.target.value)}
            style={{ padding: '8px', borderRadius: '4px', border: '1px solid #ccc', flex: 1 }}
          />
          <button type="submit" style={{ padding: '8px 20px', background: '#2563eb', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer' }}>
            Adicionar
          </button>
        </form>
      </div>

      {/* Lista */}
      {loading ? <p>A carregar...</p> : (
        <div style={{ display: 'grid', gap: '10px' }}>
          {teachers.map(t => (
            <div key={t.id} style={{ background: 'white', padding: '15px', borderRadius: '8px', display: 'flex', justifyContent: 'space-between' }}>
              <span>ID: {t.id} - <strong>{t.name}</strong></span>
              {/* Futuramente: Botão apagar/editar */}
            </div>
          ))}
          {teachers.length === 0 && <p>Nenhum professor encontrado.</p>}
        </div>
      )}
    </div>
  );
};

export default Teachers;