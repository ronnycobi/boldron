import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_client.dart';
import '../../core/providers.dart';

/// A surface a change touches (e.g. "Mobile apps") with a plain-language detail.
class ChangeSurface {
  final String name;
  final String detail;
  const ChangeSurface({required this.name, required this.detail});

  factory ChangeSurface.fromJson(Map<String, dynamic> j) => ChangeSurface(
        name: (j['name'] ?? '') as String,
        detail: (j['detail'] ?? '') as String,
      );
}

/// The customer-facing impact view for a change (spec §6/§19): what it touches and
/// the tests it requires before shipping.
class ChangeImpact {
  final String summary;
  final List<ChangeSurface> surfaces;
  final List<String> requiredTests;
  final int testsRequired;
  final String riskLabel;
  final bool requiresApproval;

  const ChangeImpact({
    required this.summary,
    required this.surfaces,
    required this.requiredTests,
    required this.testsRequired,
    required this.riskLabel,
    required this.requiresApproval,
  });

  bool get isEmpty => surfaces.isEmpty && requiredTests.isEmpty;

  factory ChangeImpact.fromJson(Map<String, dynamic> j) => ChangeImpact(
        summary: (j['summary'] ?? '') as String,
        surfaces: ((j['surfaces'] as List?) ?? [])
            .map((s) => ChangeSurface.fromJson(s as Map<String, dynamic>))
            .toList(),
        requiredTests: ((j['required_tests'] as List?) ?? [])
            .map((e) => e.toString())
            .toList(),
        testsRequired: (j['tests_required'] ?? 0) as int,
        riskLabel: (j['risk_label'] ?? '') as String,
        requiresApproval: (j['requires_approval'] ?? false) as bool,
      );
}

class ChangeRequest {
  final int id;
  final int project;
  final String description;
  final String status;
  final String statusDisplay;
  final Map<String, dynamic> plan;
  final Map<String, dynamic> estimate;
  final bool requiresApproval;
  final bool approved;
  final String risk;
  final ChangeImpact? impact;
  final bool canRollback;

  const ChangeRequest({
    required this.id,
    required this.project,
    required this.description,
    required this.status,
    required this.statusDisplay,
    required this.plan,
    required this.estimate,
    required this.requiresApproval,
    required this.approved,
    required this.risk,
    required this.impact,
    required this.canRollback,
  });

  factory ChangeRequest.fromJson(Map<String, dynamic> j) => ChangeRequest(
        id: j['id'] as int,
        project: (j['project'] ?? 0) as int,
        description: (j['description'] ?? '') as String,
        status: (j['status'] ?? '') as String,
        statusDisplay: (j['status_display'] ?? j['status'] ?? '') as String,
        plan: (j['plan'] as Map?)?.cast<String, dynamic>() ?? const {},
        estimate: (j['estimate'] as Map?)?.cast<String, dynamic>() ?? const {},
        requiresApproval: (j['requires_approval'] ?? false) as bool,
        approved: (j['approved'] ?? false) as bool,
        risk: (j['risk'] ?? '') as String,
        impact: j['impact'] is Map
            ? ChangeImpact.fromJson((j['impact'] as Map).cast<String, dynamic>())
            : null,
        canRollback: (j['can_rollback'] ?? false) as bool,
      );
}

class ChangesRepository {
  final ApiClient _api;
  ChangesRepository(this._api);

  Future<List<ChangeRequest>> list(int projectId) async {
    final data = await _api.get('projects/$projectId/changes/');
    return (data as List)
        .map((c) => ChangeRequest.fromJson(c as Map<String, dynamic>))
        .toList();
  }

  Future<ChangeRequest> create(int projectId, String description) async {
    final data = await _api.post('projects/$projectId/changes/',
        body: {'description': description});
    return ChangeRequest.fromJson(data as Map<String, dynamic>);
  }

  Future<ChangeRequest> get(int id) async {
    final data = await _api.get('changes/$id/');
    return ChangeRequest.fromJson(data as Map<String, dynamic>);
  }

  Future<ChangeRequest> _act(int id, String action) async {
    final data = await _api.post('changes/$id/$action/');
    return ChangeRequest.fromJson(data as Map<String, dynamic>);
  }

  Future<ChangeRequest> approve(int id) => _act(id, 'approve');
  Future<ChangeRequest> implement(int id) => _act(id, 'implement');
  Future<ChangeRequest> rollback(int id) => _act(id, 'rollback');
}

final changesRepositoryProvider = Provider<ChangesRepository>(
  (ref) => ChangesRepository(ref.watch(apiClientProvider)),
);

final changesProvider =
    FutureProvider.family<List<ChangeRequest>, int>((ref, projectId) {
  return ref.watch(changesRepositoryProvider).list(projectId);
});

final changeProvider =
    FutureProvider.family<ChangeRequest, int>((ref, id) {
  return ref.watch(changesRepositoryProvider).get(id);
});
