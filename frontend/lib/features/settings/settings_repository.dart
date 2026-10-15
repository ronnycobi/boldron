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
