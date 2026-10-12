import 'dart:convert';
import 'dart:typed_data';

import 'package:boldron_app/core/api_client.dart';
import 'package:boldron_app/core/api_exception.dart';
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/fake_token_storage.dart';

/// A scriptable HTTP adapter: each (METHOD path-substring) maps to a queue of
/// responses, consumed in order (the last one repeats).
class ScriptedAdapter implements HttpClientAdapter {
  final Map<String, List<_Resp>> _script;
  final List<String> calls = [];

  ScriptedAdapter(this._script);

  @override
  Future<ResponseBody> fetch(RequestOptions options,
      Stream<Uint8List>? requestStream, Future<void>? cancelFuture) async {
    final key = _match(options);
    calls.add(key);
    final queue = _script[key]!;
    final resp = queue.length > 1 ? queue.removeAt(0) : queue.first;
    return ResponseBody.fromString(
      jsonEncode(resp.body),
      resp.status,
      headers: {
        Headers.contentTypeHeader: ['application/json'],
      },
    );
  }

  String _match(RequestOptions o) {
    return _script.keys.firstWhere(
      (k) {
        final parts = k.split(' ');
        return o.method == parts[0] && o.path.contains(parts[1]);
      },
      orElse: () => throw StateError('No script for ${o.method} ${o.path}'),
    );
  }

  @override
  void close({bool force = false}) {}
}

class _Resp {
  final int status;
  final Object body;
  _Resp(this.status, this.body);
}

ApiClient _client(FakeTokenStorage tokens,
    {required ScriptedAdapter main,
    required ScriptedAdapter refresh,
    void Function()? onExpired}) {
  final mainDio = Dio()..httpClientAdapter = main;
  final refreshDio = Dio()..httpClientAdapter = refresh;
  return ApiClient(
    tokens: tokens,
    dio: mainDio,
    refreshDio: refreshDio,
    baseUrl: 'http://test/api/v1/',
    onSessionExpired: onExpired,
  );
}

void main() {
  test('attaches the bearer token and returns data', () async {
    final tokens = FakeTokenStorage(access: 'abc', refresh: 'r1');
    final main = ScriptedAdapter({
      'GET me/': [
        _Resp(200, {'email': 'a@b.com'})
      ],
    });
    final api = _client(tokens,
        main: main, refresh: ScriptedAdapter({'POST x': [_Resp(200, {})]}));
    final data = await api.get('me/');
    expect(data['email'], 'a@b.com');
  });

  test('normalizes a base URL without a trailing slash', () async {
    // Regression: base ".../api/v1" + "auth/register/" must NOT fuse into
    // ".../api/v1auth/register/" (dio concatenates raw).
    final tokens = FakeTokenStorage(access: 'abc', refresh: 'r1');
    final main = ScriptedAdapter({'POST auth/register/': [_Resp(200, {'ok': true})]});
    final mainDio = Dio()..httpClientAdapter = main;
    final api = ApiClient(
      tokens: tokens,
      dio: mainDio,
      refreshDio: Dio()..httpClientAdapter = ScriptedAdapter({'POST x': [_Resp(200, {})]}),
      baseUrl: 'http://test/api/v1', // no trailing slash
    );
    await api.post('auth/register/', body: {});
    expect(main.calls.single, 'POST auth/register/');
    expect(mainDio.options.baseUrl, endsWith('/'));
  });

  test('refreshes the access token on 401 and retries once', () async {
    final tokens = FakeTokenStorage(access: 'expired', refresh: 'r1');
    final main = ScriptedAdapter({
      'GET me/': [
        _Resp(401, {'detail': 'expired'}),
        _Resp(200, {'email': 'a@b.com'}),
      ],
    });
    final refresh = ScriptedAdapter({
      'POST auth/token/refresh': [
        _Resp(200, {'access': 'fresh'})
      ],
    });
    final api = _client(tokens, main: main, refresh: refresh);

    final data = await api.get('me/');
    expect(data['email'], 'a@b.com'); // retried successfully
    expect(tokens.access, 'fresh'); // new access persisted
    expect(main.calls.length, 2); // original + retry
  });

  test('clears session and signals expiry when refresh fails', () async {
    var expired = false;
    final tokens = FakeTokenStorage(access: 'expired', refresh: 'bad');
    final main = ScriptedAdapter({
      'GET me/': [
        _Resp(401, {'detail': 'expired'})
      ],
    });
    final refresh = ScriptedAdapter({
      'POST auth/token/refresh': [
        _Resp(401, {'detail': 'invalid'})
      ],
    });
    final api = _client(tokens,
        main: main, refresh: refresh, onExpired: () => expired = true);

    expect(() => api.get('me/'), throwsA(isA<ApiException>()));
    await Future<void>.delayed(const Duration(milliseconds: 10));
    expect(expired, isTrue);
    expect(tokens.refresh, isNull); // cleared
  });

  test('maps field validation errors', () async {
    final tokens = FakeTokenStorage(access: 'abc', refresh: 'r1');
    final main = ScriptedAdapter({
      'POST auth/register/': [
        _Resp(400, {
          'email': ['An account with that email already exists.']
        })
      ],
    });
    final api = _client(tokens,
        main: main, refresh: ScriptedAdapter({'POST x': [_Resp(200, {})]}));

    try {
      await api.post('auth/register/', body: {'email': 'x'});
      fail('should have thrown');
    } on ApiException catch (e) {
      expect(e.statusCode, 400);
      expect(e.firstFieldError, contains('already exists'));
    }
  });
}
