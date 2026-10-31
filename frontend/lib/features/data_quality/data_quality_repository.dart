import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_client.dart';
import '../../core/providers.dart';

/// Data quality (spec §9) over the shared backend. Scores and issues are true
/// counts from the rows checked — never estimated.
class DataQualityRepository {
  final ApiClient _api;
  DataQualityRepository(this._api);

  Future<Map<String, dynamic>> overview(int projectId) async {
    final data = await _api.get('projects/$projectId/data-quality/');
    return (data as Map).cast<String, dynamic>();
  }
}

final dataQualityRepositoryProvider = Provider<DataQualityRepository>(
  (ref) => DataQualityRepository(ref.watch(apiClientProvider)),
);

final dataQualityProvider =
    FutureProvider.family<Map<String, dynamic>, int>((ref, projectId) {
  return ref.watch(dataQualityRepositoryProvider).overview(projectId);
});
