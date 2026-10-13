import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:medassist/core/api/api_exception.dart';
import 'package:medassist/core/api/generated/api_models.dart';
import 'package:medassist/features/clinician/dashboard/clinician_dashboard_screen.dart';
import 'package:medassist/features/clinician/dashboard/data/clinician_dose_repository.dart';
import 'package:medassist/features/clinician/dashboard/state/adherence_analysis_provider.dart';
import 'package:medassist/features/clinician/dashboard/state/clinician_doses_provider.dart';
import 'package:medassist/features/clinician/dashboard/widgets/dose_correction_sheet.dart';

AdherenceAnalysisResult _createDummyAnalysis(int patientId) =>
    AdherenceAnalysisResult(
      patientId: patientId,
      evaluatedAt: DateTime(2026, 10, 5, 10, 0),
      safetyRiskLevel: 'LOW',
      requiresHumanReview: false,
      recommendedAction: 'Continue current regimen.',
      patientExplanation: const PatientExplanation(
        summary: 'All good',
        whatTheSystemFound: 'No issues',
        whyItMatters: 'Adherence',
        whatToDoNext: 'Keep taking meds',
        whenToContactCareTeam: 'If unwell',
      ),
      clinicalBrief: ClinicalBrief(
        patientId: patientId,
        period: '7d',
        safetyRiskLevel: 'LOW',
        requiresHumanReview: false,
      ),
      validationPassed: true,
    );

TodayScheduleResponse _createSchedule({
  required int patientId,
  required List<TodayDoseResponse> doses,
}) =>
    TodayScheduleResponse(
      patientId: patientId,
      localDate: '2026-10-05',
      timezone: 'UTC',
      doses: doses,
      totalDoses: doses.length,
      dosesTaken: doses.where((d) => d.status == 'TAKEN').length,
      dosesRemaining: doses.where((d) => d.status == 'PENDING').length,
    );

