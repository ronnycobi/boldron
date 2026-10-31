import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_client.dart';
import '../../core/providers.dart';

/// Explain-my-application (spec §29) over the shared backend. A plain-language,
/// customer-safe account composed from real project knowledge.
class ExplainRepository {
  final ApiClient _api;
  ExplainRepository(this._api);

  Future<Map<String, dynamic>> explain(int projectId) async {
    final data = await _api.get('projects/$projectId/explain/');
    return (data as Map).cast<String, dynamic>();
  }
}

final explainRepositoryProvider = Provider<ExplainRepository>(
  (ref) => ExplainRepository(ref.watch(apiClientProvider)),
);

final explainProvider =
    FutureProvider.family<Map<String, dynamic>, int>((ref, projectId) {
  return ref.watch(explainRepositoryProvider).explain(projectId);
});
