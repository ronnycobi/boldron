import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_client.dart';
import '../../core/providers.dart';

/// A project's files & media — list, upload, delete (spec §17).
class FilesRepository {
  final ApiClient _api;
  FilesRepository(this._api);

  Future<List<Map<String, dynamic>>> list(int projectId) async {
    final data = await _api.get('files/', query: {'project': '$projectId'});
    return (data as List).map((e) => (e as Map).cast<String, dynamic>()).toList();
  }

  Future<Map<String, dynamic>> upload(int orgId, int projectId, String filePath,
      {String filename = 'upload.jpg', bool isPublic = false}) async {
    final data = await _api.postFile('files/',
        field: 'file',
        filePath: filePath,
        filename: filename,
        fields: {
          'organization': '$orgId',
          'project': '$projectId',
          'is_public': isPublic ? 'true' : 'false',
        });
    return (data as Map).cast<String, dynamic>();
  }

  Future<void> delete(int fileId) => _api.delete('files/$fileId/');
}

final filesRepositoryProvider = Provider<FilesRepository>(
  (ref) => FilesRepository(ref.watch(apiClientProvider)),
);

final projectFilesProvider =
    FutureProvider.family<List<Map<String, dynamic>>, int>(
  (ref, projectId) => ref.watch(filesRepositoryProvider).list(projectId),
);
