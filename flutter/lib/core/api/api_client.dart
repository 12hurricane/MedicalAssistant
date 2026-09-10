import 'dart:io' show Platform;

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';

import '../storage/secure_token_storage.dart';
import 'api_exception.dart';
import 'auth_interceptor.dart';
import 'generated/api_models.dart';

/// Where the FastAPI backend lives.
///
/// Override at build time:
///
///     flutter run --dart-define=API_BASE_URL=http://192.168.1.20:8000
///
/// The default is per-platform because "localhost" does not mean the same thing
/// everywhere: an Android emulator's localhost is the emulator itself, and the host
/// machine is reachable only at 10.0.2.2. Getting this wrong looks like a dead
/// backend rather than a misconfigured client, so it is resolved here once.
String resolveApiBaseUrl() {
  const fromEnv = String.fromEnvironment('API_BASE_URL');
  if (fromEnv.isNotEmpty) return fromEnv;

  if (kIsWeb) return 'http://localhost:8000';
  try {
    if (Platform.isAndroid) return 'http://10.0.2.2:8000';
  } on Object {
    // Platform is unavailable on some targets; the localhost default is right there.
  }
  return 'http://localhost:8000';
}

/// The single HTTP entry point to the backend.
///
/// Every method returns a decoded model or throws an [ApiException]. Callers never
/// see a [DioException] or a raw status code, so a screen cannot accidentally treat
/// a 403 as an empty result.
class ApiClient {
  ApiClient({
    required SecureTokenStorage storage,
    required Future<void> Function() onSessionExpired,
    String? baseUrl,
    Dio? dio,
    Dio? refreshDio,
  }) : _dio = dio ?? Dio() {
    final resolved = baseUrl ?? resolveApiBaseUrl();
    final options = BaseOptions(
      baseUrl: resolved,
      connectTimeout: const Duration(seconds: 10),
      receiveTimeout: const Duration(seconds: 20),
      sendTimeout: const Duration(seconds: 20),
      contentType: Headers.jsonContentType,
      responseType: ResponseType.json,
      // Non-2xx is handled by the exception mapper below, uniformly, instead of
      // each call site checking a status code.
      validateStatus: (status) => status != null && status >= 200 && status < 300,
    );
    _dio.options = options;

    // A separate Dio for refreshing and for retrying, with no AuthInterceptor of
    // its own so a refresh cannot recurse back into the 401 handler.
    final refresher = refreshDio ?? Dio();
    refresher.options = options;

    _dio.interceptors.add(
      AuthInterceptor(
        storage: storage,
        refreshClient: refresher,
        onSessionExpired: onSessionExpired,
      ),
    );
  }

  final Dio _dio;

  /// Exposed for the auth repository, which needs to send a form-encoded login.
  Dio get raw => _dio;

  /// GET returning a decoded object.
  Future<T> getObject<T>(
    String path, {
    required T Function(Map<String, dynamic> json) decode,
    Map<String, dynamic>? query,
  }) async {
    final data = await _send<dynamic>(
      () => _dio.get<dynamic>(path, queryParameters: query),
    );
    return _decodeObject(path, data, decode);
  }

  /// GET returning a decoded list.
  Future<List<T>> getList<T>(
    String path, {
    required T Function(Map<String, dynamic> json) decode,
    Map<String, dynamic>? query,
  }) async {
    final data = await _send<dynamic>(
      () => _dio.get<dynamic>(path, queryParameters: query),
    );
    if (data is! List) {
      throw ContractException(
        'Expected a JSON list from $path, got ${data.runtimeType}.',
      );
    }
    return [
      for (final entry in data) _decodeObject(path, entry, decode),
    ];
  }

  /// POST a JSON body, returning a decoded object.
  Future<T> postObject<T>(
    String path, {
    required Map<String, dynamic> body,
    required T Function(Map<String, dynamic> json) decode,
    bool skipAuth = false,
  }) async {
    final data = await _send<dynamic>(
      () => _dio.post<dynamic>(
        path,
        data: body,
        options: skipAuth ? Options(extra: {kSkipAuthExtra: true}) : null,
      ),
    );
    return _decodeObject(path, data, decode);
  }

  /// PUT a JSON body, returning a decoded object.
  Future<T> putObject<T>(
    String path, {
    required Map<String, dynamic> body,
    required T Function(Map<String, dynamic> json) decode,
  }) async {
    final data = await _send<dynamic>(() => _dio.put<dynamic>(path, data: body));
    return _decodeObject(path, data, decode);
  }

  /// POST a form-encoded body. Only `/auth/login` needs this: the endpoint takes
  /// an `OAuth2PasswordRequestForm`, so JSON is rejected with a 422.
  Future<T> postForm<T>(
    String path, {
    required Map<String, dynamic> fields,
    required T Function(Map<String, dynamic> json) decode,
  }) async {
    final data = await _send<dynamic>(
      () => _dio.post<dynamic>(
        path,
        data: fields,
        options: Options(
          contentType: Headers.formUrlEncodedContentType,
          extra: {kSkipAuthExtra: true},
        ),
      ),
    );
    return _decodeObject(path, data, decode);
  }

  Future<dynamic> _send<T>(Future<Response<T>> Function() request) async {
    try {
      final response = await request();
      return response.data;
    } on DioException catch (error) {
      throw mapDioException(error);
    }
  }

  T _decodeObject<T>(
    String path,
    Object? data,
    T Function(Map<String, dynamic> json) decode,
  ) {
    if (data is! Map<String, dynamic>) {
      throw ContractException(
        'Expected a JSON object from $path, got ${data.runtimeType}.',
      );
    }
    try {
      return decode(data);
    } on ApiSchemaMismatch catch (error) {
      throw ContractException('$path: ${error.message}');
    } on TypeError catch (error) {
      // A missing required field or a changed type lands here. Reported as a
      // contract failure because retrying will not help — the client is out of date.
      throw ContractException('$path returned an unexpected shape: $error');
    } on FormatException catch (error) {
      throw ContractException('$path returned an unparseable value: ${error.message}');
    }
  }
}
