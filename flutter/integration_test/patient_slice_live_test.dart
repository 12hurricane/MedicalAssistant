// The patient vertical slice, driven end to end against a running backend.
//
// This is not a unit test and it does not mock anything: it launches the real app,
// which makes real HTTP calls to a real FastAPI server and stores real JWTs in the
// platform's credential store. It exists because the milestone it covers — "create
// Flutter project → connect live FastAPI backend → implement auth → role-based
// routing → Patient Dashboard → Today's Medication Schedule → real dose logging →
// refresh adherence score" — is only meaningfully verified against live data.
//
// Prerequisites, in order:
//
//   1. The backend is running and reachable:
//        cd backend && venv/Scripts/python -m uvicorn app.main:app --port 8000
//   2. The walkthrough patient exists with at least two unlogged doses today:
//        cd backend && venv/Scripts/python seed_walkthrough_patient.py
//   3. Run with the base URL pinned, because "localhost" on Windows can resolve to
//      ::1 while uvicorn is listening on 127.0.0.1:
//        flutter test integration_test/patient_slice_live_test.dart -d windows \
//          --dart-define=API_BASE_URL=http://127.0.0.1:8000
//
// The three tests are deliberately order-dependent and share one app install. Test 2
// verifies that the tokens test 1 stored survive a relaunch, which cannot be checked
// by a test that clears its own state first. Each run consumes two of the seeded
// patient's pending doses, so re-run the seed script before running the file again.

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'package:medassist/app/app.dart';
import 'package:medassist/core/api/generated/api_models.dart';
import 'package:medassist/core/storage/secure_token_storage.dart';
import 'package:medassist/features/patient/adherence/widgets/adherence_summary_card.dart';
import 'package:medassist/features/patient/medications/widgets/dose_log_sheet.dart';
import 'package:medassist/features/patient/medications/widgets/dose_tile.dart';

const String _email = 'flutter_walkthrough@example.com';
const String _password = 'FlutterWalk2026!';

