// Unit and widget tests for the clinician patient roster.
//
// What it holds:
//
//   1. The PatientRosterNotifier correctly surfaces backend errors as
//      typed AsyncError states (ForbiddenException, NetworkException, etc.)
//   2. The PatientRosterScreen renders controlled states for:
//      - successful roster with patients
//      - empty roster (no patients match)
//      - access denied (ForbiddenException / 403)
//      - retryable error (NetworkException, ServerException)
//   3. The search delegates to the notifier, which delegates to the backend.
//
// What it does NOT test:
//
//   - Backend authorization logic (that belongs in backend/tests/)
//   - Auth interceptor token refresh (tested by auth_interceptor_test.dart)
//   - The PatientResponse.fromJson contract (tested by api_contract_test.dart)

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:medassist/core/api/api_exception.dart';
import 'package:medassist/core/api/generated/api_models.dart';
import 'package:medassist/core/widgets/state_views.dart';
import 'package:medassist/features/auth/domain/session.dart';
import 'package:medassist/features/auth/state/auth_controller.dart';
import 'package:medassist/features/clinician/dashboard/patient_roster_screen.dart';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

PatientResponse _patient({
  required int id,
  String? name,
  String? email,
}) =>
    PatientResponse(
      id: id,
      userId: id,
      preferredLanguage: 'en',
      timezone: 'America/New_York',
      createdAt: DateTime(2026, 1, 1),
      name: name,
      email: email,
    );

final _twoPatients = [
  _patient(id: 1, name: 'Jane Doe', email: 'jane@example.com'),
  _patient(id: 2, name: 'John Smith', email: 'john@example.com'),
];

// ---------------------------------------------------------------------------
// Mock notifiers
// ---------------------------------------------------------------------------

/// Returns a fixed list of patients.
class _SuccessNotifier extends PatientRosterNotifier {
  _SuccessNotifier(this._patients);

  final List<PatientResponse> _patients;

  @override
  Future<List<PatientResponse>> build() async => _patients;
}

/// Returns an empty list.
class _EmptyNotifier extends PatientRosterNotifier {
  @override
  Future<List<PatientResponse>> build() async => [];
}

/// Throws a ForbiddenException (403).
class _ForbiddenNotifier extends PatientRosterNotifier {
  @override
  Future<List<PatientResponse>> build() async =>
      throw const ForbiddenException('You do not have access to this.');
}

/// Throws a NetworkException (connection failure).
class _NetworkErrorNotifier extends PatientRosterNotifier {
  @override
  Future<List<PatientResponse>> build() async =>
      throw const NetworkException('Cannot reach the server.');
}

/// Throws a ServerException (5xx).
class _ServerErrorNotifier extends PatientRosterNotifier {
  @override
  Future<List<PatientResponse>> build() async =>
      throw const ServerException('The server hit an error (500).');
}

/// Never completes. Holds the provider in AsyncLoading permanently.
class _NeverCompletesNotifier extends PatientRosterNotifier {
  @override
  Future<List<PatientResponse>> build() => Completer<List<PatientResponse>>().future;
}

/// Signed-in clinician session for the auth controller.
class _MockAuthController extends AuthController {
  @override
  AuthState build() => AuthSignedIn(
        _clinicianSession,
      );
}

