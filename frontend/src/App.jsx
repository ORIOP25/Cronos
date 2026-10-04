import { lazy, Suspense, useEffect, useRef } from 'react'
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import { useAuth, useOrganization } from '@clerk/react'
import { toast } from 'react-hot-toast'

import { setClerkTokenGetter } from './apiClient'

import SignInPage from './pages/SignInPage'
import SignUpPage from './pages/SignUpPage'
import ForgotPasswordPage from './pages/ForgotPasswordPage'
import NotFoundPage from './pages/NotFoundPage'

const Dashboard = lazy(() => import('./pages/Dashboard'))
const MyAvailability = lazy(() => import('./pages/MyAvailability'))
const MyProgress = lazy(() => import('./pages/MyProgress'))
const MySchedules = lazy(() => import('./pages/MySchedules'))
const Members = lazy(() => import('./pages/Members'))
const Rooms = lazy(() => import('./pages/Rooms'))
const Subjects = lazy(() => import('./pages/Subjects'))
const SchoolConfig = lazy(() => import('./pages/SchoolConfig'))
const Schedules = lazy(() => import('./pages/Schedules'))
const Occurrences = lazy(() => import('./pages/Occurrences'))
const Timesheets = lazy(() => import('./pages/Timesheets'))
const Courses = lazy(() => import('./pages/Courses'))
const CourseDetails = lazy(() => import('./pages/CourseDetails'))
const ClassDetails = lazy(() => import('./pages/ClassDetails'))
const ClassSubjects = lazy(() => import('./pages/ClassSubjects'))
const BulkImport = lazy(() => import('./pages/BulkImport'))
const Foundation = lazy(() => import('./pages/Foundation'))
const FoundationWaiting = lazy(() => import('./pages/FoundationWaiting'))
const Guide = lazy(() => import('./pages/Guide'))
const LegalDocumentLayout = lazy(() => import('./features/legal/LegalDocumentLayout.jsx'))

const MarketingLayout = lazy(() => import('./features/marketing/components/layout/MarketingLayout.jsx'))
const HomePage = lazy(() => import('./pages/marketing/HomePage.jsx'))
const VantagensPage = lazy(() => import('./pages/marketing/VantagensPage.jsx'))
const HowItWorksPage = lazy(() => import('./pages/marketing/HowItWorksPage.jsx'))
const AboutPage = lazy(() => import('./pages/marketing/AboutPage.jsx'))
const HelpPage = lazy(() => import('./pages/marketing/HelpPage.jsx'))
const ContactPage = lazy(() => import('./pages/marketing/ContactPage.jsx'))

import DefaultLayout from './components/DefaultLayout'
import { ROUTE_MY_SCHEDULES } from './roleAccess'
import { PageLoader, RequireAdmin, RequireFoundationAdmin, RequireAuth, RequireTeacher } from './routeGuards'
import { clearStorageKeys } from './utils/expiringStorage'

function useStorageScopeCleanup(userId, isSignedIn, organizationId) {
  const previousUserId = useRef(userId)
  const previousOrganizationId = useRef(organizationId)
  useEffect(() => {
    const previousUser = previousUserId.current
    const previousOrganization = previousOrganizationId.current
    const userChanged = Boolean(previousUser) && (!isSignedIn || previousUser !== userId)
    const organizationChanged = Boolean(previousOrganization) && previousOrganization !== organizationId
    if (userChanged) {
      clearStorageKeys(localStorage, (key) => key.includes(`:user:${previousUser}:`))
    }
    if (organizationChanged) {
      clearStorageKeys(localStorage, (key) => key.includes(`:org:${previousOrganization}`) || key.endsWith(`-org-${previousOrganization}`))
    }
    if (userChanged || organizationChanged) toast.removeAll()
    previousUserId.current = userId
    previousOrganizationId.current = organizationId
  }, [isSignedIn, organizationId, userId])
}

function App() {
  const { getToken, isLoaded, userId, isSignedIn } = useAuth()
  const { organization } = useOrganization()
  useStorageScopeCleanup(userId, isSignedIn, organization?.id)

  useEffect(() => {
    if (isLoaded && getToken) {
      setClerkTokenGetter(getToken)
      return () => setClerkTokenGetter(() => Promise.resolve(null))
    }
    return undefined
  }, [isLoaded, getToken])

  return (
    <Router>
      <Suspense fallback={<PageLoader />}>
        <Routes>
          <Route element={<MarketingLayout />}>
            <Route path="/" element={<HomePage />} />
            <Route path="/vantagens" element={<VantagensPage />} />
            <Route path="/como-funciona" element={<HowItWorksPage />} />
            <Route path="/sobre" element={<AboutPage />} />
            <Route path="/about" element={<AboutPage />} />
            <Route path="/ajuda" element={<HelpPage />} />
            <Route path="/contacto" element={<ContactPage />} />
            <Route path="/contact" element={<ContactPage />} />
          </Route>

          <Route element={<MarketingLayout allowSignedIn />}>
            <Route path="/privacidade" element={<LegalDocumentLayout kind="privacy" />} />
            <Route path="/privacy" element={<LegalDocumentLayout kind="privacy" />} />
            <Route path="/termos" element={<LegalDocumentLayout kind="terms" />} />
            <Route path="/dpa" element={<LegalDocumentLayout kind="dpa" />} />
            <Route path="/cookies" element={<LegalDocumentLayout kind="cookies" />} />
          </Route>

          <Route path="/login/*" element={<SignInPage />} />
          <Route path="/recuperar-palavra-passe" element={<ForgotPasswordPage />} />
          <Route path="/register/*" element={<SignUpPage />} />
          <Route path="/sign-in/*" element={<Navigate to="/login" replace />} />
          <Route path="/sign-up/*" element={<Navigate to="/register" replace />} />

          <Route path="/foundation/waiting" element={
            <RequireAuth><FoundationWaiting /></RequireAuth>
          } />

          <Route path="/foundation" element={
            <RequireFoundationAdmin><Foundation /></RequireFoundationAdmin>
          } />
          <Route path="/guide" element={<RequireFoundationAdmin><Guide /></RequireFoundationAdmin>} />

          <Route element={<RequireAuth><DefaultLayout /></RequireAuth>}>
            <Route element={<RequireAdmin />}>
              <Route path="dashboard" element={<Dashboard />} />
              <Route path="members" element={<Members />} />
              <Route path="rooms" element={<Rooms />} />
              <Route path="subjects" element={<Subjects />} />
              <Route path="courses" element={<Courses />} />
              <Route path="courses/:id" element={<CourseDetails />} />
              <Route path="courses/:courseId/classes/:classId" element={<ClassDetails />} />
              <Route path="courses/:courseId/classes/:classId/subjects" element={<ClassSubjects />} />
              <Route path="config" element={<SchoolConfig />} />
              <Route path="schedules" element={<Schedules />} />
              <Route path="absences" element={<Occurrences />} />
              <Route path="timesheets" element={<Timesheets />} />
              <Route path="imports" element={<BulkImport />} />
            </Route>
            <Route element={<RequireTeacher />}>
              <Route path={ROUTE_MY_SCHEDULES.slice(1)} element={<MySchedules />} />
              <Route path="my-progress" element={<MyProgress />} />
              <Route path="my-availability" element={<MyAvailability />} />
            </Route>
          </Route>

          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </Suspense>
    </Router>
  )
}

export default App