const String _reseed =
    'Re-run the seed script to restore this patient\'s pending doses:\n'
    '  cd backend && venv/Scripts/python seed_walkthrough_patient.py';

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('sign in, land on the patient dashboard, log a dose as taken',
      (tester) async {
    // Only test 1 clears storage. Test 2 depends on what this run leaves behind.
    await SecureTokenStorage().clear();

    await _launch(tester);

    // The splash gives way to the login screen once restore finds nothing stored.
    // The button, not the heading: the screen renders "Sign in" as both.
    final signInButton = find.widgetWithText(FilledButton, 'Sign in');
    await _pumpUntil(tester, signInButton, describe: 'the login screen');

    await tester.enterText(_field('Email'), _email);
    await tester.enterText(_field('Password'), _password);
    await tester.tap(signInButton);

    // Role-based routing: a PATIENT lands here, and nothing else does.
    await _pumpUntil(tester, find.text('Today'), describe: 'the patient dashboard');
    expect(
      find.text('Hello, Flutter'),
      findsOneWidget,
      reason: 'The app bar greeting comes from GET /auth/me, so its absence means the '
          'session was routed without the profile actually being fetched.',
    );

    // Live schedule data, not placeholder content.
    await _pumpUntil(
      tester,
      find.byType(DoseTile),
      describe: 'at least one dose from GET /schedule/today',
    );

    // Waited for rather than asserted: the card is fed by a second request
    // (GET /adherence/score, which computes the slot and weekday breakdowns) and it
    // reliably arrives after the schedule. Asserting it the moment the doses render
    // was a race that failed on a local backend, and would fail more often on a real
    // network.
    await _pumpUntil(
      tester,
      find.byType(AdherenceSummaryCard),
      describe: 'the adherence card from GET /adherence/score',
    );

    final before = _takenCounter(tester);
    expect(before, isNotNull, reason: 'The "N of M taken" line is missing.');
    final counts = _parseCounter(before!);

    final tile = _firstLoggableTile(tester);
    final medicine = _medicineNameOf(tester, tile);

    await tester.ensureVisible(_recordButtonIn(tile));
    await tester.pumpAndSettle(const Duration(milliseconds: 300));
    await tester.tap(_recordButtonIn(tile));

    await _pumpUntil(
      tester,
      find.text('Did you take $medicine?'),
      describe: 'the dose log sheet for $medicine',
    );

    await tester.tap(find.text('Yes, I took it'));

    // The counter is recomputed from GET /schedule/today, so it only moves once the
    // write landed and the refetch came back.
    await _pumpUntilTrue(
      tester,
      () => _takenCounter(tester) == '${counts.taken + 1} of ${counts.total} taken',
      describe: 'the taken counter to reach ${counts.taken + 1} of ${counts.total}',
    );

    // The sheet closes after the write, not with it: `log()` awaits the refetch of
    // both the schedule and the adherence score before popping, so the counter on the
    // dashboard updates first and the sheet's dismissal animation follows.
    await _pumpUntilTrue(
      tester,
      () => find.text('Did you take $medicine?').evaluate().isEmpty,
      describe: 'the log sheet to close after a successful write',
    );
  });

  testWidgets('a relaunch restores the session without showing the login screen',
      (tester) async {
    // Storage is deliberately not cleared: the tokens test 1 stored are the subject.
    expect(
      await SecureTokenStorage().hasSession(),
      isTrue,
      reason: 'Test 1 did not leave a refresh token on disk, so there is nothing to '
          'restore. Run the whole file in order.',
    );

    await _launch(tester);

    await _pumpUntil(
      tester,
      find.text('Today'),
      describe: 'the patient dashboard, restored from stored tokens',
    );
    expect(
      find.text('Sign in'),
      findsNothing,
      reason: 'A patient with a valid stored session must never be shown the login '
          'screen, not even briefly.',
    );
  });

  testWidgets('skipping a dose records the structured reason the UI collected',
      (tester) async {
    await _launch(tester);
    await _pumpUntil(tester, find.byType(DoseTile), describe: 'today\'s doses');

    final before = _takenCounter(tester);
    final counts = _parseCounter(before!);

    final tile = _firstLoggableTile(tester);
    final medicine = _medicineNameOf(tester, tile);

    // The schedule this run is about to skip. Held so the refetch can be checked on
    // this specific dose rather than on a count of matching labels: an earlier run
    // leaves its own skipped dose on the list, and the adherence card renders a
    // "Skipped" stat of its own, so counting text matches is not a measurement of
    // anything. `dose.status` is the value the refetch actually delivered.
    final scheduleId = tester.widget<DoseTile>(tile).dose.scheduleId;

    await tester.ensureVisible(_recordButtonIn(tile));
    await tester.pumpAndSettle(const Duration(milliseconds: 300));
    await tester.tap(_recordButtonIn(tile));
    await _pumpUntil(tester, find.text('Did you take $medicine?'));

    await tester.tap(find.text('Skip this dose'));
    await _pumpUntil(tester, find.text('Why was this dose skipped?'));

    // The closed list is the point of 5.4: the barrier classifier is given an answer
    // rather than left to infer one from free text.
    //
    // Scoped to the sheet, because the same labels appear on the dashboard behind it:
    // a tile for an already-skipped dose renders its reason with the same wording.
    Finder inSheet(String text) => find.descendant(
          of: find.byType(DoseLogSheet),
          matching: find.text(text),
        );

    expect(inSheet('Doctor instructed me'), findsOneWidget);
    expect(inSheet('Medication unavailable'), findsOneWidget);
    expect(inSheet('Cost'), findsOneWidget);

    await tester.tap(inSheet('Side effects'));
    await tester.pump(const Duration(milliseconds: 200));

    await tester.enterText(
      find.descendant(of: find.byType(DoseLogSheet), matching: find.byType(TextField)),
      'Felt nauseous after the morning dose.',
    );
    await tester.pump(const Duration(milliseconds: 200));

    await tester.tap(find.text('Record skip'));

    await _pumpUntilTrue(
      tester,
      () => find.text('Why was this dose skipped?').evaluate().isEmpty,
      describe: 'the skip to be recorded and the sheet to close',
    );

    // The write is only half of 5.4. The other half is that the structured answer the
    // sheet collected comes back down on the dose, which is what a clinician will
    // eventually read. Asserted on the refetched tile, not on the sheet's own state.
    await _pumpUntilTrue(
      tester,
      () => _doseOf(tester, scheduleId)?.status == 'SKIPPED',
      describe: 'schedule $scheduleId to come back from the refetch as SKIPPED',
      diagnose: () => _tileSummary(tester),
    );

    expect(
      _doseOf(tester, scheduleId)?.skipReasonCode,
      equals(SkipReasonCode.sideEffects.wire),
      reason: 'The reason the patient picked from the closed list must survive the '
          'round trip. If this is null, the sheet wrote a bare SKIPPED and the '
          'barrier classifier is back to guessing.',
    );

    expect(
      _takenCounter(tester),
      equals('${counts.taken} of ${counts.total} taken'),
      reason: 'A skipped dose is not a taken dose.',
    );
  });
}

