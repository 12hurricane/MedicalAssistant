import 'dart:async';

import 'package:dio/dio.dart';

import '../storage/secure_token_storage.dart';
import 'api_endpoints.dart';
import 'generated/api_models.dart';

/// Marks a request that must not carry an Authorization header.
///
/// Login, register and refresh are the only three. Sending a stale access token to
/// `/auth/refresh` is the specific mistake this guards: the endpoint rejects an
/// access token outright, so the refresh would fail and the session would be
/// dropped even though the refresh token was perfectly good.
const String kSkipAuthExtra = 'medassist.skipAuth';

/// Attaches the bearer token, and renews it once when the backend says it expired.
///
/// Two properties this deliberately guarantees:
///
/// 1. **One refresh at a time.** Five widgets loading in parallel produce five
///    401s. Without the shared [_refreshing] future they would fire five refreshes,
///    four of which race; whichever lands last wins and the others' retries go out
///    with a token that has already been replaced.
/// 2. **One retry per request.** A request that 401s after a successful refresh is
///    not retried again. Otherwise a backend that always answers 401 turns into an
///    infinite loop of refresh-and-retry.
class AuthInterceptor extends Interceptor {
  AuthInterceptor({
    required SecureTokenStorage storage,
    required Dio refreshClient,
    required Future<void> Function() onSessionExpired,
  })  : _storage = storage,
        _refreshClient = refreshClient,
        _onSessionExpired = onSessionExpired;

  static const String _retriedExtra = 'medassist.retried';

  final SecureTokenStorage _storage;

  /// A separate Dio with no interceptors, so refreshing cannot recurse into this
  /// interceptor and 401 its way back here.
  final Dio _refreshClient;

  final Future<void> Function() _onSessionExpired;

  Future<String?>? _refreshing;

  @override
  Future<void> onRequest(
    RequestOptions options,
    RequestInterceptorHandler handler,
  ) async {
    if (options.extra[kSkipAuthExtra] == true) {
      return handler.next(options);
    }
    final token = await _storage.readAccessToken();
    if (token != null) {
      options.headers['Authorization'] = 'Bearer $token';
    }
    handler.next(options);
  }

  @override
  Future<void> onError(
    DioException err,
    ErrorInterceptorHandler handler,
  ) async {
    final options = err.requestOptions;
    final isAuthFailure = err.response?.statusCode == 401;
    final alreadyRetried = options.extra[_retriedExtra] == true;
    final skipsAuth = options.extra[kSkipAuthExtra] == true;

    if (!isAuthFailure || alreadyRetried || skipsAuth) {
      return handler.next(err);
    }

    final token = await _refreshOnce();
    if (token == null) {
      // Refresh failed: the session is over, not merely stale.
      await _onSessionExpired();
      return handler.next(err);
    }

    try {
      final retried = await _refreshClient.fetch<dynamic>(
        options
          ..headers['Authorization'] = 'Bearer $token'
          ..extra[_retriedExtra] = true,
      );
      return handler.resolve(retried);
    } on DioException catch (retryError) {
      return handler.next(retryError);
    }
  }

  /// Returns a fresh access token, or null if the session cannot be renewed.
  ///
  /// Concurrent callers await the same in-flight attempt.
  Future<String?> _refreshOnce() {
    final inFlight = _refreshing;
    if (inFlight != null) return inFlight;

    final attempt = _performRefresh();
    _refreshing = attempt;
    // Cleared in a `whenComplete` rather than after the await, so a thrown
    // refresh does not leave a permanently poisoned future here.
    attempt.whenComplete(() => _refreshing = null);
    return attempt;
  }

  Future<String?> _performRefresh() async {
    final refreshToken = await _storage.readRefreshToken();
    if (refreshToken == null) return null;

    try {
      final response = await _refreshClient.post<dynamic>(
        ApiEndpoints.refresh,
        data: TokenRefresh(refreshToken: refreshToken).toJson(),
        options: Options(extra: {kSkipAuthExtra: true}),
      );
      final data = response.data;
      if (data is! Map<String, dynamic>) return null;

      final tokens = TokenResponse.fromJson(data);
      // The backend may or may not rotate the refresh token. Store whatever came
      // back rather than assuming; keeping a rotated-out refresh token would mean
      // the next renewal fails.
      await _storage.saveTokens(
        accessToken: tokens.accessToken,
        refreshToken: tokens.refreshToken,
      );
      return tokens.accessToken;
    } on DioException {
      return null;
    } on ApiSchemaMismatch {
      return null;
    }
  }
}
