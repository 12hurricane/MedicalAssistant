import 'package:flutter/foundation.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:timezone/data/latest_all.dart' as tz;
import 'package:timezone/timezone.dart' as tz;
import 'package:flutter_timezone/flutter_timezone.dart';

final notificationServiceProvider = Provider<NotificationService>((ref) {
  return NotificationService();
});

/// Local notification service for scheduled medication dose reminders.
///
/// SCOPE NOTE:
/// Local notifications are IN SCOPE for this MVP on mobile platforms (Android/iOS).
/// On web, flutter_local_notifications does not have full background scheduling support,
/// so web execution safely no-ops.
class NotificationService {
  final FlutterLocalNotificationsPlugin _notifications = FlutterLocalNotificationsPlugin();
  bool _initialized = false;

  Future<void> init() async {
    if (_initialized || kIsWeb) return;

    tz.initializeTimeZones();
    try {
      final info = await FlutterTimezone.getLocalTimezone();
      tz.setLocalLocation(tz.getLocation(info.identifier));
    } catch (_) {
      // Fallback if local device timezone cannot be resolved
    }

    const androidSettings = AndroidInitializationSettings('@mipmap/ic_launcher');
    const iosSettings = DarwinInitializationSettings(
      requestAlertPermission: true,
      requestBadgePermission: true,
      requestSoundPermission: true,
    );

    const initSettings = InitializationSettings(
      android: androidSettings,
      iOS: iosSettings,
    );

    await _notifications.initialize(settings: initSettings);
    _initialized = true;
  }

  /// Schedule a notification for a pending dose at [scheduledTime] in the patient's [timezoneName].
  ///
  /// Converted using [tz.TZDateTime.from] into the patient's registered timezone location
  /// so that the reminder fires at the exact moment the patient's local clock strikes dose time.
  Future<void> scheduleDoseReminder({
    required int id,
    required String medicationName,
    required DateTime scheduledTime,
    String? timezoneName,
  }) async {
    if (!_initialized || kIsWeb) return;
    if (scheduledTime.isBefore(DateTime.now().toUtc())) return;

    final androidDetails = const AndroidNotificationDetails(
      'med_reminders',
      'Medication Reminders',
      channelDescription: 'Notifications for scheduled medication doses',
      importance: Importance.max,
      priority: Priority.high,
    );
    const iosDetails = DarwinNotificationDetails();
    final details = NotificationDetails(android: androidDetails, iOS: iosDetails);

    tz.Location location;
    if (timezoneName != null && timezoneName.isNotEmpty) {
      try {
        location = tz.getLocation(timezoneName);
      } catch (_) {
        location = tz.local;
      }
    } else {
      location = tz.local;
    }

    final scheduledLocal = tz.TZDateTime.from(scheduledTime.toUtc(), location);

    await _notifications.zonedSchedule(
      id: id,
      title: 'Time for your medication',
      body: 'It is time to take $medicationName.',
      scheduledDate: scheduledLocal,
      notificationDetails: details,
      androidScheduleMode: AndroidScheduleMode.exactAllowWhileIdle,
    );
  }

  /// Cancel reminder for a specific dose (e.g. when dose is logged as TAKEN or SKIPPED).
  Future<void> cancelReminder(int id) async {
    if (!_initialized || kIsWeb) return;
    await _notifications.cancel(id: id);
  }

  /// Cancel all scheduled reminders (e.g. on logout or full schedule rebuild).
  Future<void> cancelAll() async {
    if (!_initialized || kIsWeb) return;
    await _notifications.cancelAll();
  }
}