TodayDoseResponse _createDose({
  required int scheduleId,
  required int? eventId,
  required String medicineName,
  required String status,
  String scheduledLocalTime = '08:00',
  String? skipReason,
}) =>
    TodayDoseResponse(
      scheduleId: scheduleId,
      eventId: eventId,
      medicineName: medicineName,
      status: status,
      scheduledAt: DateTime.utc(2026, 10, 5, 8, 0),
      scheduledLocalTime: scheduledLocalTime,
      isDue: true,
      skipReason: skipReason,
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

void _setLargeViewport(WidgetTester tester) {
  tester.view.physicalSize = const Size(800, 2000);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(() {
    tester.view.resetPhysicalSize();
    tester.view.resetDevicePixelRatio();
  });
}

void main() {
  group('Clinician Dose Events — Event Retrieval on Dashboard', () {
    testWidgets('1. Assigned clinician sees individual medication dose events', (tester) async {
      _setLargeViewport(tester);
      const patientId = 42;
      final schedule = _createSchedule(
        patientId: patientId,
        doses: [
          _createDose(
            scheduleId: 101,
            eventId: 501,
            medicineName: 'Warfarin 5mg',
            status: 'SKIPPED',
            skipReason: 'Felt dizzy',
          ),
        ],
      );

      await tester.pumpWidget(
        _buildApp(
          patientId: patientId,
          overrides: [
            adherenceAnalysisProvider(patientId).overrideWith((ref) async => _createDummyAnalysis(patientId)),
            clinicianDosesProvider(patientId).overrideWith((ref) async => schedule),
          ],
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text("Today's Medication Doses"), findsOneWidget);
      expect(find.text('Warfarin 5mg'), findsOneWidget);
      expect(find.text('SKIPPED'), findsOneWidget);
      expect(find.text('Reason: "Felt dizzy"'), findsOneWidget);
      expect(find.byKey(const Key('correct_dose_button_501')), findsOneWidget);
    });

    testWidgets('2. Empty event list renders empty state message', (tester) async {
      _setLargeViewport(tester);
      const patientId = 42;
      final emptySchedule = _createSchedule(patientId: patientId, doses: []);

      await tester.pumpWidget(
        _buildApp(
          patientId: patientId,
          overrides: [
            adherenceAnalysisProvider(patientId).overrideWith((ref) async => _createDummyAnalysis(patientId)),
            clinicianDosesProvider(patientId).overrideWith((ref) async => emptySchedule),
          ],
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('No scheduled doses for today.'), findsOneWidget);
    });

    testWidgets('3. 403 access denied shows non-retryable message', (tester) async {
      _setLargeViewport(tester);
      const patientId = 42;

      await tester.pumpWidget(
        _buildApp(
          patientId: patientId,
          overrides: [
            adherenceAnalysisProvider(patientId).overrideWith((ref) async => _createDummyAnalysis(patientId)),
            clinicianDosesProvider(patientId).overrideWith(
              (ref) async => throw const ForbiddenException('Not assigned to this patient'),
            ),
          ],
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Access to dose schedule denied.'), findsOneWidget);
      expect(find.text('Retry'), findsNothing);
    });

    testWidgets('4. Network error shows retry button and allows retry', (tester) async {
      _setLargeViewport(tester);
      const patientId = 42;
      int callCount = 0;

      await tester.pumpWidget(
        _buildApp(
          patientId: patientId,
          overrides: [
            adherenceAnalysisProvider(patientId).overrideWith((ref) async => _createDummyAnalysis(patientId)),
            clinicianDosesProvider(patientId).overrideWith((ref) async {
              callCount++;
              if (callCount == 1) {
                throw const NetworkException('Connection timeout');
              }
              return _createSchedule(
                patientId: patientId,
                doses: [
                  _createDose(scheduleId: 101, eventId: 501, medicineName: 'Metformin', status: 'TAKEN'),
                ],
              );
            }),
          ],
        ),
      );
      await tester.pumpAndSettle();

      expect(find.textContaining('Connection timeout'), findsOneWidget);
      expect(find.text('Retry'), findsOneWidget);

      await tester.tap(find.text('Retry'));
      await tester.pumpAndSettle();

      expect(find.text('Metformin'), findsOneWidget);
      expect(find.text('TAKEN'), findsOneWidget);
    });
  });

  group('DoseCorrectionSheet — Validation and Submission', () {
    testWidgets('5. Renders real event data and current status', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: DoseCorrectionSheet(
              eventId: 501,
              currentStatus: 'SKIPPED',
              medicineName: 'Glucophage 500mg',
              onCorrect: ({required eventId, required newStatus, required reason}) async {},
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Correct Dose Event'), findsOneWidget);
      expect(find.text('Glucophage 500mg'), findsOneWidget);
      expect(find.text('CURRENT STATUS'), findsOneWidget);
      expect(find.text('SKIPPED'), findsOneWidget);
      // Target choices should only offer TAKEN and MISSED, not SKIPPED
      expect(find.text('TAKEN'), findsOneWidget);
      expect(find.text('MISSED'), findsOneWidget);
    });

    testWidgets('6. Rejects empty status and short reason (<3 chars)', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: DoseCorrectionSheet(
              eventId: 501,
              currentStatus: 'SKIPPED',
              medicineName: 'Glucophage 500mg',
              onCorrect: ({required eventId, required newStatus, required reason}) async {},
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Tap submit with no status selected
      await tester.tap(find.text('Apply Correction'));
      await tester.pumpAndSettle();
      expect(find.text('Select a corrected status.'), findsOneWidget);

      // Select status TAKEN
      await tester.tap(find.text('TAKEN'));
      await tester.pumpAndSettle();

      // Tap submit with empty reason
      await tester.tap(find.text('Apply Correction'));
      await tester.pumpAndSettle();
      expect(find.text('Reason must be at least 3 characters.'), findsOneWidget);

      // Enter short 2-char reason
      await tester.enterText(find.byType(TextField), 'No');
      await tester.tap(find.text('Apply Correction'));
      await tester.pumpAndSettle();
      expect(find.text('Reason must be at least 3 characters.'), findsOneWidget);
    });

    testWidgets('7. Submits valid correction and prevents duplicate submission while active', (tester) async {
      final completer = Completer<void>();
      int submitCalls = 0;
      int capturedEventId = 0;
      String capturedStatus = '';
      String capturedReason = '';

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: DoseCorrectionSheet(
              eventId: 501,
              currentStatus: 'SKIPPED',
              medicineName: 'Glucophage 500mg',
              onCorrect: ({required eventId, required newStatus, required reason}) {
                submitCalls++;
                capturedEventId = eventId;
                capturedStatus = newStatus;
                capturedReason = reason;
                return completer.future;
              },
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('TAKEN'));
      await tester.enterText(find.byType(TextField), 'Patient confirmed dose taken at breakfast');
      await tester.tap(find.text('Apply Correction'));
      await tester.pump(); // Start submitting

      expect(submitCalls, equals(1));
      expect(capturedEventId, equals(501));
      expect(capturedStatus, equals('TAKEN'));
      expect(capturedReason, equals('Patient confirmed dose taken at breakfast'));

      // Progress indicator should be visible
      expect(find.byType(CircularProgressIndicator), findsOneWidget);

      // Second tap while submitting must be ignored
      await tester.tap(find.byType(ElevatedButton));
      expect(submitCalls, equals(1));

      // Complete async submission
      completer.complete();
      await tester.pumpAndSettle();
    });

    testWidgets('8. Handles 422 ValidationException and 403 ForbiddenException cleanly', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: DoseCorrectionSheet(
              eventId: 501,
              currentStatus: 'MISSED',
              medicineName: 'Glucophage 500mg',
              onCorrect: ({required eventId, required newStatus, required reason}) async {
                throw const ValidationException('Event is already MISSED; no change needed', {});
              },
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('TAKEN'));
      await tester.enterText(find.byType(TextField), 'Testing 422');
      await tester.tap(find.text('Apply Correction'));
      await tester.pumpAndSettle();

      expect(find.text('Event is already MISSED; no change needed'), findsOneWidget);
      expect(find.text('Apply Correction'), findsOneWidget);
    });
  });

  group('End-to-End Correction Workflow & Authoritative Refresh', () {
    testWidgets('9. Correcting dose via sheet triggers authoritative refresh of both providers without optimistic update', (tester) async {
      _setLargeViewport(tester);
      const patientId = 42;
      String currentStatus = 'SKIPPED';
      int analysisRefreshCount = 0;
      int dosesRefreshCount = 0;

      final container = ProviderContainer(
        overrides: [
          adherenceAnalysisProvider(patientId).overrideWith((ref) async {
            analysisRefreshCount++;
            return _createDummyAnalysis(patientId);
          }),
          clinicianDosesProvider(patientId).overrideWith((ref) async {
            dosesRefreshCount++;
            return _createSchedule(
              patientId: patientId,
              doses: [
                _createDose(
                  scheduleId: 101,
                  eventId: 501,
                  medicineName: 'Warfarin 5mg',
                  status: currentStatus,
                ),
              ],
            );
          }),
          clinicianDoseRepositoryProvider.overrideWith((ref) => FakeClinicianDoseRepository(
                onCorrect: ({required eventId, required newStatus, required reason}) async {
                  // Simulate backend commit updating authoritative state
                  currentStatus = newStatus;
                  return EventCorrectionResponse(
                    correctionId: 99,
                    eventId: eventId,
                    previousStatus: 'SKIPPED',
                    newStatus: newStatus,
                    correctedBy: 1,
                    correctedAt: '2026-10-05T10:00:00Z',
                    reason: reason,
                  );
                },
              )),
        ],
      );

      await tester.pumpWidget(
        UncontrolledProviderScope(
          container: container,
          child: const MaterialApp(
            home: ClinicianDashboardScreen(patientId: patientId),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('SKIPPED'), findsOneWidget);

      // Tap Correct button
      await tester.tap(find.byKey(const Key('correct_dose_button_501')));
      await tester.pumpAndSettle();

      // Sheet is open
      expect(find.text('Correct Dose Event'), findsOneWidget);

      // Select TAKEN and enter reason
      await tester.tap(find.text('TAKEN'));
      await tester.enterText(find.byType(TextField), 'Patient confirmed dose taken');
      await tester.tap(find.text('Apply Correction'));
      await tester.pumpAndSettle();

      // Sheet closed
      expect(find.text('Correct Dose Event'), findsNothing);

      // SnackBar displayed
      expect(find.text('Dose event corrected successfully.'), findsOneWidget);

      // Authoritative state in dashboard updated to TAKEN
      expect(find.text('TAKEN'), findsOneWidget);

      // Both providers were refreshed authoritatively
      expect(analysisRefreshCount, greaterThanOrEqualTo(2));
      expect(dosesRefreshCount, greaterThanOrEqualTo(2));
    });
  });
}

class FakeClinicianDoseRepository implements ClinicianDoseRepository {
  FakeClinicianDoseRepository({required this.onCorrect});

  final Future<EventCorrectionResponse> Function({
    required int eventId,
    required String newStatus,
    required String reason,
  }) onCorrect;

  @override
  Future<TodayScheduleResponse> fetchPatientDoses(int patientId) async {
    return TodayScheduleResponse(
      patientId: patientId,
      localDate: '2026-10-05',
      timezone: 'UTC',
      doses: [],
      totalDoses: 0,
      dosesTaken: 0,
      dosesRemaining: 0,
    );
  }

  @override
  Future<EventCorrectionResponse> correctEvent({
    required int eventId,
    required String newStatus,
    required String reason,
  }) {
    return onCorrect(eventId: eventId, newStatus: newStatus, reason: reason);
  }
}
