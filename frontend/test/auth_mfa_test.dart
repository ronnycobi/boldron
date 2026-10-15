import 'dart:convert';
import 'dart:typed_data';

import 'package:boldron_app/core/api_client.dart';
import 'package:boldron_app/features/auth/auth_repository.dart';
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/fake_token_storage.dart';

/// Minimal scriptable adapter (one response per matched METHOD+path substring).
class _Adapter implements HttpClientAdapter {
  final Map<String, (int, Object)> script;
  _Adapter(this.script);

  @override
  Future<ResponseBody> fetch(RequestOptions options,
      Stream<Uint8List>? requestStream, Future<void>? cancelFuture) async {
    final key = script.keys.firstWhere(
      (k) {
        final p = k.split(' ');
        return options.method == p[0] && options.path.contains(p[1]);
      },
      orElse: () => throw StateError('No script for ${options.method} ${options.path}'),
    );
    final (status, body) = script[key]!;
    return ResponseBody.fromString(jsonEncode(body), status,
        headers: {Headers.contentTypeHeader: ['application/json']});
  }

  @override
  void close({bool force = false}) {}
}

ApiClient _client(FakeTokenStorage tokens, _Adapter adapter) => ApiClient(
      tokens: tokens,
      dio: Dio()..httpClientAdapter = adapter,
      refreshDio: Dio()..httpClientAdapter = _Adapter({'POST x': (200, {})}),
      baseUrl: 'http://test/api/v1/',
    );

void main() {
  test('login returns an MFA challenge instead of tokens when required', () async {
    final tokens = FakeTokenStorage();
    final repo = AuthRepository(
      _client(tokens, _Adapter({
        'POST auth/token/': (200, {'mfa_required': true, 'mfa_token': 'chal-123'}),
      })),
      tokens,
    );
    final outcome = await repo.login('a@b.com', 'pw');
    expect(outcome.mfaRequired, isTrue);
    expect(outcome.mfaToken, 'chal-123');
    expect(outcome.user, isNull);
    expect(tokens.access, isNull); // no tokens persisted at the password step
  });

  test('login returns the user directly when MFA is off', () async {
    final tokens = FakeTokenStorage();
    final repo = AuthRepository(
      _client(tokens, _Adapter({
        'POST auth/token/': (200, {
          'access': 'A',
          'refresh': 'R',
          'user': {'id': 1, 'email': 'a@b.com'},
        }),
      })),
      tokens,
    );
    final outcome = await repo.login('a@b.com', 'pw');
    expect(outcome.mfaRequired, isFalse);
    expect(outcome.user!.email, 'a@b.com');
    expect(tokens.access, 'A');
  });

  test('verifyMfa exchanges the challenge + code for tokens', () async {
    final tokens = FakeTokenStorage();
    final repo = AuthRepository(
      _client(tokens, _Adapter({
        'POST auth/mfa/verify/': (200, {
          'access': 'A2',
          'refresh': 'R2',
          'user': {'id': 1, 'email': 'a@b.com'},
        }),
      })),
      tokens,
    );
    final user = await repo.verifyMfa('chal-123', '123456');
    expect(user.email, 'a@b.com');
    expect(tokens.access, 'A2');
    expect(tokens.refresh, 'R2');
  });
}
