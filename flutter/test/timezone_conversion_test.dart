import 'package:flutter_test/flutter_test.dart';
import 'package:medassist/shared/time_utils.dart';
import 'package:medassist/features/patient/medications/widgets/dose_tile.dart';

void main() {
  setUpAll(() {
    ensureTimezonesInitialized();
  });

  group('Timezone Conversion & Display', () {
    test('converts 08:00 UTC to 13:00 for Asia/Karachi (PKT, UTC+5)', () {
      final scheduledAtUtc = DateTime.utc(2026, 9, 18, 8, 0, 0);
      const patientTimezone = 'Asia/Karachi';

      final localTime24 = formatUtcToPatientTime(
        scheduledAtUtc,
        patientTimezone,
        use24Hour: true,
      );
      expect(localTime24, equals('13:00'));

      final localTime12 = formatUtcToPatientTime(
        scheduledAtUtc,
        patientTimezone,
        use24Hour: false,
      );
      expect(localTime12, equals('1:00 PM'));

      final formattedFrom24 = formatLocalTime(localTime24);
      expect(formattedFrom24, equals('1:00 PM'));
    });

    test('converts 08:00 UTC to 04:00 for America/New_York (EDT, UTC-4)', () {
      final scheduledAtUtc = DateTime.utc(2026, 9, 18, 8, 0, 0);
      const patientTimezone = 'America/New_York';

      final localTime24 = formatUtcToPatientTime(
        scheduledAtUtc,
        patientTimezone,
        use24Hour: true,
      );
      expect(localTime24, equals('04:00'));

      final formatted = formatLocalTime(localTime24);
      expect(formatted, equals('4:00 AM'));
    });

    test('converts fractional offset UTC+5:30 for Asia/Kolkata (IST)', () {
      final scheduledAtUtc = DateTime.utc(2026, 9, 18, 8, 0, 0);
      const patientTimezone = 'Asia/Kolkata';

      final localTime24 = formatUtcToPatientTime(
        scheduledAtUtc,
        patientTimezone,
        use24Hour: true,
      );
      expect(localTime24, equals('13:30'));

      final localTime12 = formatUtcToPatientTime(
        scheduledAtUtc,
        patientTimezone,
        use24Hour: false,
      );
      expect(localTime12, equals('1:30 PM'));

      final formatted = formatLocalTime(localTime24);
      expect(formatted, equals('1:30 PM'));
    });

    test('converts 45-minute offset UTC+5:45 for Asia/Kathmandu (NPT)', () {
      final scheduledAtUtc = DateTime.utc(2026, 9, 18, 8, 0, 0);
      const patientTimezone = 'Asia/Kathmandu';

      final localTime24 = formatUtcToPatientTime(
        scheduledAtUtc,
        patientTimezone,
        use24Hour: true,
      );
      expect(localTime24, equals('13:45'));

      final localTime12 = formatUtcToPatientTime(
        scheduledAtUtc,
        patientTimezone,
        use24Hour: false,
      );
      expect(localTime12, equals('1:45 PM'));

      final formatted = formatLocalTime(localTime24);
      expect(formatted, equals('1:45 PM'));
    });

    test('handles DST boundaries correctly in America/New_York (Summer EDT vs Winter EST)', () {
      const patientTimezone = 'America/New_York';

      // Summer date (July) - EDT is UTC-4
      final summerUtc = DateTime.utc(2026, 7, 15, 8, 0, 0);
      final summerLocal = formatUtcToPatientTime(summerUtc, patientTimezone, use24Hour: true);
      expect(summerLocal, equals('04:00'));

      // Winter date (January) - EST is UTC-5
      final winterUtc = DateTime.utc(2026, 1, 15, 8, 0, 0);
      final winterLocal = formatUtcToPatientTime(winterUtc, patientTimezone, use24Hour: true);
      expect(winterLocal, equals('03:00'));
    });
  });
}
