import 'package:timezone/data/latest_all.dart' as tz;
import 'package:timezone/timezone.dart' as tz;

bool _timezonesInitialized = false;

/// Ensures the timezone database is loaded once.
void ensureTimezonesInitialized() {
  if (!_timezonesInitialized) {
    tz.initializeTimeZones();
    _timezonesInitialized = true;
  }
}

/// Converts a UTC [DateTime] to the patient's local time in [timezoneName]
/// and formats it as 24-hour ('13:00') or 12-hour ('1:00 PM').
///
/// Example:
/// A dose scheduled at 08:00 UTC for a patient in 'Asia/Karachi' (UTC+5)
/// will return:
/// - '13:00' when [use24Hour] is true
/// - '1:00 PM' when [use24Hour] is false
String formatUtcToPatientTime(
  DateTime scheduledAtUtc,
  String timezoneName, {
  bool use24Hour = false,
}) {
  ensureTimezonesInitialized();

  tz.Location location;
  try {
    location = tz.getLocation(timezoneName);
  } catch (_) {
    location = tz.UTC;
  }

  final local = tz.TZDateTime.from(scheduledAtUtc.toUtc(), location);
  final hour24 = local.hour.toString().padLeft(2, '0');
  final minute = local.minute.toString().padLeft(2, '0');

  if (use24Hour) {
    return '$hour24:$minute';
  }

  final hour12 = local.hour % 12 == 0 ? 12 : local.hour % 12;
  final period = local.hour < 12 ? 'AM' : 'PM';
  return '$hour12:$minute $period';
}
