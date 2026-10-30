import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_client.dart';
import '../../core/providers.dart';

/// One incident with its timeline.
class Incident {
  final int id;
  final String title;
  final String severity;
  final String status;
  final String source;
  final bool isOpen;
  final String detail;
  final String resolution;
  final List<Map<String, dynamic>> timeline;

  const Incident({
    required this.id,
    required this.title,
    required this.severity,
    required this.status,
    required this.source,
    required this.isOpen,
    required this.detail,
    required this.resolution,
    this.timeline = const [],
  });

  factory Incident.fromJson(Map<String, dynamic> j) => Incident(
        id: j['id'] as int,
        title: (j['title'] ?? '') as String,
        severity: (j['severity'] ?? '') as String,
        status: (j['status'] ?? '') as String,
        source: (j['source'] ?? '') as String,
        isOpen: (j['is_open'] ?? false) as bool,
        detail: (j['detail'] ?? '') as String,
        resolution: (j['resolution'] ?? '') as String,
        timeline: ((j['timeline'] as List?) ?? [])
            .map((e) => (e as Map).cast<String, dynamic>())
            .toList(),
      );
}

class OperationsRepository {
  final ApiClient _api;
  OperationsRepository(this._api);

  Future<Map<String, dynamic>> overview(int projectId) async {
    final data = await _api.get('projects/$projectId/operations/');
    return (data as Map).cast<String, dynamic>();
  }

  Future<Map<String, dynamic>> incidents(int projectId) async {
    final data = await _api.get('projects/$projectId/incidents/');
    return (data as Map).cast<String, dynamic>();
  }

  /// Full incident incl. its timeline (the list omits the timeline for weight).
  Future<Incident> incident(int incidentId) async {
    final data = await _api.get('incidents/$incidentId/');
    return Incident.fromJson((data as Map).cast<String, dynamic>());
  }

  Future<void> openIncident(int projectId,
          {required String title, String severity = 'medium', String detail = ''}) =>
      _api.post('projects/$projectId/incidents/',
          body: {'title': title, 'severity': severity, 'detail': detail});

  Future<void> transition(int incidentId, String status, {String resolution = ''}) =>
      _api.post('incidents/$incidentId/transition/',
          body: {'status': status, if (resolution.isNotEmpty) 'resolution': resolution});

  Future<void> addNote(int incidentId, String text) =>
      _api.post('incidents/$incidentId/note/', body: {'text': text});
}

final operationsRepositoryProvider = Provider<OperationsRepository>(
  (ref) => OperationsRepository(ref.watch(apiClientProvider)),
);

final operationsProvider =
    FutureProvider.family<Map<String, dynamic>, int>((ref, projectId) {
  return ref.watch(operationsRepositoryProvider).overview(projectId);
});

final incidentsProvider =
    FutureProvider.family<Map<String, dynamic>, int>((ref, projectId) {
  return ref.watch(operationsRepositoryProvider).incidents(projectId);
});

/// The incident lifecycle states, in order.
const kIncidentStatuses = <(String, String)>[
  ('detected', 'Detected'),
  ('investigating', 'Investigating'),
  ('identified', 'Identified'),
  ('mitigating', 'Mitigating'),
  ('resolved', 'Resolved'),
  ('closed', 'Closed'),
];
