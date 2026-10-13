import 'dart:async';
import 'package:flutter/foundation.dart';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_timezone/flutter_timezone.dart';

import '../../../core/api/api_exception.dart';
import '../../../core/api/generated/api_models.dart';
import '../../../core/providers.dart';
import '../data/auth_repository.dart';
import '../domain/session.dart';

/// Whether anyone is signed in.
///
/// Sealed, and with [AuthRestoring] as a first-class state rather than a nullable
/// session: on a cold start the app genuinely does not yet know, and collapsing
/// "don't know" into "signed out" is what produces a flash of the login screen for a
/// patient who was already signed in.
sealed class AuthState {
  const AuthState();
}

/// Cold start: reading storage and asking the backend who this is.
class AuthRestoring extends AuthState {
  const AuthRestoring();
}

class AuthSignedOut extends AuthState {
  const AuthSignedOut({this.notice});

  /// Shown once on the login screen — "Your session expired", not an error the user
  /// caused. Null after a deliberate sign-out.
  final String? notice;
}

class AuthSignedIn extends AuthState {
  const AuthSignedIn(this.session);

  final Session session;
}

final authRepositoryProvider = Provider<AuthRepository>(
  (ref) => AuthRepository(
    client: ref.watch(apiClientProvider),
    storage: ref.watch(secureTokenStorageProvider),
  ),
);

final authControllerProvider = NotifierProvider<AuthController, AuthState>(
  AuthController.new,
);

/// Convenience for widgets that only render when signed in.
final currentSessionProvider = Provider<Session?>((ref) {
  final state = ref.watch(authControllerProvider);
  return state is AuthSignedIn ? state.session : null;
});

class AuthController extends Notifier<AuthState> {
  @override
  AuthState build() {
    // A 401 that survived a refresh means the session is over. Handled here rather
    // than at each call site so one dead token cannot leave half the app authenticated.
    final expiry = ref.watch(sessionExpiryChannelProvider);
    final subscription = expiry.onExpired.listen((_) {
      if (state is AuthSignedIn) {
        state = const AuthSignedOut(
          notice: 'Your session expired. Please sign in again.',
        );
      }
    });
    ref.onDispose(subscription.cancel);

    // Kicked off, not awaited: `build` must return synchronously, and the router
    // shows the splash route while the state is still AuthRestoring.
    Future<void>.microtask(restore);
    return const AuthRestoring();
  }

  /// Reads stored tokens and confirms them against `GET /auth/me`.
  ///
  /// A network failure is *not* a sign-out. The state goes to [AuthSignedOut] with a
  /// notice so the login screen can explain itself, but the tokens stay on disk and
  /// the next attempt can still succeed.
  Future<void> restore() async {
    state = const AuthRestoring();
    try {
      final session = await ref.read(authRepositoryProvider).restoreSession();
      state = session == null ? const AuthSignedOut() : AuthSignedIn(session);
    } on ApiSchemaMismatch catch (error) {
      state = AuthSignedOut(notice: error.message);
    } on Object catch (error) {
      state = AuthSignedOut(notice: _messageOf(error));
    }
  }

  /// Signs in. Rethrows on failure so the form can show the reason against the field.
  Future<void> login({required String email, required String password}) async {
    final session = await ref
        .read(authRepositoryProvider)
        .login(email: email, password: password);
    state = AuthSignedIn(session);
  }

  /// Registers and signs in. Rethrows on failure, like [login].
  ///
  /// No `role` parameter: registration creates a PATIENT, and the backend contract no
  /// longer has a field to say otherwise. See [AuthRepository.register].
  Future<void> register({
    required String name,
    required String email,
    required String password,
    String? phone,
  }) async {
    String? timezone;
    try {
      if (!kIsWeb) {
        final dynamic tz = await FlutterTimezone.getLocalTimezone();
        timezone = tz.toString();
      } else {
        // web fallback since flutter_timezone doesn't support web by default 
        timezone = DateTime.now().timeZoneName;
      }
    } catch (_) {
      // Ignored
    }

    final session = await ref.read(authRepositoryProvider).register(
          name: name,
          email: email,
          password: password,
          phone: phone,
          timezone: timezone,
        );
    state = AuthSignedIn(session);
  }

  Future<void> logout() async {
    await ref.read(authRepositoryProvider).logout();
    state = const AuthSignedOut();
  }

  static String _messageOf(Object error) {
    // ApiException.message is already written for a user to read; toString() prefixes
    // it with the runtime type, which belongs in a log and not on a login screen.
    if (error is ApiException) return error.message;
    return 'Could not reach the server. Please try again.';
  }
}
