// Unit and widget tests for the Clinician Dashboard Screen (Phase 10.2B Remediation).
//
// States covered:
//   1. Findings Present — backend returns elevated safety risk level (CRITICAL, HIGH, MODERATE)
//      or requiresHumanReview=true; renders FindingPresentView
//   2. All Clear — backend returns safety risk level 'LOW' and requiresHumanReview=false; renders AllClearView
//   3. 403 Access Denied — backend returns ForbiddenException; renders AccessDeniedView without retry
//   4. Retryable Error — backend returns NetworkException/ServerException; renders ErrorView with retry
//   5. Loading — provider unresolved; renders LoadingView
//   6. Invalid Patient ID — route parameter malformed; renders EmptyView without fallback to 1
//
// Invariants verified:
//   - Patient X invariant: dashboard for patient X requests and renders data for patient X
//   - Elimination of fabricated metadata: no "Jane Doe", no "Dr. Sarah Lin", no "#JD-",
//     no hardcoded prescription counts, no fake Atorvastatin schedule in AllClearView.

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:medassist/core/api/api_exception.dart';
import 'package:medassist/core/api/generated/api_models.dart';
import 'package:medassist/core/widgets/state_views.dart';
import 'package:medassist/features/clinician/dashboard/clinician_dashboard_screen.dart';
import 'package:medassist/features/clinician/dashboard/state/adherence_analysis_provider.dart';
import 'package:medassist/features/clinician/dashboard/widgets/all_clear_view.dart';
import 'package:medassist/features/clinician/dashboard/widgets/finding_present_view.dart';

AdherenceAnalysisResult _createAnalysis({
  required int patientId,
  required String safetyRiskLevel,
  bool requiresHumanReview = false,
  String recommendedAction = 'Continue current regimen as directed.',
  String summary = 'Patient adheres to regimen on schedule.',
  String whatTheSystemFound = 'No adverse interactions detected.',
  String whyItMatters = 'Maintaining adherence prevents recurrence.',
  String whatToDoNext = 'Take doses as scheduled.',
  String whenToContactCareTeam = 'Contact care team if side effects occur.',
}) =>
    AdherenceAnalysisResult(
      patientId: patientId,
      evaluatedAt: DateTime(2026, 10, 2, 14, 30),
      safetyRiskLevel: safetyRiskLevel,
      requiresHumanReview: requiresHumanReview,
      recommendedAction: recommendedAction,
      patientExplanation: PatientExplanation(
        summary: summary,
        whatTheSystemFound: whatTheSystemFound,
        whyItMatters: whyItMatters,
        whatToDoNext: whatToDoNext,
        whenToContactCareTeam: whenToContactCareTeam,
      ),
      clinicalBrief: ClinicalBrief(
        patientId: patientId,
        period: '7d',
        safetyRiskLevel: safetyRiskLevel,
        requiresHumanReview: requiresHumanReview,
      ),
      validationPassed: true,
    );

Widget _buildApp({
  required int patientId,
  required List<Override> overrides,
}) {
  return ProviderScope(
    overrides: overrides,
    child: MaterialApp(
      home: ClinicianDashboardScreen(patientId: patientId),
    ),
  );
}

