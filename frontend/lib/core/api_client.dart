import 'dart:math';

import 'package:dio/dio.dart';

import '../config/app_config.dart';
import 'api_exception.dart';
import 'token_storage.dart';

/// The single HTTP entry point for the app (spec §32).
///
/// UI widgets never make raw requests — repositories call this, and this owns
/// authentication, token refresh, error normalization, request IDs and timeouts
/// in one place. A Bearer access token is attached to every request; on a 401
/// the client transparently refreshes the token once (single-flight, so
/// concurrent 401s share one refresh) and retries. If refresh fails, it clears
/// the session and notifies [onSessionExpired] so the app can route to sign-in.
class ApiClient {
  final Dio _dio;
  final Dio _refreshDio; // bare client for the refresh call (no interceptors)
  final TokenStorage _tokens;
  final void Function()? onSessionExpired;

  Future<String?>? _refreshInFlight;

  ApiClient({
    required TokenStorage tokens,
    this.onSessionExpired,
    Dio? dio,
    Dio? refreshDio,
    String? baseUrl,
  })  : _tokens = tokens,
        _dio = dio ?? Dio(),
        _refreshDio = refreshDio ?? Dio() {
    final base = baseUrl ?? AppConfig.apiBaseUrl;
    for (final d in [_dio, _refreshDio]) {
      d.options
        ..baseUrl = base
        ..connectTimeout = const Duration(seconds: 15)
        ..receiveTimeout = const Duration(seconds: 30)
        ..headers['Accept'] = 'application/json';
    }
    _dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: _onRequest,
        onError: _onError,
      ),
    );
  }

  // --- public verbs --------------------------------------------------------

  Future<dynamic> get(String path, {Map<String, dynamic>? query}) =>
      _send(() => _dio.get(path, queryParameters: query));

  Future<dynamic> post(String path, {Object? body}) =>
      _send(() => _dio.post(path, data: body));

  Future<dynamic> patch(String path, {Object? body}) =>
      _send(() => _dio.patch(path, data: body));

  Future<dynamic> delete(String path, {Object? body}) =>
      _send(() => _dio.delete(path, data: body));

  /// Multipart upload of a single file field (e.g. an avatar). Goes through the
  /// same auth/refresh interceptor as every other request.
  Future<dynamic> postFile(
    String path, {
    required String field,
    required String filePath,
    String filename = 'upload.jpg',
  }) async {
    final form = FormData.fromMap({
      field: await MultipartFile.fromFile(filePath, filename: filename),
    });
    return _send(() => _dio.post(path, data: form));
  }

  // --- interceptors --------------------------------------------------------

  Future<void> _onRequest(
    RequestOptions options,
    RequestInterceptorHandler handler,
  ) async {
    final access = await _tokens.readAccess();
    if (access != null && access.isNotEmpty) {
      options.headers['Authorization'] = 'Bearer $access';
    }
    options.headers['X-Request-Id'] = _requestId();
    handler.next(options);
  }

  Future<void> _onError(
    DioException err,
    ErrorInterceptorHandler handler,
  ) async {
    final response = err.response;
    final isRefreshCall = err.requestOptions.path.contains('auth/token/refresh');

    // A 401 on a normal call: try a single shared refresh, then retry once.
    if (response?.statusCode == 401 && !isRefreshCall) {
      final newAccess = await _refreshOnce();
      if (newAccess != null) {
        final retried = await _retry(err.requestOptions, newAccess);
        if (retried != null) return handler.resolve(retried);
      }
      // Refresh failed → the session is over.
      await _tokens.clear();
      onSessionExpired?.call();
    }
    handler.next(err);
  }

  /// At most one refresh runs at a time; concurrent 401s await the same future.
  Future<String?> _refreshOnce() {
    return _refreshInFlight ??= _doRefresh().whenComplete(() {
      _refreshInFlight = null;
    });
  }

  Future<String?> _doRefresh() async {
    final refresh = await _tokens.readRefresh();
    if (refresh == null || refresh.isEmpty) return null;
    try {
      final res = await _refreshDio.post(
        'auth/token/refresh/',
        data: {'refresh': refresh},
      );
      final access = (res.data as Map)['access'] as String?;
      if (access != null) {
        await _tokens.saveAccess(access);
        return access;
      }
    } on DioException {
      // fall through — refresh token is expired/revoked
    }
    return null;
  }

  Future<Response<dynamic>?> _retry(
    RequestOptions options,
    String access,
  ) async {
    try {
      final headers = Map<String, dynamic>.from(options.headers)
        ..['Authorization'] = 'Bearer $access';
      return await _dio.request(
        options.path,
        data: options.data,
        queryParameters: options.queryParameters,
        options: Options(method: options.method, headers: headers),
      );
    } on DioException {
      return null;
    }
  }

  // --- helpers -------------------------------------------------------------

  Future<dynamic> _send(Future<Response<dynamic>> Function() run) async {
    try {
      final res = await run();
      return res.data;
    } on DioException catch (e) {
      throw _toApiException(e);
    }
  }

  ApiException _toApiException(DioException e) {
    final status = e.response?.statusCode;
    if (status == null) {
      return ApiException(
        'Network problem — check your connection and try again.',
        isNetwork: true,
      );
    }
    final data = e.response?.data;
    final fieldErrors = <String, List<String>>{};
    String message = 'Something went wrong (HTTP $status).';
    if (data is Map) {
      // Convention: {"detail": "..."} for a single message, or
      // {"field": ["msg", ...]} for form validation.
      if (data['detail'] is String) {
        message = data['detail'] as String;
      }
      data.forEach((key, value) {
        if (key == 'detail') return;
        if (value is List) {
          fieldErrors[key.toString()] =
              value.map((v) => v.toString()).toList();
        } else if (value is String) {
          fieldErrors[key.toString()] = [value];
        }
      });
      if (data['detail'] is! String && fieldErrors.isNotEmpty) {
        message = fieldErrors.values.first.first;
      }
    }
    return ApiException(
      message,
      statusCode: status,
      fieldErrors: fieldErrors,
      isUnauthorized: status == 401,
    );
  }

  String _requestId() {
    final rnd = Random();
    final now = DateTime.now().microsecondsSinceEpoch.toRadixString(16);
    final tail = rnd.nextInt(1 << 32).toRadixString(16);
    return '$now-$tail';
  }
}
