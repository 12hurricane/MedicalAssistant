// The client's half of the backend contract, checked mechanically.
//
// Nothing here talks to a running server. Every assertion is made against
// `../backend/openapi.json`, which the backend produces from its own Pydantic
// schemas — so this suite fails on a `git pull` that changes the API, at the point
// where the change is cheap to notice, rather than on a patient's phone.
//
// What it holds:
//
//   1. The committed generated models are current. `generate()` is pure, so the
//      spec is re-rendered in memory and compared against the file on disk.
//   2. Every path in `ApiEndpoints` exists in the spec. A typo'd URL is otherwise a
//      404 discovered at runtime.
//   3. The hand-written enums that mirror the spec still mirror it — `DoseLogAction`
//      against the one inline enum the generator deliberately renders as a bare
//      `String`, and `AppRole` against every role the API can create.
//   4. The UI's own lists cover the generated enums they render, so a new backend
//      value cannot become an option a patient is never offered.
//   5. `UserRegister` publishes no `role`. That is a security property, not a
//      cosmetic one: the generated models come from this document, so a role field
//      here becomes a settable field on the client and, eventually, a sent one.

import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:medassist/core/api/api_endpoints.dart';
import 'package:medassist/core/api/generated/api_models.dart';
import 'package:medassist/features/auth/domain/session.dart';
import 'package:medassist/shared/dose_status.dart';
import 'package:medassist/shared/skip_reason_labels.dart';

// Not a `package:` import: the generator lives in `tool/`, outside `lib/`, because it
// is a build-time script and must never be reachable from application code.
import '../tool/generate_api_models.dart' show generate;

const String _specRelative = '../backend/openapi.json';
const String _generatedRelative = 'lib/core/api/generated/api_models.dart';

const String _regenerateSpec =
    'Regenerate the spec from the backend:\n'
    '  cd backend && python -c "import json; from app.main import app; '
    'json.dump(app.openapi(), open(\'openapi.json\',\'w\'), indent=2)"';

const String _regenerateModels =
    'Regenerate the models:\n'
    '  cd flutter && dart run tool/generate_api_models.dart';

