import React, { useEffect } from 'react'
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import { Show, useAuth } from '@clerk/react'

import { setClerkTokenGetter } from './apiClient'

import SignInPage from './pages/SignInPage'
import SignUpPage from './pages/SignUpPage'
import ForgotPasswordPage from './pages/ForgotPasswordPage'
import CreateOrgPage from './pages/CreateOrgPage'
import NotFoundPage from './pages/NotFoundPage'

const Dashboard = React.lazy(() => import('./pages/Dashboard'))
const MyAvailability = React.lazy(() => import('./pages/MyAvailability'))
const MyProgress = React.lazy(() => import('./pages/MyProgress'))
const MySchedules = React.lazy(() => import('./pages/MySchedules'))
const Members = React.lazy(() => import('./pages/Members'))
const Rooms = React.lazy(() => import('./pages/Rooms'))
const Subjects = React.lazy(() => import('./pages/Subjects'))
const SchoolConfig = React.lazy(() => import('./pages/SchoolConfig'))
const Schedules = React.lazy(() => import('./pages/Schedules'))
const Occurrences = React.lazy(() => import('./pages/Occurrences'))
const Timesheets = React.lazy(() => import('./pages/Timesheets'))
const Courses = React.lazy(() => import('./pages/Courses'))
const CourseDetails = React.lazy(() => import('./pages/CourseDetails'))
const ClassDetails = React.lazy(() => import('./pages/ClassDetails'))
const ClassSubjects = React.lazy(() => import('./pages/ClassSubjects'))
const Onboarding = React.lazy(() => import('./pages/Onboarding'))

import DefaultLayout from './components/DefaultLayout'
import { MarketingSite } from './pages/MarketingSite'
import { ROUTE_MY_SCHEDULES } from './roleAccess'
import { LazyPage, RequireAdmin, RequireAuth, RequireTeacher, SignedInRedirect } from './routeGuards'

function App() {
  const { getToken, isLoaded } = useAuth()

  useEffect(() => {
    if (isLoaded && getToken) {
      setClerkTokenGetter(getToken)
    }
  }, [isLoaded, getToken])

  return (
    <Router>
      <Routes>
        <Route path="/" element={
          <Show when="signed-out" fallback={<SignedInRedirect />}>
            <MarketingSite />
          </Show>
        } />

        <Route path="/login/*" element={<SignInPage />} />
        <Route path="/recuperar-palavra-passe" element={<ForgotPasswordPage />} />
        <Route path="/register/*" element={<SignUpPage />} />
        <Route path="/sign-in/*" element={<Navigate to="/login" replace />} />
        <Route path="/sign-up/*" element={<Navigate to="/register" replace />} />

        <Route path="/create-org" element={
          <RequireAuth><CreateOrgPage /></RequireAuth>
        } />

        <Route path="/onboarding" element={
          <RequireAdmin><LazyPage><Onboarding /></LazyPage></RequireAdmin>
        } />

        <Route element={<RequireAuth><DefaultLayout /></RequireAuth>}>
          <Route path="dashboard" element={<RequireAdmin><LazyPage><Dashboard /></LazyPage></RequireAdmin>} />
          <Route path="members" element={<RequireAdmin><LazyPage><Members /></LazyPage></RequireAdmin>} />
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
          <Route path="absences" element={<RequireAdmin><LazyPage><Occurrences /></LazyPage></RequireAdmin>} />
          <Route path="timesheets" element={<RequireAdmin><LazyPage><Timesheets /></LazyPage></RequireAdmin>} />
          <Route path="my-availability" element={<RequireTeacher><LazyPage><MyAvailability /></LazyPage></RequireTeacher>} />
        </Route>

        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </Router>
  )
}

export default App
