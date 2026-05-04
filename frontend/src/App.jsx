import React, { Suspense } from 'react'
import { BrowserRouter as Router, Routes, Route, Navigate, Outlet } from 'react-router-dom'
import { CSpinner } from '@coreui/react'

// Páginas públicas (sem lazy — carregamento imediato)
import Login from './pages/Login'
import Register from './pages/Register'

// Páginas protegidas com code splitting
const Dashboard = React.lazy(() => import('./pages/Dashboard'))
const MyAvailability = React.lazy(() => import('./pages/MyAvailability'))
const MySchedules = React.lazy(() => import('./pages/MySchedules'))
const Teachers = React.lazy(() => import('./pages/Teachers'))
const Rooms = React.lazy(() => import('./pages/Rooms'))
const Subjects = React.lazy(() => import('./pages/Subjects'))
const SchoolConfig = React.lazy(() => import('./pages/SchoolConfig'))
const Schedules = React.lazy(() => import('./pages/Schedules'))
const Occurrences = React.lazy(() => import('./pages/Occurrences'))
const Timesheets = React.lazy(() => import('./pages/Timesheets'))
const ScheduleAuditDashboard = React.lazy(() => import('./pages/ScheduleAuditDashboard'))
const Courses = React.lazy(() => import('./pages/Courses'))
const CourseDetails = React.lazy(() => import('./pages/CourseDetails'))
const ClassDetails = React.lazy(() => import('./pages/ClassDetails'))
const ClassSubjects = React.lazy(() => import('./pages/ClassSubjects'))

import DefaultLayout from './components/DefaultLayout'
import ProtectedRoute from './components/ProtectedRoute'
import { useAuthStore } from './store'
import { PublicHomeGate } from './pages/MarketingSite'
import {
  USER_ROLE_ADMIN,
  USER_ROLE_TEACHER,
  ROUTE_MY_SCHEDULES,
  getForbiddenRedirectRoute,
} from './roleAccess'

const PageLoader = () => (
  <div className="d-flex justify-content-center align-items-center" style={{ minHeight: '40vh' }}>
    <CSpinner color="primary" />
  </div>
)

function LazyPage({ children }) {
  return <Suspense fallback={<PageLoader />}>{children}</Suspense>
}

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
          <Route path="/" element={<ProtectedRoute><DefaultLayout /></ProtectedRoute>}>
            <Route path="dashboard" element={<AdminOnlyRoute><LazyPage><Dashboard /></LazyPage></AdminOnlyRoute>} />
            <Route path="teachers" element={<AdminOnlyRoute><LazyPage><Teachers /></LazyPage></AdminOnlyRoute>} />
            <Route path="rooms" element={<AdminOnlyRoute><LazyPage><Rooms /></LazyPage></AdminOnlyRoute>} />
            <Route path="subjects" element={<AdminOnlyRoute><LazyPage><Subjects /></LazyPage></AdminOnlyRoute>} />
            <Route path="courses" element={<AdminOnlyRoute><LazyPage><Courses /></LazyPage></AdminOnlyRoute>} />
            <Route path="courses/:id" element={<AdminOnlyRoute><LazyPage><CourseDetails /></LazyPage></AdminOnlyRoute>} />
            <Route path="courses/:courseId/classes/:classId" element={<AdminOnlyRoute><LazyPage><ClassDetails /></LazyPage></AdminOnlyRoute>} />
            <Route path="courses/:courseId/classes/:classId/subjects" element={<AdminOnlyRoute><LazyPage><ClassSubjects /></LazyPage></AdminOnlyRoute>} />
            <Route path="config" element={<AdminOnlyRoute><LazyPage><SchoolConfig /></LazyPage></AdminOnlyRoute>} />
            <Route path="schedules" element={<AdminOnlyRoute><LazyPage><Schedules /></LazyPage></AdminOnlyRoute>} />
            <Route path={ROUTE_MY_SCHEDULES.slice(1)} element={<TeacherOnlyRoute><LazyPage><MySchedules /></LazyPage></TeacherOnlyRoute>} />
            <Route path="schedules/audit" element={<AdminOnlyRoute><LazyPage><ScheduleAuditDashboard /></LazyPage></AdminOnlyRoute>} />
            <Route path="absences" element={<AdminOnlyRoute><LazyPage><Occurrences /></LazyPage></AdminOnlyRoute>} />
            <Route path="timesheets" element={<AdminOnlyRoute><LazyPage><Timesheets /></LazyPage></AdminOnlyRoute>} />
            <Route path="my-availability" element={<TeacherOnlyRoute><LazyPage><MyAvailability /></LazyPage></TeacherOnlyRoute>} />
          </Route>
        </Route>
      </Routes>
    </Router>
  )
}

export default App
