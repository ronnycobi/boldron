import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_client.dart';
import '../../core/providers.dart';

/// The Legal Center (spec §53) over the shared backend: published documents, the
/// user's own versioned acceptances, and any pending acceptances. Recording an
/// acceptance is a durable, versioned act — the same engine the web uses.
class LegalRepository {
  final ApiClient _api;
  LegalRepository(this._api);

  Future<List<Map<String, dynamic>>> documents() async {
    final data = await _api.get('legal/documents/');
    return (((data as Map)['documents'] as List?) ?? [])
        .map((e) => (e as Map).cast<String, dynamic>())
        .toList();
  }

  Future<List<Map<String, dynamic>>> acceptances() async {
    final data = await _api.get('legal/acceptances/');
    return (((data as Map)['acceptances'] as List?) ?? [])
        .map((e) => (e as Map).cast<String, dynamic>())
        .toList();
  }

  Future<List<Map<String, dynamic>>> pending() async {
    final data = await _api.get('legal/pending/');
    return (((data as Map)['pending'] as List?) ?? [])
        .map((e) => (e as Map).cast<String, dynamic>())
        .toList();
  }

  Future<void> accept(String slug) =>
      _api.post('legal/acceptances/', body: {'document': slug, 'method': 'mobile'});
}

final legalRepositoryProvider =
    Provider<LegalRepository>((ref) => LegalRepository(ref.watch(apiClientProvider)));

/// Combined view model: documents + acceptance map + pending.
final legalCenterProvider =
    FutureProvider.autoDispose<Map<String, dynamic>>((ref) async {
  final repo = ref.watch(legalRepositoryProvider);
  final docs = await repo.documents();
  final accepted = await repo.acceptances();
  final pending = await repo.pending();
  final acceptedBySlug = {for (final a in accepted) a['slug']: a};
  return {"documents": docs, "accepted": acceptedBySlug, "pending": pending};
});
