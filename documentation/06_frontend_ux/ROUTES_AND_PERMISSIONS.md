# Routes and Permissions

## Purpose
This document specifies application client routes, accessibility controls, and role-based route protection guards.

## Intended Reader
This document targets frontend developers maintaining routes and navigation.

## Prerequisites
Read [Members and Access](../02_domain_model/MEMBERS_AND_ACCESS.md).

## Client Routes Table

| Route Path | Page Component | Access Level | Description |
| :--- | :--- | :--- | :--- |
| `/` | `pages/marketing/HomePage.jsx` | Public | Public landing page for signed-out users |
| `/vantagens` | `pages/marketing/VantagensPage.jsx` | Public | Marketing comparison and benefits |
| `/como-funciona` | `pages/marketing/HowItWorksPage.jsx` | Public | Marketing workflow explanation |
| `/sobre` | `pages/marketing/AboutPage.jsx` | Public | Cronos story and founder information |
| `/ajuda` | `pages/marketing/HelpPage.jsx` | Public | Frequently asked questions |
| `/contacto` | `pages/marketing/ContactPage.jsx` | Public | Demonstration request questionnaire |
| `/login/*` | `SignInPage.jsx` | Public | Authentication sign-in view |
| `/register/*` | `SignUpPage.jsx` | Public | Registration view |
| `/recuperar-palavra-passe` | `ForgotPasswordPage.jsx` | Public | Password recovery view |
| `/foundation` | `Foundation.jsx` | Foundation admin | Organization setup wizard |
| `/create-org` | `CreateOrgPage.jsx` | Authenticated | Organization creation view |
| `/dashboard` | `Dashboard.jsx` | Admin | Administrative command center |
| `/schedules` | `Schedules.jsx` | Admin | Timetable view and solver trigger |
| `/courses` | `Courses.jsx` | Admin | Course catalog management |
| `/courses/:id` | `CourseDetails.jsx` | Admin | Course details and classes list |
| `/courses/:courseId/classes/:classId` | `ClassDetails.jsx` | Admin | Class details view |
| `/courses/:courseId/classes/:classId/subjects` | `ClassSubjects.jsx` | Admin | Class subject assignments |
| `/subjects` | `Subjects.jsx` | Admin | Subject catalog management |
| `/members` | `Members.jsx` | Admin | Team member management (`Equipa`) |
| `/rooms` | `Rooms.jsx` | Admin | Room catalog management |
| `/absences` | `Occurrences.jsx` | Admin | Occurrence and substitution management |
| `/timesheets` | `Timesheets.jsx` | Admin | Weekly timesheet review |
| `/my-schedules` | `MySchedules.jsx` | Teacher | Personal schedule, logs, and week submission |
| `/my-availability` | `MyAvailability.jsx` | Teacher | Teacher availability grid |
| `/my-progress` | `MyProgress.jsx` | Teacher | Teacher assigned class progress |
| `/config` | `SchoolConfig.jsx` | Admin | School parameters & shift settings |

## Route Guard Logic
Routes use `<RequireAdmin>` and `<RequireTeacher>` capability guards:
- A member without admin capability is redirected to its default route from administrative routes.
- A member needs the teacher capability and a linked `teacher_id` for teacher routes.
- A member with both capabilities uses the admin default route.

## Contracts and Invariants
- Signed-out users accessing protected routes are redirected to `/login`.
- A signed-in user without an active organization sees the organization selector or `/create-org`.
- Signed-in root visits use `getDefaultRouteForMember`.
- Public metadata comes from `features/marketing/content/metadata.js`.

## Failure Modes
- Route Not Found: Accessing invalid path renders `NotFoundPage.jsx` (404 view).

## Verification Procedure
Log in as a teacher-only user. Open `/config` and verify redirection to `/my-availability`.

## Source Map
- Route Guards: `frontend/src/routeGuards.jsx`
- App Router: `frontend/src/App.jsx`
- Role Access Definition: `frontend/src/roleAccess.js`

## Related Documents
- [Frontend Architecture](FRONTEND_ARCHITECTURE.md)
- [Members and Access](../02_domain_model/MEMBERS_AND_ACCESS.md)
