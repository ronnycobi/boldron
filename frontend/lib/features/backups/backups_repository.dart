import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_client.dart';
import '../../core/providers.dart';

class Backup {
  final int id;
  final String label;
  final String commitSha;
  final String createdAt;

  const Backup({
    required this.id,
    required this.label,
    required this.commitSha,
    required this.createdAt,
  });

  factory Backup.fromJson(Map<String, dynamic> j) => Backup(
        id: j['id'] as int,
        label: (j['label'] ?? '') as String,
        commitSha: (j['commit_sha'] ?? '') as String,
        createdAt: (j['created_at'] ?? '') as String,
      );
}

class BackupsRepository {
  final ApiClient _api;
  BackupsRepository(this._api);

  Future<List<Backup>> list(int projectId) async {
    final data = await _api.get('projects/$projectId/backups/');
    return (data as List)
        .map((b) => Backup.fromJson(b as Map<String, dynamic>))
        .toList();
  }

  Future<void> create(int projectId, String label) =>
      _api.post('projects/$projectId/backups/', body: {'label': label});

  Future<void> restore(int backupId) =>
      _api.post('backups/$backupId/restore/');
}

final backupsRepositoryProvider = Provider<BackupsRepository>(
  (ref) => BackupsRepository(ref.watch(apiClientProvider)),
);

final backupsProvider =
    FutureProvider.family<List<Backup>, int>((ref, projectId) {
  return ref.watch(backupsRepositoryProvider).list(projectId);
});
