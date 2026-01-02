import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import MyAvailability from './pages/MyAvailability';
import Teachers from './pages/Teachers'; // Vamos criar este ficheiro a seguir
import DefaultLayout from './components/DefaultLayout';
import ProtectedRoute from './components/ProtectedRoute';

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/login" element={<Login />} />
        
        {/* Rotas Protegidas (Só com Login) */}
        <Route path="/" element={<ProtectedRoute><DefaultLayout /></ProtectedRoute>}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<Dashboard />} />
          
          {/* Novas Rotas */}
          <Route path="teachers" element={<Teachers />} />
          <Route path="my-availability" element={<MyAvailability />} />
        </Route>
      </Routes>
    </Router>
  );
}

export default App;