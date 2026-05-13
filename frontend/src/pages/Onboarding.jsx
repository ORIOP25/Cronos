import { useState, useEffect } from "react";
import { useOrganization } from "@clerk/react";
import { useNavigate } from "react-router-dom";
import apiClient from "../apiClient";

const today = new Date().toISOString().slice(0, 10);
const nextYear = new Date(new Date().setFullYear(new Date().getFullYear() + 1)).toISOString().slice(0, 10);

export default function Onboarding() {
  const { organization } = useOrganization();
  const navigate = useNavigate();

  const [status, setStatus] = useState({ loading: true, complete: false });
  const [form, setForm] = useState({
    school_start_date: today,
    school_target_end_date: nextYear,
    school_hard_end_date: nextYear,
    lunch_start: "12:30",
    lunch_end: "14:00",
    lunch_min_duration: 60,
  });
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    apiClient.get("/onboarding/status")
      .then((res) => {
        setStatus({ loading: false, complete: res.data.onboarding_complete });
        if (res.data.onboarding_complete) {
          navigate("/dashboard", { replace: true });
        }
      })
      .catch(() => setStatus({ loading: false, complete: false }));
  }, [navigate]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await apiClient.post("/onboarding", form);
      navigate("/dashboard", { replace: true });
    } catch (err) {
      setError(err.response?.data?.detail || "Erro ao guardar configurações. Tente novamente.");
    } finally {
      setSubmitting(false);
    }
  };

  if (status.loading) {
    return (
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: "60vh" }}>
        <p style={{ color: "var(--rs-body-color)", fontSize: "1.1rem" }}>A preparar a sua escola...</p>
      </div>
    );
  }

  if (status.complete) {
    return (
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: "60vh" }}>
        <p style={{ color: "var(--rs-body-color)", fontSize: "1.1rem" }}>Configuração já concluída. A redirecionar...</p>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 640, margin: "5vh auto", padding: "0 20px" }}>
      <div style={{ marginBottom: 32 }}>
        <h1 style={{ fontSize: "1.8rem", fontWeight: 700, margin: 0 }}>
          Configurar a <span style={{ color: "var(--rs-sidebar-brand)" }}>{organization?.name || "escola"}</span>
        </h1>
        <p style={{ color: "var(--rs-body-color)", marginTop: 8, opacity: 0.7 }}>
          Precisamos de algumas informações para começar a gerar horários.
        </p>
      </div>

      <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 24 }}>
        <fieldset style={fieldsetStyle}>
          <legend style={legendStyle}>Ano Letivo</legend>

          <div style={fieldStyle}>
            <label style={labelStyle}>Data de início</label>
            <input type="date" value={form.school_start_date}
              onChange={e => setForm({ ...form, school_start_date: e.target.value })}
              style={inputStyle} required />
          </div>

          <div style={fieldStyle}>
            <label style={labelStyle}>Fim previsto</label>
            <input type="date" value={form.school_target_end_date}
              onChange={e => setForm({ ...form, school_target_end_date: e.target.value })}
              style={inputStyle} required />
          </div>

          <div style={fieldStyle}>
            <label style={labelStyle}>Fim máximo (inclui exames / recuperações)</label>
            <input type="date" value={form.school_hard_end_date}
              onChange={e => setForm({ ...form, school_hard_end_date: e.target.value })}
              style={inputStyle} required />
          </div>
        </fieldset>

        <fieldset style={fieldsetStyle}>
          <legend style={legendStyle}>Janela de Almoço</legend>

          <div style={{ display: "flex", gap: 16 }}>
            <div style={{ flex: 1 }}>
              <label style={labelStyle}>Início</label>
              <input type="time" value={form.lunch_start}
                onChange={e => setForm({ ...form, lunch_start: e.target.value })}
                style={inputStyle} required />
            </div>
            <div style={{ flex: 1 }}>
              <label style={labelStyle}>Fim</label>
              <input type="time" value={form.lunch_end}
                onChange={e => setForm({ ...form, lunch_end: e.target.value })}
                style={inputStyle} required />
            </div>
          </div>

          <div style={fieldStyle}>
            <label style={labelStyle}>Duração mínima (minutos)</label>
            <input type="number" value={form.lunch_min_duration} min={30} max={120}
              onChange={e => setForm({ ...form, lunch_min_duration: parseInt(e.target.value) || 60 })}
              style={inputStyle} required />
          </div>
        </fieldset>

        {error && (
          <div role="alert" style={{
            padding: "12px 16px", borderRadius: 6,
            backgroundColor: "rgba(229, 62, 62, 0.1)", color: "#e53e3e",
            fontSize: "0.9rem", border: "1px solid rgba(229, 62, 62, 0.2)",
          }}>
            {error}
          </div>
        )}

        <button type="submit" disabled={submitting}
          className="btn-zen btn-zen-primary"
          style={{ padding: "12px 24px", fontSize: "1rem", fontWeight: 600, alignSelf: "flex-start" }}>
          {submitting ? "A guardar..." : "Guardar e Começar"}
        </button>
      </form>
    </div>
  );
}

const fieldsetStyle = {
  border: "1px solid var(--rs-border-color, rgba(255,255,255,0.08))",
  borderRadius: 8,
  padding: "20px 24px",
  background: "rgba(255,255,255,0.02)",
};

const legendStyle = {
  fontSize: "0.95rem",
  fontWeight: 600,
  color: "var(--rs-sidebar-brand)",
  padding: "0 8px",
};

const fieldStyle = {
  display: "flex",
  flexDirection: "column",
  gap: 4,
  marginTop: 12,
};

const labelStyle = {
  fontSize: "0.85rem",
  color: "var(--rs-body-color)",
  opacity: 0.8,
};

const inputStyle = {
  padding: "8px 12px",
  borderRadius: 6,
  border: "1px solid var(--rs-border-color, rgba(255,255,255,0.12))",
  background: "var(--rs-input-bg, rgba(0,0,0,0.2))",
  color: "var(--rs-body-color, #fff)",
  fontSize: "0.95rem",
};
