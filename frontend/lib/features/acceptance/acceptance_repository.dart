import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_client.dart';
import '../../core/providers.dart';

/// Acceptance criteria (spec §3) over the shared backend. Honest: the status
/// shown is whatever a person has verified — criteria are never auto-marked met.
class AcceptanceRepository {
  final ApiClient _api;
  AcceptanceRepository(this._api);

  Future<Map<String, dynamic>> list(int projectId) async {
    final data = await _api.get('projects/$projectId/acceptance/');
    return (data as Map).cast<String, dynamic>();
  }

  Future<Map<String, dynamic>> importFromRequirements(int projectId) async {
    final data = await _api.post('projects/$projectId/acceptance/import/');
    return (data as Map).cast<String, dynamic>();
  }

  Future<void> verify(int criterionId, String status, {String note = ''}) =>
      _api.post('acceptance/$criterionId/verify/',
          body: {'status': status, 'note': note});
}

final acceptanceRepositoryProvider = Provider<AcceptanceRepository>(
  (ref) => AcceptanceRepository(ref.watch(apiClientProvider)),
);

final acceptanceProvider =
    FutureProvider.family<Map<String, dynamic>, int>((ref, projectId) {
  return ref.watch(acceptanceRepositoryProvider).list(projectId);
});
