import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import MyAvailability from './pages/MyAvailability';
import Teachers from './pages/Teachers';
import Rooms from './pages/Rooms';
import Subjects from './pages/Subjects';
import SchoolConfig from './pages/SchoolConfig';
import Schedules from './pages/Schedules';
import Courses from './pages/Courses';
import CourseDetails from './pages/CourseDetails';
import ClassDetails from './pages/ClassDetails';
import ServiceDistribution from './pages/ServiceDistribution';
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
          <Route path="rooms" element={<Rooms />} />
          <Route path="subjects" element={<Subjects />} />
          
          {/* Cursos com Hierarchia */}
          <Route path="courses" element={<Courses />} />
          <Route path="courses/:id" element={<CourseDetails />} />
          <Route path="courses/:courseId/classes/:classId" element={<ClassDetails />} />
          
          <Route path="config" element={<SchoolConfig />} />
          <Route path="schedules" element={<Schedules />} />
          <Route path="my-availability" element={<MyAvailability />} />
          <Route path="service-distribution" element={<ServiceDistribution />} />
        </Route>
      </Routes>
    </Router>
  );
}

export default App;