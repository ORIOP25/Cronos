import React, { Suspense } from 'react'
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import { CSpinner } from '@coreui/react'
import { Show, RedirectToSignIn, useAuth, useOrganization } from '@clerk/react'

import SignInPage from './pages/SignInPage'
import SignUpPage from './pages/SignUpPage'
import CreateOrgPage from './pages/CreateOrgPage'

const Dashboard = React.lazy(() => import('./pages/Dashboard'))
const MyAvailability = React.lazy(() => import('./pages/MyAvailability'))
const MyProgress = React.lazy(() => import('./pages/MyProgress'))
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
const Onboarding = React.lazy(() => import('./pages/Onboarding'))

import DefaultLayout from './components/DefaultLayout'
import { MarketingSite } from './pages/MarketingSite'
import { ROUTE_MY_SCHEDULES } from './roleAccess'

const PageLoader = () => (
  <div className="d-flex justify-content-center align-items-center" style={{ minHeight: '40vh' }}>
    <CSpinner color="primary" />
  </div>
)

function LazyPage({ children }) {
  return <Suspense fallback={<PageLoader />}>{children}</Suspense>
}

function RequireAuth({ children }) {
  const { isSignedIn, isLoaded } = useAuth()
  if (!isLoaded) return <PageLoader />
  if (!isSignedIn) return <RedirectToSignIn />
  return children
}

function RequireAdmin({ children }) {
  const { isSignedIn, isLoaded } = useAuth()
  const { membership } = useOrganization()
  if (!isLoaded) return <PageLoader />
  if (!isSignedIn) return <RedirectToSignIn />
  if (membership?.role !== 'org:admin') return <Navigate to="/login" />
  return children
}

function RequireTeacher({ children }) {
  const { isSignedIn, isLoaded } = useAuth()
  const { membership } = useOrganization()
  if (!isLoaded) return <PageLoader />
  if (!isSignedIn) return <RedirectToSignIn />
  if (membership?.role !== 'org:member') return <Navigate to="/login" />
  return children
}

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={
          <Show when="signed-out" fallback={<Navigate to="/dashboard" />}>
            <MarketingSite />
          </Show>
        } />

        <Route path="/login/*" element={<SignInPage />} />
        <Route path="/register/*" element={<SignUpPage />} />

        <Route path="/create-org" element={
          <RequireAuth><CreateOrgPage /></RequireAuth>
        } />

        <Route path="/onboarding" element={
          <RequireAdmin><LazyPage><Onboarding /></LazyPage></RequireAdmin>
        } />

        <Route element={<RequireAuth><DefaultLayout /></RequireAuth>}>
          <Route path="dashboard" element={<RequireAdmin><LazyPage><Dashboard /></LazyPage></RequireAdmin>} />
          <Route path="teachers" element={<RequireAdmin><LazyPage><Teachers /></LazyPage></RequireAdmin>} />
          <Route path="rooms" element={<RequireAdmin><LazyPage><Rooms /></LazyPage></RequireAdmin>} />
          <Route path="subjects" element={<RequireAdmin><LazyPage><Subjects /></LazyPage></RequireAdmin>} />
          <Route path="courses" element={<RequireAdmin><LazyPage><Courses /></LazyPage></RequireAdmin>} />
          <Route path="courses/:id" element={<RequireAdmin><LazyPage><CourseDetails /></LazyPage></RequireAdmin>} />
          <Route path="courses/:courseId/classes/:classId" element={<RequireAdmin><LazyPage><ClassDetails /></LazyPage></RequireAdmin>} />
          <Route path="courses/:courseId/classes/:classId/subjects" element={<RequireAdmin><LazyPage><ClassSubjects /></LazyPage></RequireAdmin>} />
          <Route path="config" element={<RequireAdmin><LazyPage><SchoolConfig /></LazyPage></RequireAdmin>} />
          <Route path="schedules" element={<RequireAdmin><LazyPage><Schedules /></LazyPage></RequireAdmin>} />
          <Route path={ROUTE_MY_SCHEDULES.slice(1)} element={<RequireTeacher><LazyPage><MySchedules /></LazyPage></RequireTeacher>} />
          <Route path="my-progress" element={<RequireTeacher><LazyPage><MyProgress /></LazyPage></RequireTeacher>} />
          <Route path="schedules/audit" element={<RequireAdmin><LazyPage><ScheduleAuditDashboard /></LazyPage></RequireAdmin>} />
          <Route path="absences" element={<RequireAdmin><LazyPage><Occurrences /></LazyPage></RequireAdmin>} />
          <Route path="timesheets" element={<RequireAdmin><LazyPage><Timesheets /></LazyPage></RequireAdmin>} />
          <Route path="my-availability" element={<RequireTeacher><LazyPage><MyAvailability /></LazyPage></RequireTeacher>} />
        </Route>
      </Routes>
    </Router>
  )
}

export default App
