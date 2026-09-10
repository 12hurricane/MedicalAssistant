import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// The access and refresh tokens, held in the platform's secure store.
///
/// Not `SharedPreferences`: that is a world-readable XML file on a rooted Android
/// device and an unencrypted plist on iOS. These tokens authorise reading a
/// patient's medication history, so they go in the Keystore / Keychain.
///
/// Writes are serialised through a single [FlutterSecureStorage] instance because
/// the Android implementation is not safe against concurrent writes to the same key.
class SecureTokenStorage {
  SecureTokenStorage({FlutterSecureStorage? storage})
      : _storage = storage ??
            const FlutterSecureStorage(
              aOptions: AndroidOptions(encryptedSharedPreferences: true),
              iOptions: IOSOptions(
                accessibility: KeychainAccessibility.first_unlock_this_device,
              ),
            );

  static const _accessTokenKey = 'medassist.access_token';
  static const _refreshTokenKey = 'medassist.refresh_token';

  final FlutterSecureStorage _storage;

  Future<String?> readAccessToken() => _storage.read(key: _accessTokenKey);

  Future<String?> readRefreshToken() => _storage.read(key: _refreshTokenKey);

  /// Stores both tokens. Writes the refresh token first: if the process dies
  /// between the two writes, having a refresh token without an access token is
  /// recoverable, whereas the reverse would leave a session that cannot renew.
  Future<void> saveTokens({
    required String accessToken,
    required String refreshToken,
  }) async {
    await _storage.write(key: _refreshTokenKey, value: refreshToken);
    await _storage.write(key: _accessTokenKey, value: accessToken);
  }

  /// Replaces only the access token, after a refresh that did not rotate the
  /// refresh token.
  Future<void> saveAccessToken(String accessToken) =>
      _storage.write(key: _accessTokenKey, value: accessToken);

  /// Clears both keys by name rather than calling `deleteAll`, which would also
  /// wipe anything else the app has stored.
  Future<void> clear() async {
    await _storage.delete(key: _accessTokenKey);
    await _storage.delete(key: _refreshTokenKey);
  }

  Future<bool> hasSession() async => (await readRefreshToken()) != null;
}