void main() {
  final root = _packageRoot();
  final specFile = File('${root.path}/$_specRelative');

  setUpAll(() {
    // Checked once, with the fix in the message. A bare FileSystemException here reads
    // as a broken test rather than as a missing artefact someone has to regenerate.
    if (!specFile.existsSync()) {
      fail('Cannot find ${specFile.path}.\n$_regenerateSpec');
    }
  });

  Map<String, dynamic> readSpec() =>
      jsonDecode(specFile.readAsStringSync()) as Map<String, dynamic>;

  group('generated models', () {
    test('committed file matches what the current spec generates', () {
      final committed = File('${root.path}/$_generatedRelative');
      expect(
        committed.existsSync(),
        isTrue,
        reason: 'Missing $_generatedRelative.\n$_regenerateModels',
      );

      final expected = generate(readSpec());

      // Line endings are normalised before comparing. A CRLF checkout is a git
      // `core.autocrlf` artefact, not a schema divergence, and failing on it would
      // teach people that this test cries wolf.
      final actual = _normalise(committed.readAsStringSync());
      final wanted = _normalise(expected);

      if (actual != wanted) {
        fail(
          'The committed models are stale — the backend schema has changed.\n'
          '${_firstDifference(actual, wanted)}\n\n'
          '$_regenerateModels\n'
          'Then fix whatever no longer compiles, rather than editing the '
          'generated file.',
        );
      }
    });

    test('generate() is pure — same spec in, same string out', () {
      // The staleness check above is only meaningful if this holds. A generator that
      // embedded a timestamp or iterated an unordered map would make it flap.
      final spec = readSpec();
      expect(generate(spec), equals(generate(readSpec())));
    });
  });

  group('endpoints', () {
    test('every ApiEndpoints path exists in the spec', () {
      final paths = (readSpec()['paths'] as Map<String, dynamic>).keys.toSet();

      final missing = ApiEndpoints.allTemplates
          .where((template) => !paths.contains(template))
          .toList();

      expect(
        missing,
        isEmpty,
        reason: 'These paths are called by the client but are not in the spec:\n'
            '${missing.map((p) => '  $p').join('\n')}\n'
            'Either the backend moved them or the constant is a typo. Both are a '
            '404 at runtime.',
      );
    });

    test('allTemplates covers every constant path on ApiEndpoints', () {
      // Guards the list itself. Adding a constant and forgetting to register it here
      // would leave the new path unchecked, which is the failure this whole group
      // exists to prevent.
      const declared = <String>[
        ApiEndpoints.register,
        ApiEndpoints.login,
        ApiEndpoints.refresh,
        ApiEndpoints.me,
        ApiEndpoints.myPatientProfile,
        ApiEndpoints.myPatientSafety,
        ApiEndpoints.todaySchedule,
        ApiEndpoints.logDose,
        ApiEndpoints.adherenceScore,
        ApiEndpoints.adherenceAnalysis,
        ApiEndpoints.prescriptions,
        ApiEndpoints.medications,
        ApiEndpoints.health,
      ];

      for (final path in declared) {
        expect(
          ApiEndpoints.allTemplates,
          contains(path),
          reason: '$path is missing from ApiEndpoints.allTemplates, so nothing '
              'checks that the backend still serves it.',
        );
      }
    });
  });

  group('hand-written enums', () {
    test('DoseLogAction matches DoseLogCreate.status in the spec', () {
      // The only inline (anonymous) enum in the spec, which the generator renders as
      // a bare `String` by design — so this is the one place the closed set the client
      // is allowed to *send* is pinned to the backend's own list.
      final schemas = readSpec()['components']['schemas'] as Map<String, dynamic>;
      final status = (schemas['DoseLogCreate']
          as Map<String, dynamic>)['properties']['status'] as Map<String, dynamic>;

      final specValues = (status['enum'] as List).cast<String>();

      expect(
        DoseLogAction.values.map((a) => a.wire).toList(),
        equals(specValues),
        reason: 'POST /adherence/log accepts $specValues. Sending anything else is '
            'a 422 the compiler should have caught.',
      );
    });

    test('AppRole covers every role the backend can create', () {
      // `UserResponse.role` is a plain string, so AppRole.fromWire is tolerant and
      // routes anything unrecognised to a dead end. That is the right behaviour for a
      // value this build has never heard of — and the wrong behaviour for a role the
      // backend has already declared. This is the difference.
      //
      // The vocabulary is assembled from two places rather than one, because the
      // backend no longer publishes a single all-roles enum: removing `role` from
      // `UserRegister` left `UserRole` referenced by nothing, so the generator stops
      // emitting it. What the spec does still describe is every role the API can
      // actually create — PATIENT via self-registration, and `PrivilegedRole` via
      // `POST /admin/users`.
      //
      // Weaker than before, and worth stating plainly: a role that is neither
      // self-registerable nor admin-grantable would not appear here, so this test
      // would not notice it. Typing `UserResponse.role` as `UserRole` on the backend
      // would restore a single source — at the cost of making response parsing strict
      // about a field this client deliberately parses leniently.
      final roles = <String>{
        'PATIENT',
        ...PrivilegedRole.values.map((r) => r.wire),
      };

      for (final wire in roles) {
        expect(
          AppRole.fromWire(wire),
          isNot(AppRole.unknown),
          reason: 'The backend can create a "$wire" account but AppRole does not '
              'know that role, so such a user would be shown the "unsupported '
              'role" dead end. Add it to AppRole and decide where it routes.',
        );
      }
    });

    test('AppRole carries no role the backend cannot create', () {
      // The other direction, which the test above cannot see.
      //
      // That one fails when the backend gains a role the client lacks. This one fails
      // when the client keeps a role the backend has retired — a branch that still
      // reads as a supported case, routes somewhere, and can never be reached. When
      // DOCTOR became CLINICIAN, leaving `doctor('DOCTOR')` in `AppRole` alongside the
      // new value would have passed every other test in this file: nothing would have
      // been missing, only permanently dead. And a dead role in a routing enum is not
      // inert, because the next reader has no way to tell it from a live one and will
      // maintain both.
      //
      // `unknown` is excluded by design: its empty wire value matches nothing, which is
      // the whole mechanism by which an unrecognised role reaches the dead end.
      final creatable = <String>{
        'PATIENT',
        ...PrivilegedRole.values.map((r) => r.wire),
      };

      final orphaned = AppRole.values
          .where((r) => r != AppRole.unknown)
          .where((r) => !creatable.contains(r.wire))
          .toList();

      expect(
        orphaned,
        isEmpty,
        reason: 'AppRole declares ${orphaned.map((r) => r.wire).toList()}, which the '
            'backend can no longer create. Either the backend retired the role and '
            'this is now unreachable code, or the client invented a role the API has '
            'never had.',
      );
    });

    test('the public registration schema has no role field', () {
      // The client-side half of the privilege-escalation fix. `UserRegister` used to
      // carry a role, so the generated model had a settable `role` and the repository
      // had a `UserRole role = UserRole.patient` parameter — a default that reads as
      // safe while the field it fills is the escalation vector. Both are gone.
      //
      // Asserted against the spec, not against the Dart: the generated file is
      // derived, so a stale checkout would fail test 1 above instead of this one, and
      // this test states the property that made the change necessary.
      final schemas = readSpec()['components']['schemas'] as Map<String, dynamic>;
      final register = (schemas['UserRegister']
          as Map<String, dynamic>)['properties'] as Map<String, dynamic>;
      expect(
        register.containsKey('role'),
        isFalse,
        reason: 'POST /auth/register advertises a role field again. Anonymous '
            'callers must not be able to choose their own role.',
      );

      // And PATIENT must stay out of the privileged enum: patients are created by
      // self-registration, the one path that also builds their profile row.
      final privileged =
          (schemas['PrivilegedRole'] as Map<String, dynamic>)['enum'] as List;
      expect(privileged, isNot(contains('PATIENT')));
    });

    test('every DoseLogAction is displayable as a DoseStatus', () {
      // The client writes a status and then renders whatever the server echoes back.
      // If those two vocabularies drift, a dose the patient just logged renders as
      // "Unknown" in grey.
      for (final action in DoseLogAction.values) {
        expect(
          DoseStatus.fromWire(action.wire),
          isNot(DoseStatus.unknown),
          reason: 'The client can send "${action.wire}" but DoseStatus cannot '
              'display it.',
        );
      }
    });
  });

  group('UI lists cover their generated enums', () {
    test('kSkipReasonOrder contains every SkipReasonCode exactly once', () {
      // A skip reason absent from this list is an answer the sheet never offers, so
      // the barrier classifier has to infer what the UI could have simply asked.
      expect(
        kSkipReasonOrder.toSet(),
        equals(SkipReasonCode.values.toSet()),
        reason: 'kSkipReasonOrder and SkipReasonCode have diverged. Missing: '
            '${SkipReasonCode.values.toSet().difference(kSkipReasonOrder.toSet())}',
      );
      expect(
        kSkipReasonOrder.length,
        equals(SkipReasonCode.values.length),
        reason: 'A duplicate in kSkipReasonOrder would render the same radio option '
            'twice.',
      );
    });

    test('every SkipReasonCode has both labels and round-trips from the wire', () {
      for (final code in SkipReasonCode.values) {
        expect(code.patientLabel, isNotEmpty);
        expect(code.clinicianLabel, isNotEmpty);
        expect(skipReasonCodeOrNull(code.wire), equals(code));
      }
    });
  });
}

