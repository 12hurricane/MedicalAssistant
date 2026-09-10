import 'dart:async';

/// Announces that the backend has definitively rejected the session.
///
/// [AuthInterceptor] discovers this — it is the only code that sees a 401 survive a
/// refresh attempt — but it must not depend on the auth feature to report it. This
/// channel is the seam: `core/` publishes, `features/auth/` listens.
///
/// Without the seam, `core/api` would import the auth controller and the auth
/// controller would import `core/api`, and the resulting cycle would have to be
/// untangled by whoever next needs to test either half in isolation.
class SessionExpiryChannel {
  SessionExpiryChannel();

  final StreamController<void> _controller = StreamController<void>.broadcast();

  /// Broadcast, so more than one listener is allowed, and no event is buffered for a
  /// listener that attaches later — an expiry is only meaningful while it is current.
  Stream<void> get onExpired => _controller.stream;

  void notifyExpired() {
    if (!_controller.isClosed) _controller.add(null);
  }

  Future<void> dispose() => _controller.close();
}
