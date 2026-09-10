import 'package:dio/dio.dart';

import 'generated/api_models.dart';

/// A failed backend call, classified so callers can react rather than guess.
///
/// Kept sealed so a `switch` over it is exhaustive: a new failure mode becomes a
/// compile error at every handling site instead of silently falling into a generic
/// "something went wrong" branch.
sealed class ApiException implements Exception {
  const ApiException(this.message);

  /// Safe to show a user. Never contains a token or a raw stack trace.
  final String message;

  @override
  String toString() => '$runtimeType: $message';
}

/// The request never reached the backend, or the reply never came back.
class NetworkException extends ApiException {
  const NetworkException(super.message);
}

/// 401. The access token is missing, expired or rejected.
///
/// Reaching a caller means refresh has already been tried and failed, so the
/// session is genuinely over.
class UnauthorizedException extends ApiException {
  const UnauthorizedException(super.message);
}

/// 403. Authenticated, but not allowed to do this — a patient reaching for a
/// clinician endpoint, for example. Signing in again will not help.
class ForbiddenException extends ApiException {
  const ForbiddenException(super.message);
}

/// 404.
class NotFoundException extends ApiException {
  const NotFoundException(super.message);
}

/// 400. The backend understood the request and refused it, with a reason.
///
/// This is how the dose-logging path reports "Schedule #12 not found for patient
/// #3", so the detail string matters and is preserved verbatim.
class BadRequestException extends ApiException {
  const BadRequestException(super.message);
}

/// 422. Per-field validation failure from FastAPI.
class ValidationException extends ApiException {
  const ValidationException(super.message, this.fieldErrors);

  /// Field name (last element of the `loc` path) to its message.
  final Map<String, String> fieldErrors;
}

/// 5xx.
class ServerException extends ApiException {
  const ServerException(super.message);
}

/// The reply was well-formed HTTP but not the shape the schema promised.
///
/// Distinct from [ServerException] because it points at a client/backend version
/// mismatch rather than a backend fault, and the fix is a rebuild, not a retry.
class ContractException extends ApiException {
  const ContractException(super.message);
}

/// Translates a Dio failure into the classified form.
ApiException mapDioException(DioException error) {
  switch (error.type) {
    case DioExceptionType.connectionTimeout:
    case DioExceptionType.sendTimeout:
    case DioExceptionType.receiveTimeout:
    case DioExceptionType.transformTimeout:
      return const NetworkException('The server took too long to respond.');
    case DioExceptionType.connectionError:
      return const NetworkException(
        'Cannot reach the server. Check that the backend is running and that '
        'the app is pointed at the right address.',
      );
    case DioExceptionType.badCertificate:
      return const NetworkException('The server\'s certificate was rejected.');
    case DioExceptionType.cancel:
      return const NetworkException('The request was cancelled.');
    case DioExceptionType.unknown:
      if (error.error is ApiException) return error.error as ApiException;
      return NetworkException(error.message ?? 'The request failed.');
    case DioExceptionType.badResponse:
      break;
  }

  final response = error.response;
  final status = response?.statusCode ?? 0;
  final detail = _detailOf(response?.data);

  if (status == 401) {
    return UnauthorizedException(detail ?? 'Your session has expired.');
  }
  if (status == 403) {
    return ForbiddenException(detail ?? 'You do not have access to this.');
  }
  if (status == 404) {
    return NotFoundException(detail ?? 'Not found.');
  }
  if (status == 422) {
    final errors = _fieldErrorsOf(response?.data);
    return ValidationException(
      errors.isEmpty
          ? (detail ?? 'The submitted data was rejected.')
          : errors.values.first,
      errors,
    );
  }
  if (status >= 500) {
    return ServerException(detail ?? 'The server hit an error ($status).');
  }
  return BadRequestException(detail ?? 'The request was rejected ($status).');
}

/// FastAPI puts a plain-string reason in `detail` for `HTTPException`.
String? _detailOf(Object? data) {
  if (data is Map && data['detail'] is String) return data['detail'] as String;
  return null;
}

/// FastAPI puts a list of [ValidationError] in `detail` for a 422.
Map<String, String> _fieldErrorsOf(Object? data) {
  if (data is! Map) return const {};
  final detail = data['detail'];
  if (detail is! List) return const {};

  final out = <String, String>{};
  for (final entry in detail) {
    if (entry is! Map<String, dynamic>) continue;
    try {
      final parsed = ValidationError.fromJson(entry);
      // `loc` is like ["body", "email"]; the last element names the field.
      final field = parsed.loc.isEmpty ? '_' : parsed.loc.last.toString();
      out[field] = parsed.msg;
    } on Object {
      // A malformed validation envelope should not mask the real failure.
      continue;
    }
  }
  return out;
}
