import '../../../core/api/api_client.dart';
import '../../../core/api/api_endpoints.dart';
import '../../../core/api/api_exception.dart';
import '../../../core/api/generated/api_models.dart';
import '../../../core/storage/secure_token_storage.dart';
import '../domain/session.dart';

/// Register, sign in, restore, sign out.
///
/// The only place tokens are written or cleared. Everything above this layer works
/// with a [Session] and never touches storage, so there is exactly one answer to
/// "where did this token come from".
class AuthRepository {
  AuthRepository({required ApiClient client, required SecureTokenStorage storage})
      : _client = client,
        _storage = storage;

  final ApiClient _client;
  final SecureTokenStorage _storage;

  /// Creates the account and signs in.
  ///
  /// Register returns the user but no tokens, so a second call is unavoidable. If the
  /// login half fails the account still exists — surfaced as-is rather than swallowed,
  /// because silently landing on the login screen after a successful registration
  /// reads as "registration failed" and invites a duplicate-email retry.
  ///
  /// There is no `role` parameter, and that is the point. This endpoint creates a
  /// PATIENT and nothing else; the backend removed the field from `UserRegister`
  /// rather than validating it, so `role` is not expressible here and a caller cannot
  /// ask for one. Clinician accounts come from `POST /admin/users`, which requires an
  /// authenticated ADMIN — see `app/api/v1/endpoints/admin.py`. The parameter used to
  /// exist with a `UserRole.patient` default, which read as a safe default but was
  /// really an open door with a polite sign on it.
  Future<Session> register({
    required String name,
    required String email,
    required String password,
    String? phone,
  }) async {
    await _client.postObject(
      ApiEndpoints.register,
      body: UserRegister(
        name: name,
        email: email,
        password: password,
        phone: phone,
      ).toJson(),
      decode: UserResponse.fromJson,
      skipAuth: true,
    );
    return login(email: email, password: password);
  }

  /// Signs in and stores the tokens.
  ///
  /// Form-encoded, and the email goes in `username`: the endpoint is FastAPI's
  /// `OAuth2PasswordRequestForm`, which rejects a JSON body with a 422.
  Future<Session> login({
    required String email,
    required String password,
  }) async {
    final tokens = await _client.postForm(
      ApiEndpoints.login,
      fields: BodyLoginApiV1AuthLoginPost(
        username: email,
        password: password,
      ).toJson(),
      decode: TokenResponse.fromJson,
    );
    await _storage.saveTokens(
      accessToken: tokens.accessToken,
      refreshToken: tokens.refreshToken,
    );
    return _fetchSession();
  }

  /// Returns the stored session, or null if there is none to restore.
  ///
  /// A [UnauthorizedException] here means the interceptor already tried to refresh and
  /// the backend refused, so the tokens are dead and are cleared. Every other failure
  /// — no network, backend down — is rethrown with the tokens left intact: signing a
  /// patient out because their train went into a tunnel would be wrong.
  Future<Session?> restoreSession() async {
    if (!await _storage.hasSession()) return null;
    try {
      return await _fetchSession();
    } on UnauthorizedException {
      await _storage.clear();
      return null;
    }
  }

  Future<void> logout() => _storage.clear();

  Future<Session> _fetchSession() async {
    final user = await _client.getObject(
      ApiEndpoints.me,
      decode: UserResponse.fromJson,
    );
    return Session.fromUser(user);
  }
}