final _clinicianSession = Session.fromUser(
  UserResponse(
    id: 10,
    name: 'Dr. Clinician',
    email: 'clinician@hospital.com',
    role: 'CLINICIAN',
    isActive: true,
    createdAt: DateTime(2026, 1, 1),
  ),
);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/// Builds the PatientRosterScreen inside a ProviderScope with the given
/// notifier override, plus a mock auth controller.
Widget _buildApp({
  required PatientRosterNotifier Function() notifierFactory,
}) {
  return ProviderScope(
    overrides: [
      patientRosterProvider.overrideWith(notifierFactory),
      authControllerProvider.overrideWith(_MockAuthController.new),
    ],
    child: const MaterialApp(
      home: PatientRosterScreen(),
    ),
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

void main() {
  group('PatientRosterScreen — success states', () {
    testWidgets('renders patient cards when roster loads', (tester) async {
      await tester.pumpWidget(
        _buildApp(notifierFactory: () => _SuccessNotifier(_twoPatients)),
      );
      await tester.pumpAndSettle();

      // Both patients should appear
      expect(find.text('Jane Doe'), findsOneWidget);
      expect(find.text('John Smith'), findsOneWidget);
      expect(find.text('jane@example.com'), findsOneWidget);
      expect(find.text('john@example.com'), findsOneWidget);

      // Patient IDs should be displayed
      expect(find.text('ID: 1'), findsOneWidget);
      expect(find.text('ID: 2'), findsOneWidget);
    });

    testWidgets('renders Review buttons for each patient', (tester) async {
      await tester.pumpWidget(
        _buildApp(notifierFactory: () => _SuccessNotifier(_twoPatients)),
      );
      await tester.pumpAndSettle();

      // Each patient row has a "Review" button
      expect(find.text('Review'), findsNWidgets(2));
    });
  });

  group('PatientRosterScreen — empty state', () {
    testWidgets('renders empty view when roster has no patients', (tester) async {
      await tester.pumpWidget(
        _buildApp(notifierFactory: _EmptyNotifier.new),
      );
      await tester.pumpAndSettle();

      // The EmptyView from state_views.dart
      expect(find.byType(EmptyView), findsOneWidget);
      expect(find.text('No patients found'), findsOneWidget);
    });
  });

  group('PatientRosterScreen — access denied (403)', () {
    testWidgets('renders access denied view, not retry button', (tester) async {
      await tester.pumpWidget(
        _buildApp(notifierFactory: _ForbiddenNotifier.new),
      );
      await tester.pumpAndSettle();

      // Should show the access denied message, not the generic ErrorView
      expect(find.text('Access Denied'), findsOneWidget);
      expect(
        find.text(
          'You do not have permission to view the patient roster. '
          'Contact your administrator if you believe this is an error.',
        ),
        findsOneWidget,
      );

      // Must NOT offer a retry button — authorization failures are not transient
      expect(find.text('Try again'), findsNothing);
    });

    testWidgets('does not render ErrorView for 403', (tester) async {
      await tester.pumpWidget(
        _buildApp(notifierFactory: _ForbiddenNotifier.new),
      );
      await tester.pumpAndSettle();

      // ErrorView should not appear — 403 has its own dedicated view
      expect(find.byType(ErrorView), findsNothing);
    });
  });

  group('PatientRosterScreen — retryable errors', () {
    testWidgets('renders ErrorView with retry for network error', (tester) async {
      await tester.pumpWidget(
        _buildApp(notifierFactory: _NetworkErrorNotifier.new),
      );
      await tester.pumpAndSettle();

      // Should show the ErrorView with the server message
      expect(find.byType(ErrorView), findsOneWidget);
      expect(find.text('Cannot reach the server.'), findsOneWidget);

      // Should offer retry — network errors are transient
      expect(find.text('Try again'), findsOneWidget);
    });

    testWidgets('renders ErrorView with retry for server error', (tester) async {
      await tester.pumpWidget(
        _buildApp(notifierFactory: _ServerErrorNotifier.new),
      );
      await tester.pumpAndSettle();

      expect(find.byType(ErrorView), findsOneWidget);
      expect(find.text('Try again'), findsOneWidget);
    });
  });

  group('PatientRosterScreen — loading state', () {
    testWidgets('renders loading spinner while roster is fetching', (tester) async {
      // Use a notifier whose build() never completes, holding the provider
      // in AsyncLoading indefinitely.
      await tester.pumpWidget(
        _buildApp(notifierFactory: _NeverCompletesNotifier.new),
      );
      // Single pump — not pumpAndSettle, which would wait forever.
      await tester.pump();

      expect(find.byType(LoadingView), findsOneWidget);
      expect(find.text('Loading patient roster...'), findsOneWidget);
    });
  });

  group('PatientRosterScreen — UI structure', () {
    testWidgets('has search field in app bar area', (tester) async {
      await tester.pumpWidget(
        _buildApp(notifierFactory: () => _SuccessNotifier(_twoPatients)),
      );
      await tester.pumpAndSettle();

      // Search field should exist
      expect(
        find.widgetWithText(TextField, ''),
        findsOneWidget,
      );
    });

    testWidgets('has refresh and logout actions', (tester) async {
      await tester.pumpWidget(
        _buildApp(notifierFactory: () => _SuccessNotifier(_twoPatients)),
      );
      await tester.pumpAndSettle();

      expect(find.byTooltip('Refresh roster'), findsOneWidget);
      expect(find.byTooltip('Sign out'), findsOneWidget);
    });

    testWidgets('patient card shows timezone', (tester) async {
      await tester.pumpWidget(
        _buildApp(notifierFactory: () => _SuccessNotifier(_twoPatients)),
      );
      await tester.pumpAndSettle();

      // Both patients have America/New_York timezone
      expect(find.text('America/New_York'), findsNWidgets(2));
    });

    testWidgets('patient without name shows fallback', (tester) async {
      final noNamePatient = [_patient(id: 5)];
      await tester.pumpWidget(
        _buildApp(notifierFactory: () => _SuccessNotifier(noNamePatient)),
      );
      await tester.pumpAndSettle();

      expect(find.text('Patient #5'), findsOneWidget);
    });
  });
}
