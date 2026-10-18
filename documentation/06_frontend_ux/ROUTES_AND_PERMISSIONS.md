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
| `/sobre`, `/about` | `pages/marketing/AboutPage.jsx` | Public | Cronos story and founder information |
| `/ajuda` | `pages/marketing/HelpPage.jsx` | Public | Frequently asked questions |
| `/contacto`, `/contact` | `pages/marketing/ContactPage.jsx` | Public | Demonstration request questionnaire |
| `/privacidade`, `/privacy` | `features/legal/LegalDocumentLayout.jsx` | Public (also when signed in) | Privacy policy document |
| `/termos` | `features/legal/LegalDocumentLayout.jsx` | Public | Terms of service document |
| `/dpa` | `features/legal/LegalDocumentLayout.jsx` | Public | Data processing agreement |
| `/cookies` | `features/legal/LegalDocumentLayout.jsx` | Public | Cookies and local storage document |
| `/login/*` | `SignInPage.jsx` | Public | Authentication sign-in view |
| `/register/*` | `SignUpPage.jsx` | Public | Registration view |
| `/recuperar-palavra-passe` | `ForgotPasswordPage.jsx` | Public | Password recovery view |
| `/sign-in/*`, `/sign-up/*` | Redirect | Public | Redirect to `/login` or `/register` |
| `/foundation/waiting` | `FoundationWaiting.jsx` | Signed in | Waiting view for members who cannot manage the foundation |
| `/foundation` | `Foundation.jsx` | Foundation founder | Organization setup wizard |
| `/guide` | `Guide.jsx` | Admin | Optional tutorial guide |
| `/dashboard` | `Dashboard.jsx` | Admin | Administrative command center |
| `/schedules` | `Schedules.jsx` | Admin | Timetable view, read-only proposal preview, and solver trigger |
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
| `/config` | `SchoolConfig.jsx` | Admin | School parameters & shift settings; the post-Foundation settings surface for administrators |
| `/imports` | `BulkImport.jsx` | Admin | Additive CSV validation and atomic commit |
| `*` | `NotFoundPage.jsx` | Public | Not found view (404) |

## Route Guard Logic
Routes use `<RequireAuth>`, `<RequireAdmin>`, `<RequireTeacher>`, `<RequireFoundationAdmin>`, and `<RequireGuide>`:
- `<RequireAuth>` requires a signed-in session with no pending Clerk task.
- A member without admin capability is redirected to its default route from administrative routes.
- A member needs the teacher capability and a linked `teacher_id` for teacher routes.
- A member with both capabilities uses the admin default route.
- `getDefaultRouteForMember` maps `default_mode` `admin` to `/dashboard`, `teacher` to `/my-availability`, and any other value to `/dashboard`.
- `MemberGate` checks the session, organization activation, legal gate, Foundation gate, and capability in that order.

## Contracts and Invariants
- `/courses` offers `Importar CSV` and `Novo Curso`. Assignment imports remain available through `/imports`.
- Signed-out users accessing protected routes are redirected to `/login`.
- A signed-in user without an active organization sees the organization selector.
- The authenticated layout also provides the native Clerk selector to create or switch schools.
- Creating a school opens `/foundation` when the active administrator matches Clerk's organization creator identity. Selecting or leaving a school uses the normal root route guard.
- The demonstration layout hides the selector and cannot change the real active school.
- A pending Clerk organization task uses `/login/tasks/choose-organization` for organization selection only.
- The route gate bootstraps the selected organization and completes current legal acceptance in the background; the destination follows the foundation rules below.
- Foundation completes once per organization.
  An incomplete Foundation sends its active administrator who created the Clerk organization to `/foundation`.
  Every other member waits at `/foundation/waiting`.
  Local `created_by_membership_id` values do not establish the founder.
- A completed Foundation never shows the wizard again.
  An administrator lands on the role default (`/dashboard`), and other members land on their role default route.
  A visit to `/foundation` redirects an administrator to `/config`, the school settings surface.
- `/legal/aceitar` is not a client route.
- Signed-in root visits use `getMemberRoute`, which resolves the completed role default or the foundation landing route.
- Public metadata comes from `features/marketing/content/metadata.js`.

## Failure Modes
- Route Not Found: Accessing invalid path renders `NotFoundPage.jsx` (404 view).

## Verification Procedure
- Log in as a teacher-only user. Open `/config` and verify redirection to `/my-availability`.
- Switch from a personal organization into a completed school as an administrator. Verify the app opens `/dashboard`, not `/foundation`, and that `/foundation` also redirects to `/config`.
- Switch into an incomplete school as a non-founder member and verify `/foundation/waiting`.

## Source Map
- Route Guards: `frontend/src/routeGuards.jsx`
- App Router: `frontend/src/App.jsx`
- Role Access Definition: `frontend/src/roleAccess.js`

## Onboarding Route Contract

The guard order is significant:

1. wait for Clerk authentication;
2. wait for the active organization and membership list;
3. bootstrap or read the current local member;
4. send users without a tenant to the Clerk organization task or selector;
5. complete current legal acceptance in the background for administrators, or show a compact administrator-required state;
6. apply the Foundation gate;
7. apply admin or teacher capability checks.

| Route | Access while Foundation is incomplete | Access after Foundation completion |
| :--- | :--- | :--- |
| `/foundation/waiting` | Signed-in member who is not the foundation founder | Not required; redirects to the member's role default route. |
| `/foundation` | Foundation founder | Foundation founder and any other member; redirects an administrator to `/config` and other members to their role default route. |
| `/guide` | Administrator | Administrator; tutorial remains optional. |
| `/dashboard` | No; normal admin routes are gated | Active administrator. |
| `/my-availability` | No; teacher routes are gated | Active teacher with a linked teacher profile. |

Foundation status is read from the current member and server status.
Only the founder can use the wizard.
`can_manage_foundation` requires an incomplete Foundation, active admin access, and a Clerk user matching the organization's provider-verified `created_by` identity.
A later administrator invited by the founder never owns the wizard.
The backend enforces creator access on the draft and complete endpoints (`backend/app/api/deps.py`) before and after completion.
`/members/me` avoids the provider lookup after completion because no member can manage the one-time wizard then.
Do not implement a client-only bypass for the gate.

## Related Documents
- [Frontend Architecture](FRONTEND_ARCHITECTURE.md)
- [Members and Access](../02_domain_model/MEMBERS_AND_ACCESS.md)
