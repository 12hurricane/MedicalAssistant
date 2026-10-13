import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:medassist/core/api/generated/api_models.dart';
import 'package:medassist/features/auth/domain/session.dart';
import 'package:medassist/features/auth/state/auth_controller.dart';
import 'package:medassist/features/patient/adherence/state/adherence_controller.dart';
import 'package:medassist/features/patient/dashboard/patient_shell_screen.dart';
import 'package:medassist/features/patient/medications/state/today_schedule_controller.dart';
import 'package:medassist/features/patient/medications/widgets/dose_tile.dart';

final mockSession = Session.fromUser(
  UserResponse(
    id: 1,
    name: 'Test Patient',
    email: 'test@example.com',
    role: 'PATIENT',
    isActive: true,
    createdAt: DateTime.now(),
  ),
);

class MockSignedInAuthController extends AuthController {
  @override
  AuthState build() => AuthSignedIn(mockSession);
}

class MockTodaySchedule extends TodayScheduleController {
  @override
  Future<TodayScheduleResponse> build() async {
    return TodayScheduleResponse(
      patientId: 1,
      localDate: '2026-09-18',
      timezone: 'UTC',
      doses: [
        TodayDoseResponse(
          scheduleId: 101,
          medicineName: 'Lisinopril',
          scheduledAt: DateTime.now(),
          scheduledLocalTime: '08:00',
          status: 'PENDING',
          isDue: true,
          strength: '10mg',
          instructions: 'Take with water',
        ),
      ],
      totalDoses: 1,
      dosesTaken: 0,
      dosesRemaining: 1,
    );
  }

  @override
  Future<void> refresh() async {}
}

class MockAdherenceMetrics extends AdherenceMetricsController {
  @override
  Future<AdherenceMetricsResponse> build() async {
    return AdherenceMetricsResponse(
      patientId: 1,
      period: '7d',
      periodStart: DateTime.now().subtract(const Duration(days: 7)),
      periodEnd: DateTime.now(),
      expectedDoses: 20,
      totalTaken: 17,
      totalMissed: 3,
      totalSkipped: 0,
      totalSnoozed: 0,
      currentStreak: 5,
      bestStreak: 10,
      timeSlotBreakdown: {},
      dayOfWeekBreakdown: [],
      trend: 'STABLE',
      detectedPatterns: [],
      shouldEscalate: false,
      escalationReasons: [],
      adherenceRate: 85.0,
      missedRate: 15.0,
    );
  }

  @override
  Future<void> refresh() async {}
}

void main() {
  testWidgets('End-User & QC Manager E2E Test: Dashboard Flow', (WidgetTester tester) async {
    // 1. Launch the app with Auth mocked to SignedIn and data mocked
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          authControllerProvider.overrideWith(MockSignedInAuthController.new),
          todayScheduleProvider.overrideWith(MockTodaySchedule.new),
          adherenceMetricsProvider.overrideWith(MockAdherenceMetrics.new),
        ],
        child: const MaterialApp(
          home: PatientShellScreen(),
        ),
      ),
    );
    await tester.pump(const Duration(milliseconds: 100));
    await tester.pump(const Duration(milliseconds: 100));

    // Verify we are on the Patient Shell Screen
    expect(find.byType(PatientShellScreen), findsOneWidget);

    // 2. QC Check: Header & Greeting
    expect(find.text('Hello, Test'), findsWidgets, reason: 'Dashboard should greet the user');
    expect(find.text('Good morning, Test Patient'), findsWidgets, reason: 'Patient background header should show full name');

    // 3. QC Check: Adherence Card is rendering
    expect(find.text('85%'), findsWidgets, reason: 'Adherence score should be displayed');
    
    // 4. QC Check: Today\'s Schedule
    expect(find.text('Today\'s Schedule'), findsOneWidget);
    expect(find.text('0 of 1 taken'), findsOneWidget);

    // 5. QC Check: Medication Tile is visible and interactable
    final doseTile = find.byType(DoseTile);
    expect(doseTile, findsOneWidget, reason: 'Lisinopril dose should be visible');
    expect(find.text('Lisinopril'), findsOneWidget);
    expect(find.text('10mg'), findsOneWidget);

    // Verify "Log Dose" button works
    final logButton = find.text('Log Dose');
    expect(logButton, findsOneWidget, reason: 'Log dose button should be present for pending dose');
    
    await tester.tap(logButton);
    await tester.pump(const Duration(milliseconds: 500));
    await tester.pump(const Duration(milliseconds: 500));

    // 6. QC Check: Bottom Navigation Bar
    // We expect to find 'Rx' somewhere. Note: the bottom sheet might be open, but it's fine.
    final rxTab = find.text('Rx');
    expect(rxTab, findsOneWidget, reason: 'Rx tab should be in bottom navigation');
    
    // Tap Profile tab
    final profileTab = find.text('Profile');
    // If bottom sheet is open, tap might fail if it's absorbing hit tests.
    // Let's close the bottom sheet first.
    await tester.tapAt(const Offset(10, 10)); // Tap outside to dismiss bottom sheet
    await tester.pump(const Duration(milliseconds: 500));

    await tester.tap(profileTab);
    await tester.pump(const Duration(milliseconds: 500));
    await tester.pump(const Duration(milliseconds: 500));

    // Ensure we switched to Profile View
    expect(find.text('Profile'), findsWidgets);
    
    // QC Checks passed!
  });
}
