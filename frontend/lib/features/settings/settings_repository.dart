import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_client.dart';
import '../../core/providers.dart';

class SettingsRepository {
  final ApiClient _api;
  SettingsRepository(this._api);

  Future<void> updateAccount(Map<String, dynamic> fields) =>
      _api.patch('account/', body: fields);

  /// The settings control-center overview (alerts + status + section map).
  Future<Map<String, dynamic>> overview() async {
    final data = await _api.get('settings/overview/');
    return (data as Map).cast<String, dynamic>();
  }

  /// Account Security Center: status + active sessions + login history.
  Future<Map<String, dynamic>> security() async {
    final data = await _api.get('settings/security/');
    return (data as Map).cast<String, dynamic>();
  }

  /// Revoke one of the user's own web sessions by its id.
  Future<void> revokeSession(int sessionId) =>
      _api.post('settings/sessions/$sessionId/revoke/');

  /// Begin MFA enrolment → {secret, otpauth_uri, qr_svg}.
  Future<Map<String, dynamic>> mfaEnroll() async {
    final data = await _api.post('settings/mfa/enroll/');
    return (data as Map).cast<String, dynamic>();
  }

  /// Confirm enrolment with a live code → the one-time recovery codes.
  Future<List<String>> mfaConfirm(String code) async {
    final data = await _api.post('settings/mfa/confirm/', body: {'code': code.trim()});
    return ((data as Map)['recovery_codes'] as List).cast<String>();
  }

  /// Disable MFA (re-auth with the current password).
  Future<void> mfaDisable(String password) =>
      _api.post('settings/mfa/disable/', body: {'password': password});

  /// Regenerate recovery codes (re-auth) → the new one-time codes.
  Future<List<String>> mfaRegenerateRecoveryCodes(String password) async {
    final data = await _api
        .post('settings/mfa/recovery-codes/', body: {'password': password});
    return ((data as Map)['recovery_codes'] as List).cast<String>();
  }

  /// Per-user notification preferences (categories + current values).
  Future<Map<String, dynamic>> notificationPrefs() async {
    final data = await _api.get('account/notifications/');
    return (data as Map).cast<String, dynamic>();
  }

  Future<Map<String, dynamic>> updateNotificationPrefs(
      Map<String, bool> values) async {
    final data = await _api.patch('account/notifications/', body: values);
    return ((data as Map)['preferences'] as Map).cast<String, dynamic>();
  }

  /// The signed-in user's own exported data (JSON).
  Future<Map<String, dynamic>> accountExport() async {
    final data = await _api.get('account/export/');
    return (data as Map).cast<String, dynamic>();
  }

  Future<Map<String, dynamic>> orgExport(int orgId) async {
    final data = await _api.get('organizations/$orgId/export/');
    return (data as Map).cast<String, dynamic>();
  }

  /// Single sign-on status (providers appear only when configured).
  Future<Map<String, dynamic>> connectedAccounts() async {
    final data = await _api.get('account/connected/');
    return (data as Map).cast<String, dynamic>();
  }

  Future<List<Map<String, dynamic>>> integrations() async {
    final data = await _api.get('integrations/');
    return ((data as Map)['integrations'] as List)
        .map((e) => (e as Map).cast<String, dynamic>())
        .toList();
  }
}

final settingsRepositoryProvider = Provider<SettingsRepository>(
  (ref) => SettingsRepository(ref.watch(apiClientProvider)),
);

final integrationsProvider = FutureProvider<List<Map<String, dynamic>>>(
  (ref) => ref.watch(settingsRepositoryProvider).integrations(),
);

final settingsOverviewProvider = FutureProvider<Map<String, dynamic>>(
  (ref) => ref.watch(settingsRepositoryProvider).overview(),
);

final securityProvider = FutureProvider<Map<String, dynamic>>(
  (ref) => ref.watch(settingsRepositoryProvider).security(),
);

final notificationPrefsProvider = FutureProvider<Map<String, dynamic>>(
  (ref) => ref.watch(settingsRepositoryProvider).notificationPrefs(),
);

final connectedAccountsProvider = FutureProvider<Map<String, dynamic>>(
  (ref) => ref.watch(settingsRepositoryProvider).connectedAccounts(),
);
