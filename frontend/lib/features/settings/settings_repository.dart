import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_client.dart';
import '../../core/providers.dart';

class SettingsRepository {
  final ApiClient _api;
  SettingsRepository(this._api);

  Future<void> updateAccount(Map<String, dynamic> fields) =>
      _api.patch('account/', body: fields);

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
