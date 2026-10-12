import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_client.dart';
import '../../core/providers.dart';

class BillingRepository {
  final ApiClient _api;
  BillingRepository(this._api);

  Future<Map<String, dynamic>> billing(int orgId) async {
    final data = await _api.get('orgs/$orgId/billing/');
    return (data as Map).cast<String, dynamic>();
  }

  Future<Map<String, dynamic>> usageSummary(int orgId) async {
    final data = await _api.get('orgs/$orgId/usage/summary/');
    return (data as Map).cast<String, dynamic>();
  }

  Future<List<Map<String, dynamic>>> invoices(int orgId) async {
    final data = await _api.get('orgs/$orgId/invoices/');
    return (data as List).map((e) => (e as Map).cast<String, dynamic>()).toList();
  }

  Future<String> requestUpgrade(int orgId, String plan) async {
    final data = await _api.post('orgs/$orgId/upgrade-request/', body: {'plan': plan});
    return (data as Map)['ticket_number'] as String? ?? '';
  }
}

final billingRepositoryProvider = Provider<BillingRepository>(
  (ref) => BillingRepository(ref.watch(apiClientProvider)),
);

final billingProvider =
    FutureProvider.family<Map<String, dynamic>, int>((ref, orgId) {
  return ref.watch(billingRepositoryProvider).billing(orgId);
});

final usageSummaryProvider =
    FutureProvider.family<Map<String, dynamic>, int>((ref, orgId) {
  return ref.watch(billingRepositoryProvider).usageSummary(orgId);
});
