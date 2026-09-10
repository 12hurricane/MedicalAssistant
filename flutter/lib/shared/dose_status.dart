import 'package:flutter/material.dart';

import '../app/theme/app_colors.dart';

/// How a dose ended up, for display.
///
/// The backend sends `MedicationEvent.status` as a plain string (`TodayDoseResponse.status`
/// is `str`, not an enum, in the OpenAPI schema), so this mapping is tolerant by
/// necessity: an unrecognised value becomes [unknown] and renders as "Unknown" in grey
/// rather than being forced into one of the five it happens to resemble.
///
/// Contrast with [DoseLogAction], which is what the client is allowed to *send*. That
/// one is a closed set pinned to the spec by `test/api_contract_test.dart`, because
/// sending a status the backend rejects is a bug the compiler should catch.
enum DoseStatus {
  pending('PENDING'),
  taken('TAKEN'),
  skipped('SKIPPED'),
  missed('MISSED'),
  snoozed('SNOOZED'),
  unknown('');

  const DoseStatus(this.wire);

  final String wire;

  static DoseStatus fromWire(String? wire) {
    if (wire == null) return unknown;
    final normalised = wire.trim().toUpperCase();
    for (final status in values) {
      if (status != unknown && status.wire == normalised) return status;
    }
    return unknown;
  }

  String get label => switch (this) {
        pending => 'Not logged yet',
        taken => 'Taken',
        skipped => 'Skipped',
        missed => 'Missed',
        snoozed => 'Snoozed',
        unknown => 'Unknown',
      };

  /// Paired with [color] at every render site. Status is never colour-only.
  IconData get icon => switch (this) {
        pending => Icons.schedule,
        taken => Icons.check_circle,
        skipped => Icons.remove_circle_outline,
        missed => Icons.cancel_outlined,
        snoozed => Icons.snooze,
        unknown => Icons.help_outline,
      };

  Color get color => switch (this) {
        pending => AppColors.statusPending,
        taken => AppColors.statusTaken,
        skipped => AppColors.statusSkipped,
        missed => AppColors.statusMissed,
        snoozed => AppColors.statusSnoozed,
        unknown => AppColors.statusUnknown,
      };

  /// True once the dose has an outcome, so the log buttons should not be offered again.
  bool get isLogged => this != pending && this != unknown;
}

/// The statuses `POST /adherence/log` accepts.
///
/// Exactly the inline enum on `DoseLogCreate.status` in the OpenAPI schema — the one
/// construct the model generator deliberately renders as a bare `String`, which is why
/// this exists by hand and why the contract test asserts the two lists still match.
enum DoseLogAction {
  taken('TAKEN'),
  skipped('SKIPPED'),
  missed('MISSED'),
  snoozed('SNOOZED');

  const DoseLogAction(this.wire);

  final String wire;
}
