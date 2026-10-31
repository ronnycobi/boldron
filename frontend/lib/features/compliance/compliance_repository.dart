import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_client.dart';
import '../../core/providers.dart';

/// Compliance (spec §16) over the shared backend. Platform-provided controls are
/// auto-evidenced; the rest need a human attestation — never auto-claimed met.
class ComplianceRepository {
  final ApiClient _api;
  ComplianceRepository(this._api);

  Future<Map<String, dynamic>> overview(int projectId) async {
    final data = await _api.get('projects/$projectId/compliance/');
    return (data as Map).cast<String, dynamic>();
  }

  Future<void> attest(int controlId, String status, {String evidence = ''}) =>
      _api.post('compliance/controls/$controlId/attest/',
          body: {'status': status, 'evidence': evidence});
}

final complianceRepositoryProvider = Provider<ComplianceRepository>(
  (ref) => ComplianceRepository(ref.watch(apiClientProvider)),
);

final complianceProvider =
    FutureProvider.family<Map<String, dynamic>, int>((ref, projectId) {
  return ref.watch(complianceRepositoryProvider).overview(projectId);
});