Future<void> _launch(WidgetTester tester) async {
  // A window tall enough that the whole dashboard fits. Not cosmetic: on a short
  // surface the dose tiles sit partly under the adherence card, and `tap` computes an
  // offset that hit-tests to the card instead of the button it was aimed at.
  await tester.binding.setSurfaceSize(const Size(1000, 1500));
  addTearDown(() => tester.binding.setSurfaceSize(null));

  await tester.pumpWidget(const ProviderScope(child: MedAssistApp()));
  await tester.pump();
}

Finder _field(String label) => find.ancestor(
      of: find.text(label),
      matching: find.byType(TextFormField),
    );

/// The first dose tile that still offers a log action.
///
/// Fails loudly rather than returning nothing: an all-logged schedule means the
/// seeded fixture is exhausted, which is a setup problem and not an app defect.
Finder _firstLoggableTile(WidgetTester tester) {
  final tiles = find.byType(DoseTile);
  final count = tiles.evaluate().length;

  for (var i = 0; i < count; i++) {
    final tile = tiles.at(i);
    if (_recordButtonIn(tile).evaluate().isNotEmpty) return tile;
  }

  fail(
    'All $count dose(s) on today\'s schedule are already logged, so there is '
    'nothing to record.\n$_reseed',
  );
}

Finder _recordButtonIn(Finder tile) => find.descendant(
      of: tile,
      matching: find.byTooltip('Record this dose'),
    );

String _medicineNameOf(WidgetTester tester, Finder tile) {
  final dose = tester.widget<DoseTile>(tile).dose;
  return dose.medicineName;
}

/// The dose one tile is currently rendering, by schedule, or null if no tile holds it.
///
/// Reads the model off the widget instead of matching what it drew. Status and skip
/// reason are both rendered as words that appear elsewhere on the dashboard — "Skipped"
/// is also an adherence stat label, "Side effects" is also a radio option — so a text
/// finder would answer a different question than the one being asked.
TodayDoseResponse? _doseOf(WidgetTester tester, int scheduleId) {
  for (final tile in tester.widgetList<DoseTile>(find.byType(DoseTile))) {
    if (tile.dose.scheduleId == scheduleId) return tile.dose;
  }
  return null;
}

/// Every tile's schedule and status, for a timeout message.
///
/// A bare "timed out waiting for SKIPPED" cannot distinguish a refetch that failed
/// from one that returned the dose unchanged from one that dropped the tile entirely.
String _tileSummary(WidgetTester tester) {
  final tiles = tester
      .widgetList<DoseTile>(find.byType(DoseTile))
      .map((t) => '${t.dose.scheduleId}=${t.dose.status}')
      .join(', ');
  return tiles.isEmpty ? 'no dose tiles on screen' : 'tiles now: $tiles';
}

final RegExp _counterPattern = RegExp(r'^(\d+) of (\d+) taken$');

/// The dashboard's "N of M taken" line, read back out of the rendered tree.
///
/// Read from the widget rather than recomputed, because the number the patient sees
/// is the thing under test.
String? _takenCounter(WidgetTester tester) {
  for (final element in find.byType(Text).evaluate()) {
    final data = (element.widget as Text).data;
    if (data != null && _counterPattern.hasMatch(data)) return data;
  }
  return null;
}

({int taken, int total}) _parseCounter(String text) {
  final match = _counterPattern.firstMatch(text)!;
  return (taken: int.parse(match.group(1)!), total: int.parse(match.group(2)!));
}

/// Pumps in small real-time slices until [finder] matches.
///
/// `pumpAndSettle` cannot be used while anything on screen is loading: a
/// [CircularProgressIndicator] animates forever, so "settled" never arrives and the
/// test times out on the spinner rather than on the request.
Future<void> _pumpUntil(
  WidgetTester tester,
  Finder finder, {
  Duration timeout = const Duration(seconds: 25),
  String? describe,
}) =>
    _pumpUntilTrue(
      tester,
      () => finder.evaluate().isNotEmpty,
      timeout: timeout,
      describe: describe ?? finder.describeMatch(Plurality.one),
    );

Future<void> _pumpUntilTrue(
  WidgetTester tester,
  bool Function() condition, {
  Duration timeout = const Duration(seconds: 25),
  String? describe,
  String Function()? diagnose,
}) async {
  final deadline = DateTime.now().add(timeout);
  while (DateTime.now().isBefore(deadline)) {
    if (condition()) return;
    await tester.pump(const Duration(milliseconds: 120));
  }
  if (condition()) return;
  fail(
    'Timed out after ${timeout.inSeconds}s waiting for ${describe ?? 'a condition'}.\n'
    '${diagnose == null ? '' : '${diagnose()}\n'}'
    'If the backend is not running, that is what this looks like.',
  );
}
