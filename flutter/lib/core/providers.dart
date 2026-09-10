import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'api/api_client.dart';
import 'api/session_expiry.dart';
import 'storage/secure_token_storage.dart';

/// Application-wide singletons.
///
/// Deliberately thin, and deliberately free of any dependency on `features/`: an
/// override here in a test swaps the whole backend for a fake without touching a
/// screen. `onSessionExpired` goes through [SessionExpiryChannel] rather than calling
/// the auth controller directly, so this file has no idea the auth feature exists.
final secureTokenStorageProvider = Provider<SecureTokenStorage>(
  (ref) => SecureTokenStorage(),
);

final sessionExpiryChannelProvider = Provider<SessionExpiryChannel>((ref) {
  final channel = SessionExpiryChannel();
  ref.onDispose(channel.dispose);
  return channel;
});

final apiClientProvider = Provider<ApiClient>((ref) {
  final storage = ref.watch(secureTokenStorageProvider);
  final expiry = ref.watch(sessionExpiryChannelProvider);
  return ApiClient(
    storage: storage,
    onSessionExpired: () async {
      // Clear first, announce second. If the order were reversed, the listener could
      // navigate to the login screen while a dead token was still on disk, and a
      // restore on the next launch would begin with a doomed /me call.
      await storage.clear();
      expiry.notifyExpired();
    },
  );
});