/// The directory holding `pubspec.yaml`.
///
/// `flutter test` runs with the package root as the working directory, but walking up
/// keeps the suite runnable from `test/` too.
Directory _packageRoot() {
  var dir = Directory.current;
  while (true) {
    if (File('${dir.path}/pubspec.yaml').existsSync()) return dir;
    final parent = dir.parent;
    if (parent.path == dir.path) {
      throw StateError(
        'No pubspec.yaml at or above ${Directory.current.path}. '
        'Run this from the flutter/ directory.',
      );
    }
    dir = parent;
  }
}

String _normalise(String source) => source.replaceAll('\r\n', '\n');

/// Where two versions of the generated file first disagree.
///
/// A raw `expect(a, equals(b))` on two thousand-line strings prints both in full and
/// is unreadable, which is how a real staleness failure gets skimmed past.
String _firstDifference(String actual, String expected) {
  final a = actual.split('\n');
  final b = expected.split('\n');

  for (var i = 0; i < a.length && i < b.length; i++) {
    if (a[i] != b[i]) {
      return 'First difference at line ${i + 1}:\n'
          '  committed: ${_clip(a[i])}\n'
          '  generated: ${_clip(b[i])}';
    }
  }

  return a.length < b.length
      ? 'Committed file is short by ${b.length - a.length} line(s); '
          'the spec added: ${_clip(b[a.length])}'
      : 'Committed file has ${a.length - b.length} extra line(s) at the end, '
          'starting: ${_clip(a[b.length])}';
}

String _clip(String line, [int max = 100]) =>
    line.length <= max ? line : '${line.substring(0, max)}…';
