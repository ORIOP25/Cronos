import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, Outlet } from 'react-router-dom';
import Login from './pages/Login';
import Register from './pages/Register';
import Dashboard from './pages/Dashboard';
import MyAvailability from './pages/MyAvailability';
import MySchedules from './pages/MySchedules';
import Teachers from './pages/Teachers';
import Rooms from './pages/Rooms';
import Subjects from './pages/Subjects';
import SchoolConfig from './pages/SchoolConfig';
import Schedules from './pages/Schedules';
import Occurrences from './pages/Occurrences';
import ScheduleAuditDashboard from './pages/ScheduleAuditDashboard';
import Courses from './pages/Courses';
import CourseDetails from './pages/CourseDetails';
import ClassDetails from './pages/ClassDetails';
import ClassSubjects from './pages/ClassSubjects';
import DefaultLayout from './components/DefaultLayout';
import ProtectedRoute from './components/ProtectedRoute';
import { useAuthStore } from './store';
import { PublicHomeGate } from './pages/MarketingSite';
import {
  USER_ROLE_ADMIN,
  USER_ROLE_TEACHER,
  ROUTE_MY_SCHEDULES,
  getForbiddenRedirectRoute,
} from './roleAccess';

export function AdminOnlyRoute({ children }) {
  const role = useAuthStore((state) => state.user?.role)
  if (role !== USER_ROLE_ADMIN) {
    return (
      <Navigate
        to={getForbiddenRedirectRoute(role)}
        replace
        state={{ accessDeniedMessage: 'Acesso bloqueado: esta área é exclusiva para admin.' }}
      />
    )
  }
  return children
}

export function TeacherOnlyRoute({ children }) {
  const role = useAuthStore((state) => state.user?.role)
  if (role !== USER_ROLE_TEACHER) {
    return (
      <Navigate
        to={getForbiddenRedirectRoute(role)}
        replace
        state={{ accessDeniedMessage: 'Acesso bloqueado: esta área é exclusiva para professor.' }}
      />
    )
  }
  return children
}

function RootLayout() {
  return <Outlet />
}

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />

        <Route element={<RootLayout />}>
          <Route index element={<PublicHomeGate />} />
          {/* Rotas Protegidas (Só com Login) */}
          <Route path="/" element={<ProtectedRoute><DefaultLayout /></ProtectedRoute>}>
          <Route path="dashboard" element={<AdminOnlyRoute><Dashboard /></AdminOnlyRoute>} />
          
        {/* Novas Rotas */}
          <Route path="teachers" element={<AdminOnlyRoute><Teachers /></AdminOnlyRoute>} />
          <Route path="rooms" element={<AdminOnlyRoute><Rooms /></AdminOnlyRoute>} />
          <Route path="subjects" element={<AdminOnlyRoute><Subjects /></AdminOnlyRoute>} />
          
          {/* Cursos com Hierarchia */}
          <Route path="courses" element={<AdminOnlyRoute><Courses /></AdminOnlyRoute>} />
          <Route path="courses/:id" element={<AdminOnlyRoute><CourseDetails /></AdminOnlyRoute>} />
          <Route path="courses/:courseId/classes/:classId" element={<AdminOnlyRoute><ClassDetails /></AdminOnlyRoute>} />
          <Route path="courses/:courseId/classes/:classId/subjects" element={<AdminOnlyRoute><ClassSubjects /></AdminOnlyRoute>} />
          
          <Route path="config" element={<AdminOnlyRoute><SchoolConfig /></AdminOnlyRoute>} />
          <Route path="schedules" element={<AdminOnlyRoute><Schedules /></AdminOnlyRoute>} />
          <Route path={ROUTE_MY_SCHEDULES.slice(1)} element={<TeacherOnlyRoute><MySchedules /></TeacherOnlyRoute>} />
          <Route path="schedules/audit" element={<AdminOnlyRoute><ScheduleAuditDashboard /></AdminOnlyRoute>} />
          <Route path="absences" element={<AdminOnlyRoute><Occurrences /></AdminOnlyRoute>} />
          <Route path="my-availability" element={<TeacherOnlyRoute><MyAvailability /></TeacherOnlyRoute>} />
          </Route>
        </Route>
      </Routes>
    </Router>
  );
}

export default App;