void main() {
  group('ClinicianDashboardScreen — 1. Findings Present', () {
    testWidgets('renders FindingPresentView when backend returns CRITICAL risk', (tester) async {
      const patientId = 42;
      final analysis = _createAnalysis(
        patientId: patientId,
        safetyRiskLevel: 'CRITICAL',
        requiresHumanReview: true,
        recommendedAction: 'Immediate discontinuation of Atorvastatin recommended.',
      );

      await tester.pumpWidget(
        _buildApp(
          patientId: patientId,
          overrides: [
            adherenceAnalysisProvider(patientId).overrideWith((ref) async => analysis),
          ],
        ),
      );
      await tester.pumpAndSettle();

      expect(find.byType(FindingPresentView), findsOneWidget);
      expect(find.byType(AllClearView), findsNothing);
      expect(find.text('CRITICALITY: CRITICAL'), findsOneWidget);
      expect(find.text('Immediate discontinuation of Atorvastatin recommended.'), findsOneWidget);

      // Verifies elimination of fabricated metadata
      expect(find.textContaining('Dr. Sarah Lin'), findsNothing);
      expect(find.textContaining('Jane Doe'), findsNothing);
      expect(find.textContaining('#JD-'), findsNothing);
    });

    testWidgets('renders FindingPresentView when backend returns HIGH risk', (tester) async {
      const patientId = 7;
      final analysis = _createAnalysis(
        patientId: patientId,
        safetyRiskLevel: 'HIGH',
        requiresHumanReview: true,
      );

      await tester.pumpWidget(
        _buildApp(
          patientId: patientId,
          overrides: [
            adherenceAnalysisProvider(patientId).overrideWith((ref) async => analysis),
          ],
        ),
      );
      await tester.pumpAndSettle();

      expect(find.byType(FindingPresentView), findsOneWidget);
      expect(find.byType(AllClearView), findsNothing);
      expect(find.text('CRITICALITY: HIGH'), findsOneWidget);
      expect(find.text('Human Review Required: Flagged for Clinician Review'), findsOneWidget);
      expect(find.textContaining('Sarah Lin'), findsNothing);
    });

    testWidgets('renders FindingPresentView when backend returns MODERATE risk', (tester) async {
      const patientId = 15;
      final analysis = _createAnalysis(
        patientId: patientId,
        safetyRiskLevel: 'MODERATE',
        requiresHumanReview: false,
        recommendedAction: 'Monitor patient symptoms and provide educational guidance.',
      );

      await tester.pumpWidget(
        _buildApp(
          patientId: patientId,
          overrides: [
            adherenceAnalysisProvider(patientId).overrideWith((ref) async => analysis),
          ],
        ),
      );
      await tester.pumpAndSettle();

      expect(find.byType(FindingPresentView), findsOneWidget);
      expect(find.byType(AllClearView), findsNothing);
      expect(find.text('CRITICALITY: MODERATE'), findsOneWidget);
      expect(find.text('Monitor patient symptoms and provide educational guidance.'), findsOneWidget);
    });

    testWidgets('renders FindingPresentView when backend returns LOW risk but requiresHumanReview=true', (tester) async {
      const patientId = 23;
      final analysis = _createAnalysis(
        patientId: patientId,
        safetyRiskLevel: 'LOW',
        requiresHumanReview: true,
        recommendedAction: 'Verify adherence report before clearing.',
      );

      await tester.pumpWidget(
        _buildApp(
          patientId: patientId,
          overrides: [
            adherenceAnalysisProvider(patientId).overrideWith((ref) async => analysis),
          ],
        ),
      );
      await tester.pumpAndSettle();

      expect(find.byType(FindingPresentView), findsOneWidget);
      expect(find.byType(AllClearView), findsNothing);
      expect(find.text('CRITICALITY: LOW'), findsOneWidget);
      expect(find.text('Human Review Required: Flagged for Clinician Review'), findsOneWidget);
      expect(find.text('Verify adherence report before clearing.'), findsOneWidget);
    });
  });

  group('ClinicianDashboardScreen — 2. All Clear', () {
    testWidgets('renders AllClearView when backend returns LOW risk and requiresHumanReview=false', (tester) async {
      const patientId = 42;
      final analysis = _createAnalysis(
        patientId: patientId,
        safetyRiskLevel: 'LOW',
        requiresHumanReview: false,
        recommendedAction: 'No significant drug interactions, contraindications, or adherence risks identified.',
      );

      await tester.pumpWidget(
        _buildApp(
          patientId: patientId,
          overrides: [
            adherenceAnalysisProvider(patientId).overrideWith((ref) async => analysis),
          ],
        ),
      );
      await tester.pumpAndSettle();

      expect(find.byType(AllClearView), findsOneWidget);
      expect(find.byType(FindingPresentView), findsNothing);
      expect(find.text('All Clear: No Safety Concerns Detected'), findsOneWidget);
      expect(find.text('STATUS: LOW'), findsOneWidget);
      expect(find.text('No significant drug interactions, contraindications, or adherence risks identified.'), findsOneWidget);

      // Verifies elimination of fabricated metadata and demo content
      expect(find.textContaining('Dr. Lin'), findsNothing);
      expect(find.textContaining('Jane Doe'), findsNothing);
      expect(find.textContaining('Atorvastatin'), findsNothing);
      expect(find.textContaining('3 of 4 doses on track'), findsNothing);
      expect(find.textContaining('4 Prescriptions Verified'), findsNothing);
      expect(find.textContaining('Grapefruit'), findsNothing);
    });
  });

  group('ClinicianDashboardScreen — 3. 403 Access Denied', () {
    testWidgets('renders access-denied state without retry button when backend returns 403', (tester) async {
      const patientId = 99;

      await tester.pumpWidget(
        _buildApp(
          patientId: patientId,
          overrides: [
            adherenceAnalysisProvider(patientId).overrideWith(
              (ref) => Future.error(const ForbiddenException('Clinician not assigned to patient #99.')),
            ),
          ],
        ),
      );
      await tester.pumpAndSettle();

      // Access Denied UI rendered
      expect(find.text('Access Denied'), findsOneWidget);
      expect(
        find.textContaining('You do not have permission to view this patient\'s clinical analysis.'),
        findsOneWidget,
      );
      expect(find.byIcon(Icons.shield_outlined), findsOneWidget);

      // Must NOT render generic ErrorView or retry control
      expect(find.byType(ErrorView), findsNothing);
      expect(find.text('Try again'), findsNothing);
      expect(find.byType(FindingPresentView), findsNothing);
      expect(find.byType(AllClearView), findsNothing);
    });
  });

  group('ClinicianDashboardScreen — 4. Retryable Error', () {
    testWidgets('renders retryable ErrorView with retry button on network error', (tester) async {
      const patientId = 42;

      await tester.pumpWidget(
        _buildApp(
          patientId: patientId,
          overrides: [
            adherenceAnalysisProvider(patientId).overrideWith(
              (ref) => Future.error(const NetworkException('Connection reset by peer.')),
            ),
          ],
        ),
      );
      await tester.pumpAndSettle();

      expect(find.byType(ErrorView), findsOneWidget);
      expect(find.text('Connection reset by peer.'), findsOneWidget);
      expect(find.text('Try again'), findsOneWidget);
      expect(find.byType(FindingPresentView), findsNothing);
      expect(find.byType(AllClearView), findsNothing);
    });

    testWidgets('renders retryable ErrorView with retry button on 500 server error', (tester) async {
      const patientId = 42;

      await tester.pumpWidget(
        _buildApp(
          patientId: patientId,
          overrides: [
            adherenceAnalysisProvider(patientId).overrideWith(
              (ref) => Future.error(const ServerException('Internal server error.')),
            ),
          ],
        ),
      );
      await tester.pumpAndSettle();

      expect(find.byType(ErrorView), findsOneWidget);
      expect(find.text('Internal server error.'), findsOneWidget);
      expect(find.text('Try again'), findsOneWidget);
    });
  });

  group('ClinicianDashboardScreen — 5. Loading State', () {
    testWidgets('renders LoadingView while analysis provider is pending', (tester) async {
      const patientId = 42;

      await tester.pumpWidget(
        _buildApp(
          patientId: patientId,
          overrides: [
            adherenceAnalysisProvider(patientId).overrideWith(
              (ref) => Completer<AdherenceAnalysisResult>().future,
            ),
          ],
        ),
      );
      // Single pump — do not use pumpAndSettle with uncompleted Future
      await tester.pump();

      expect(find.byType(LoadingView), findsOneWidget);
      expect(find.text('Evaluating patient safety...'), findsOneWidget);
    });
  });

  group('ClinicianDashboardScreen — Patient X Invariant', () {
    testWidgets('dashboard for patient 42 requests and renders patient 42, not fallback ID 1', (tester) async {
      const patientId = 42;
      final analysis42 = _createAnalysis(
        patientId: 42,
        safetyRiskLevel: 'LOW',
      );

      await tester.pumpWidget(
        _buildApp(
          patientId: patientId,
          overrides: [
            adherenceAnalysisProvider(42).overrideWith((ref) async => analysis42),
          ],
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('PID: #42'), findsOneWidget);
      expect(find.text('Patient #42'), findsOneWidget);
      expect(find.text('PID: #1'), findsNothing);
      expect(find.text('Patient #1'), findsNothing);
    });

    testWidgets('dashboard for patient 108 requests and renders patient 108', (tester) async {
      const patientId = 108;
      final analysis108 = _createAnalysis(
        patientId: 108,
        safetyRiskLevel: 'HIGH',
        recommendedAction: 'Verify renal clearance for patient 108.',
      );

      await tester.pumpWidget(
        _buildApp(
          patientId: patientId,
          overrides: [
            adherenceAnalysisProvider(108).overrideWith((ref) async => analysis108),
          ],
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('PID: #108'), findsOneWidget);
      expect(find.text('Patient #108'), findsOneWidget);
      expect(find.text('Verify renal clearance for patient 108.'), findsOneWidget);
    });
  });

  group('ClinicianDashboardScreen — Invalid ID Handling', () {
    testWidgets('renders EmptyView when constructed with invalidId without querying provider', (tester) async {
      await tester.pumpWidget(
        const ProviderScope(
          child: MaterialApp(
            home: ClinicianDashboardScreen.invalidId('xyz-not-an-id'),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.byType(EmptyView), findsOneWidget);
      expect(find.text('Invalid Patient Link'), findsOneWidget);
      expect(find.text('"xyz-not-an-id" is not a valid patient reference.'), findsOneWidget);
      expect(find.byType(FindingPresentView), findsNothing);
      expect(find.byType(AllClearView), findsNothing);
      expect(find.byType(ErrorView), findsNothing);
    });

    testWidgets('renders empty detail when invalidId is empty string', (tester) async {
      await tester.pumpWidget(
        const ProviderScope(
          child: MaterialApp(
            home: ClinicianDashboardScreen.invalidId(''),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.byType(EmptyView), findsOneWidget);
      expect(find.text('Invalid Patient Link'), findsOneWidget);
      expect(find.text('No patient ID was provided in the route.'), findsOneWidget);
    });
  });
}
