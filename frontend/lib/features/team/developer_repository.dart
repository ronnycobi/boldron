import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_client.dart';
import '../../core/providers.dart';

/// Org-scoped developer platform: API keys + webhooks.
class DeveloperRepository {
  final ApiClient _api;
  DeveloperRepository(this._api);

  Future<List<Map<String, dynamic>>> apiKeys(int orgId) async {
    final data = await _api.get('organizations/$orgId/api-keys/');
    return (data as List).map((e) => (e as Map).cast<String, dynamic>()).toList();
  }

  /// Returns the created key incl. its one-time plaintext in `key`.
  Future<Map<String, dynamic>> createApiKey(int orgId, String name) async {
    final data =
        await _api.post('organizations/$orgId/api-keys/', body: {'name': name});
    return (data as Map).cast<String, dynamic>();
  }

  Future<void> revokeApiKey(int orgId, int keyId) =>
      _api.post('organizations/$orgId/api-keys/$keyId/revoke/');

  Future<Map<String, dynamic>> webhooks(int orgId) async {
    final data = await _api.get('organizations/$orgId/webhooks/');
    return (data as Map).cast<String, dynamic>();
  }

  /// Returns the created webhook incl. its one-time `secret`.
  Future<Map<String, dynamic>> createWebhook(
      int orgId, String url, List<String> events) async {
    final data = await _api.post('organizations/$orgId/webhooks/',
        body: {'url': url, 'events': events});
    return (data as Map).cast<String, dynamic>();
  }

  Future<void> deleteWebhook(int orgId, int webhookId) =>
      _api.delete('organizations/$orgId/webhooks/$webhookId/');
}

final developerRepositoryProvider = Provider<DeveloperRepository>(
  (ref) => DeveloperRepository(ref.watch(apiClientProvider)),
);

final apiKeysProvider =
    FutureProvider.family<List<Map<String, dynamic>>, int>((ref, orgId) {
  return ref.watch(developerRepositoryProvider).apiKeys(orgId);
});

final webhooksProvider =
    FutureProvider.family<Map<String, dynamic>, int>((ref, orgId) {
  return ref.watch(developerRepositoryProvider).webhooks(orgId);
});
