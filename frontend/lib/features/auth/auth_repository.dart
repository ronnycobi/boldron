import '../../core/api_client.dart';
import '../../core/token_storage.dart';
import 'auth_models.dart';

/// Talks to the auth endpoints and persists tokens. The controller uses this;
/// widgets never touch the API client directly (spec §32/§33).
class AuthRepository {
  final ApiClient _api;
  final TokenStorage _tokens;

  AuthRepository(this._api, this._tokens);

  Future<AuthUser> login(String email, String password) async {
    final data = await _api.post('auth/token/', body: {
      'email': email.trim(),
      'password': password,
    });
    return _persistAndParse(data as Map<String, dynamic>);
  }

  Future<AuthUser> register({
    required String email,
    required String password,
    String fullName = '',
    String orgName = '',
  }) async {
    final data = await _api.post('auth/register/', body: {
      'email': email.trim(),
      'full_name': fullName.trim(),
      'org_name': orgName.trim(),
      'password1': password,
      'password2': password,
    });
    return _persistAndParse(data as Map<String, dynamic>);
  }

  /// Fetch the current user (used on startup when tokens already exist).
  Future<AuthUser> me() async {
    final data = await _api.get('me/');
    return AuthUser.fromJson(data as Map<String, dynamic>);
  }

  Future<void> requestPasswordReset(String email) =>
      _api.post('auth/password-reset/', body: {'email': email.trim()});

  Future<void> resendVerification() => _api.post('auth/resend-verification/');

  Future<void> logout() async {
    final refresh = await _tokens.readRefresh();
    try {
      if (refresh != null) {
        await _api.post('auth/logout/', body: {'refresh': refresh});
      }
    } catch (_) {
      // Even if the server call fails, we still clear local tokens below.
    }
    await _tokens.clear();
  }

  Future<AuthUser> _persistAndParse(Map<String, dynamic> data) async {
    await _tokens.save(
      access: data['access'] as String,
      refresh: data['refresh'] as String,
    );
    return AuthUser.fromJson(data['user'] as Map<String, dynamic>);
  }
}
