import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../features/auth/domain/session.dart';
import '../features/auth/presentation/login_screen.dart';
import '../features/auth/presentation/register_screen.dart';
import '../features/auth/presentation/splash_screen.dart';
import '../features/auth/presentation/unsupported_role_screen.dart';
import '../features/auth/state/auth_controller.dart';
import '../features/clinician/dashboard/clinician_dashboard_screen.dart';
import '../features/clinician/dashboard/patient_roster_screen.dart';
import '../features/patient/dashboard/patient_shell_screen.dart';
import '../features/patient/medications/dose_detail_screen.dart';
import '../features/patient/agent/agent_chat_screen.dart';
import '../features/patient/adherence/adherence_analytics_screen.dart';

import '../features/patient/prescriptions/prescription_upload_screen.dart';

/// Every route path, in one place.
class AppRoutes {
  const AppRoutes._();

  static const String splash = '/';
  static const String login = '/login';
  static const String register = '/register';
  static const String unsupportedRole = '/unsupported-role';

  static const String patientDashboard = '/patient';
  static const String patientAgentChat = '/patient/chat';
  static const String patientAdherence = '/patient/adherence';
  static const String patientUpload = '/patient/upload';

  /// One dose from today's schedule, keyed by its schedule id.
  static const String patientDose = '/patient/doses/:scheduleId';
  static String patientDoseOf(int scheduleId) => '/patient/doses/$scheduleId';

  static const String clinicianDashboard = '/clinician';
  static const String clinicianPatientReview = '/clinician/patient/:patientId';
  static String clinicianPatientReviewOf(int patientId) => '/clinician/patient/$patientId';
}

/// Where a signed-in user belongs.
///
/// A role this build cannot classify lands on [AppRoutes.unsupportedRole] rather than
/// falling through to the patient dashboard. The backend's patient endpoints resolve
/// "me" to the caller's own patient record, so an account with no patient profile would
/// see an empty schedule or a 404 and read it as lost data rather than as the wrong
/// destination.
///
/// This used to name CAREGIVER as the motivating case. That role is gone (backend
/// migration `9f2c1d7ab4e0`); the remaining case is [AppRole.unknown], which is what a
/// client older than its backend produces.
String homeRouteFor(AppRole role) {
  if (role.isPatientFacing) return AppRoutes.patientDashboard;
  if (role.isClinicianFacing) return AppRoutes.clinicianDashboard;
  return AppRoutes.unsupportedRole;
}

final routerProvider = Provider<GoRouter>((ref) {
  // go_router needs a Listenable, Riverpod speaks in providers. This bridges the two:
  // every auth-state change bumps the notifier, which re-runs `redirect`.
  final refresh = ValueNotifier<int>(0);
  ref.listen<AuthState>(authControllerProvider, (previous, next) => refresh.value++);
  ref.onDispose(refresh.dispose);

  return GoRouter(
    initialLocation: AppRoutes.splash,
    refreshListenable: refresh,
    debugLogDiagnostics: kDebugMode,

    // The single authority on who may be where. Screens never redirect on their own —
    // one place to reason about, and a login screen that cannot forget to navigate.
    redirect: (context, state) {
      final auth = ref.read(authControllerProvider);
      final location = state.matchedLocation;

      switch (auth) {
        case AuthRestoring():
          // Hold on the splash until the stored session has been confirmed. Anything
          // else would flash a login screen at someone who is already signed in.
          return location == AppRoutes.splash ? null : AppRoutes.splash;

        case AuthSignedOut():
          const permitted = {AppRoutes.login, AppRoutes.register};
          return permitted.contains(location) ? null : AppRoutes.login;

        case AuthSignedIn(session: final session):
          final home = homeRouteFor(session.role);

          // Signed in, but sitting on a pre-auth route: go home.
          const preAuth = {AppRoutes.splash, AppRoutes.login, AppRoutes.register};
          if (preAuth.contains(location)) return home;

          // An unroutable role is pinned to its dead end. `homeRouteFor` already
          // returns `unsupportedRole` for it, so `home` is that screen — the branch
          // exists to stop the cross-role guards below from being consulted for a role
          // that satisfies neither of them.
          if (session.role == AppRole.unknown) {
            return location == AppRoutes.unsupportedRole ? null : home;
          }

          // Cross-role guard. Deep links and back-stack entries survive a sign-out and
          // sign-in as a different person, so this cannot be left to the menus.
          if (location.startsWith(AppRoutes.patientDashboard) &&
              !session.role.isPatientFacing) {
            return home;
          }
          if (location.startsWith(AppRoutes.clinicianDashboard) &&
              !session.role.isClinicianFacing) {
            return home;
          }
          return null;
      }
    },
    routes: [
      GoRoute(
        path: AppRoutes.splash,
        builder: (context, state) => const SplashScreen(),
      ),
      GoRoute(
        path: AppRoutes.login,
        builder: (context, state) => const LoginScreen(),
      ),
      GoRoute(
        path: AppRoutes.register,
        builder: (context, state) => const RegisterScreen(),
      ),
      GoRoute(
        path: AppRoutes.unsupportedRole,
        builder: (context, state) => const UnsupportedRoleScreen(),
      ),
      GoRoute(
        path: AppRoutes.patientDashboard,
        builder: (context, state) => const PatientShellScreen(),
        routes: [
          GoRoute(
            // Relative to the parent, so 'doses/:scheduleId' rather than the full path.
            path: 'doses/:scheduleId',
            builder: (context, state) {
              final raw = state.pathParameters['scheduleId'];
              final scheduleId = int.tryParse(raw ?? '');
              if (scheduleId == null) {
                // A malformed deep link, not a backend problem. Reported rather than
                // crashing on a null assertion.
                return DoseDetailScreen.invalidId(raw);
              }
              return DoseDetailScreen(scheduleId: scheduleId);
            },
          ),
          GoRoute(
            path: 'chat',
            builder: (context, state) => const AgentChatScreen(),
          ),
          GoRoute(
            path: 'adherence',
            builder: (context, state) => const AdherenceAnalyticsScreen(),
          ),
          GoRoute(
            path: 'upload',
            builder: (context, state) => const PrescriptionUploadScreen(),
          ),
        ],
      ),
      GoRoute(
        path: AppRoutes.clinicianDashboard,
        builder: (context, state) => const PatientRosterScreen(),
        routes: [
          GoRoute(
            path: 'patient/:patientId',
            builder: (context, state) {
              final raw = state.pathParameters['patientId'];
              final patientId = int.tryParse(raw ?? '');
              if (patientId == null) {
                return ClinicianDashboardScreen.invalidId(raw);
              }
              return ClinicianDashboardScreen(patientId: patientId);
            },
          ),
        ],
      ),
    ],
  );
});
