import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_client.dart';
import '../../core/providers.dart';

/// Localization / i18n (spec §17-18) over the shared backend. Coverage reflects
/// real translations; a bundle flags strings that fall back to the source.
class LocalizationRepository {
  final ApiClient _api;
  LocalizationRepository(this._api);

  Future<Map<String, dynamic>> overview(int projectId) async {
    final data = await _api.get('projects/$projectId/i18n/');
    return (data as Map).cast<String, dynamic>();
  }

  Future<Map<String, dynamic>> bundle(int projectId, String locale) async {
    final data = await _api.get('projects/$projectId/i18n/bundle/?locale=$locale');
    return (data as Map).cast<String, dynamic>();
  }
}

final localizationRepositoryProvider = Provider<LocalizationRepository>(
  (ref) => LocalizationRepository(ref.watch(apiClientProvider)),
);

final localizationProvider =
    FutureProvider.family<Map<String, dynamic>, int>((ref, projectId) {
  return ref.watch(localizationRepositoryProvider).overview(projectId);
});
