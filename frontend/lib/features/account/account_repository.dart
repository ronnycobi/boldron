import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_client.dart';
import '../../core/providers.dart';
import '../../core/token_storage.dart';
import '../auth/auth_models.dart';

/// Account & security operations (spec §4). Password change and "sign out other
/// sessions" reissue the token pair; this persists the new tokens so the caller
/// stays signed in.
class AccountRepository {
  final ApiClient _api;
  final TokenStorage _tokens;

  AccountRepository(this._api, this._tokens);

  Future<AuthUser> updateProfile(Map<String, dynamic> fields) async {
    final data = await _api.patch('account/', body: fields);
    return AuthUser.fromJson(data as Map<String, dynamic>);
  }

  Future<AuthUser> changePassword({
    required String oldPassword,
    required String newPassword,
  }) async {
    final data = await _api.post('account/password/', body: {
      'old_password': oldPassword,
      'new_password1': newPassword,
      'new_password2': newPassword,
    });
    return _persist(data as Map<String, dynamic>);
  }

  Future<AuthUser> logoutOtherSessions() async {
    final data = await _api.post('account/logout-all/');
    return _persist(data as Map<String, dynamic>);
  }

  Future<AuthUser> uploadAvatar(String filePath) async {
    final data = await _api.postFile('account/avatar/',
        field: 'avatar', filePath: filePath, filename: 'avatar.jpg');
    return AuthUser.fromJson(data as Map<String, dynamic>);
  }

  Future<AuthUser> removeAvatar() async {
    final data = await _api.delete('account/avatar/');
    return AuthUser.fromJson(data as Map<String, dynamic>);
  }

  Future<AuthUser> _persist(Map<String, dynamic> data) async {
    if (data['access'] != null && data['refresh'] != null) {
      await _tokens.save(
        access: data['access'] as String,
        refresh: data['refresh'] as String,
      );
    }
    return AuthUser.fromJson(data['user'] as Map<String, dynamic>);
  }
}

final accountRepositoryProvider = Provider<AccountRepository>(
  (ref) => AccountRepository(
    ref.watch(apiClientProvider),
    ref.watch(tokenStorageProvider),
  ),
);
