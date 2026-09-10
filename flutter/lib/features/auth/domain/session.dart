import '../../../core/api/generated/api_models.dart';

/// The roles this client knows how to route.
///
/// The backend's `UserResponse.role` is a plain string, not the `UserRole` enum, so
/// an unrecognised value is a realistic possibility rather than a theoretical one.
/// [fromWire] therefore denies by default: it returns [unknown] instead of throwing,
/// and the router sends [unknown] to a dead end rather than guessing.
///
/// Guessing wrong in either direction is bad in a different way. Treating a clinician
/// as a patient shows them an empty dashboard; treating a patient as a clinician
/// points the UI at endpoints that will 403, and briefly implies they have a roster.
///
/// These are the three roles the backend has, and no synonyms. [clinician] was
/// `doctor('DOCTOR')` and [caregiver] existed with nothing behind it; both are gone as
/// of backend migration `9f2c1d7ab4e0`. Retaining `doctor` as an alias would have been
/// worse than useless here — the wire value it matched can no longer be issued, so it
/// would be a permanently dead branch that still reads like a supported case.
enum AppRole {
  patient('PATIENT'),
  clinician('CLINICIAN'),
  admin('ADMIN'),
  unknown('');

  const AppRole(this.wire);

  final String wire;

  /// Case- and whitespace-tolerant, because the value arrives as a bare string.
  /// Anything unmatched becomes [unknown].
  ///
  /// Note the tolerance is one-directional and only on the way in: the backend
  /// rejects anything but the exact value at creation time, so a normalised match
  /// here can only ever be forgiving a formatting difference, never admitting a role
  /// the server would not have written.
  static AppRole fromWire(String? wire) {
    if (wire == null) return unknown;
    final normalised = wire.trim().toUpperCase();
    for (final role in values) {
      if (role != unknown && role.wire == normalised) return role;
    }
    return unknown;
  }

  /// True for roles that own a medication schedule of their own.
  bool get isPatientFacing => this == patient;

  /// True for roles that review other people's medication safety.
  ///
  /// Matches the pair the backend's clinician-protected routes admit —
  /// `require_role(CLINICIAN, ADMIN)` on `GET /patients/{id}/safety` and
  /// `PUT /prescriptions/{id}/verify`. Routing a role here that those routes refuse
  /// would produce a dashboard made entirely of 403s.
  bool get isClinicianFacing => this == clinician || this == admin;
}

/// A signed-in user.
///
/// Holds no tokens. Those live only in [SecureTokenStorage] and are attached by the
/// interceptor, so a widget cannot read one out of state and log it.
class Session {
  const Session({required this.user, required this.role});

  Session.fromUser(this.user) : role = AppRole.fromWire(user.role);

  final UserResponse user;
  final AppRole role;

  int get userId => user.id;
  String get displayName => user.name;
  String get email => user.email;
}
