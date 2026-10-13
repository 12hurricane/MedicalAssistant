// Unit and router integration tests for clinician patient review routes.
//
// Invariants verified:
//   - /clinician/patient/42 resolves to ClinicianDashboardScreen with patientId 42
//   - /clinician/patient/108 resolves to ClinicianDashboardScreen with patientId 108
//   - malformed patient ID (e.g., 'abc') does NOT silently become 1
//   - missing/non-numeric patient ID does NOT silently become 1

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:medassist/app/router.dart';
import 'package:medassist/core/api/generated/api_models.dart';
import 'package:medassist/features/auth/domain/session.dart';
import 'package:medassist/features/auth/state/auth_controller.dart';
import 'package:medassist/features/clinician/dashboard/clinician_dashboard_screen.dart';
import 'package:medassist/features/clinician/dashboard/state/adherence_analysis_provider.dart';

final mockClinicianSession = Session.fromUser(
  UserResponse(
    id: 10,
    name: 'Dr. Test Clinician',
    email: 'clinician@test.com',
    role: 'CLINICIAN',
    isActive: true,
    createdAt: DateTime(2026, 1, 1),
  ),
);

class MockClinicianAuthController extends AuthController {
  @override
  AuthState build() => AuthSignedIn(mockClinicianSession);
}

AdherenceAnalysisResult _createAnalysis(int patientId) => AdherenceAnalysisResult(
      patientId: patientId,
      evaluatedAt: DateTime(2026, 10, 2, 14, 30),
      safetyRiskLevel: 'LOW',
      requiresHumanReview: false,
      recommendedAction: 'All clear.',
      patientExplanation: const PatientExplanation(
        summary: 'Summary.',
        whatTheSystemFound: 'Findings.',
        whyItMatters: 'Context.',
        whatToDoNext: 'Next.',
        whenToContactCareTeam: 'Contact.',
      ),
      clinicalBrief: ClinicalBrief(
        patientId: patientId,
        period: '7d',
        safetyRiskLevel: 'LOW',
        requiresHumanReview: false,
      ),
      validationPassed: true,
    );

void main() {
  group('Clinician Router — Patient ID Invariant', () {
    testWidgets('route /clinician/patient/42 resolves to dashboard with patientId 42', (tester) async {
      final container = ProviderContainer(
        overrides: [
          authControllerProvider.overrideWith(() => MockClinicianAuthController()),
          adherenceAnalysisProvider(42).overrideWith((ref) async => _createAnalysis(42)),
        ],
      );
      addTearDown(container.dispose);

      final router = container.read(routerProvider);

      await tester.pumpWidget(
        UncontrolledProviderScope(
          container: container,
          child: MaterialApp.router(
            routerConfig: router,
          ),
        ),
      );
      router.go('/clinician/patient/42');
      await tester.pumpAndSettle();

      expect(find.byType(ClinicianDashboardScreen), findsOneWidget);
      final screen = tester.widget<ClinicianDashboardScreen>(find.byType(ClinicianDashboardScreen));
      expect(screen.patientId, 42);
      expect(screen.invalidRawId, isNull);
    });

    testWidgets('route /clinician/patient/108 resolves to dashboard with patientId 108', (tester) async {
      final container = ProviderContainer(
        overrides: [
          authControllerProvider.overrideWith(() => MockClinicianAuthController()),
          adherenceAnalysisProvider(108).overrideWith((ref) async => _createAnalysis(108)),
        ],
      );
      addTearDown(container.dispose);

      final router = container.read(routerProvider);

      await tester.pumpWidget(
        UncontrolledProviderScope(
          container: container,
          child: MaterialApp.router(
            routerConfig: router,
          ),
        ),
      );
      router.go('/clinician/patient/108');
      await tester.pumpAndSettle();

      expect(find.byType(ClinicianDashboardScreen), findsOneWidget);
      final screen = tester.widget<ClinicianDashboardScreen>(find.byType(ClinicianDashboardScreen));
      expect(screen.patientId, 108);
      expect(screen.invalidRawId, isNull);
    });

    testWidgets('malformed patient ID "abc" does NOT become patient 1', (tester) async {
      final container = ProviderContainer(
        overrides: [
          authControllerProvider.overrideWith(() => MockClinicianAuthController()),
        ],
      );
      addTearDown(container.dispose);

      final router = container.read(routerProvider);

      await tester.pumpWidget(
        UncontrolledProviderScope(
          container: container,
          child: MaterialApp.router(
            routerConfig: router,
          ),
        ),
      );
      router.go('/clinician/patient/abc');
      await tester.pumpAndSettle();

      expect(find.byType(ClinicianDashboardScreen), findsOneWidget);
      final screen = tester.widget<ClinicianDashboardScreen>(find.byType(ClinicianDashboardScreen));
      expect(screen.patientId, isNot(1));
      expect(screen.patientId, -1);
      expect(screen.invalidRawId, 'abc');

      expect(find.text('Invalid Patient Link'), findsOneWidget);
      expect(find.text('"abc" is not a valid patient reference.'), findsOneWidget);
      expect(find.text('PID: #1'), findsNothing);
      expect(find.text('Patient #1'), findsNothing);
    });

    testWidgets('missing or non-numeric patient ID does NOT resolve to patient 1', (tester) async {
      final container = ProviderContainer(
        overrides: [
          authControllerProvider.overrideWith(() => MockClinicianAuthController()),
        ],
      );
      addTearDown(container.dispose);

      final router = container.read(routerProvider);

      await tester.pumpWidget(
        UncontrolledProviderScope(
          container: container,
          child: MaterialApp.router(
            routerConfig: router,
          ),
        ),
      );
      router.go('/clinician/patient/invalid-ref');
      await tester.pumpAndSettle();

      expect(find.byType(ClinicianDashboardScreen), findsOneWidget);
      final screen = tester.widget<ClinicianDashboardScreen>(find.byType(ClinicianDashboardScreen));
      expect(screen.patientId, isNot(1));
      expect(screen.invalidRawId, 'invalid-ref');

      expect(find.text('Invalid Patient Link'), findsOneWidget);
      expect(find.text('"invalid-ref" is not a valid patient reference.'), findsOneWidget);
      expect(find.text('PID: #1'), findsNothing);
    });
  });
}
