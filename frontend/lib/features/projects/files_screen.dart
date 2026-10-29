import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:image_picker/image_picker.dart';

import '../../core/api_exception.dart';
import 'files_repository.dart';
import 'projects_repository.dart';

/// A project's files & media. Lists stored files with image thumbnails; uploads
/// an image from the device; deletes. Private files are only reachable by
/// members (enforced server-side). Non-image uploads are a web affordance.
class FilesScreen extends ConsumerWidget {
  final int projectId;
  const FilesScreen({super.key, required this.projectId});

  Future<void> _upload(BuildContext context, WidgetRef ref) async {
    final picker = ImagePicker();
    final picked = await picker.pickImage(source: ImageSource.gallery);
    if (picked == null) return;
    try {
      final project = await ref.read(projectsRepositoryProvider).get(projectId);
      await ref.read(filesRepositoryProvider).upload(
          project.organization, projectId, picked.path,
          filename: picked.name);
      ref.invalidate(projectFilesProvider(projectId));
      if (context.mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(const SnackBar(content: Text('File uploaded.')));
      }
    } on ApiException catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(e.firstFieldError ?? e.message)));
      }
    }
  }

  Future<void> _delete(BuildContext context, WidgetRef ref, int id) async {
    try {
      await ref.read(filesRepositoryProvider).delete(id);
      ref.invalidate(projectFilesProvider(projectId));
    } on ApiException catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final files = ref.watch(projectFilesProvider(projectId));
    return Scaffold(
      appBar: AppBar(title: const Text('Files & media')),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => _upload(context, ref),
        icon: const Icon(Icons.upload_file),
        label: const Text('Upload image'),
      ),
      body: files.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(e.toString())),
        data: (list) => list.isEmpty
            ? const Center(
                child: Padding(
                  padding: EdgeInsets.all(24),
                  child: Text(
                    'No files yet. Upload an image here, or add documents from '
                    'the web app.',
                    textAlign: TextAlign.center,
                  ),
                ),
              )
            : ListView.separated(
                padding: const EdgeInsets.all(16),
                itemCount: list.length,
                separatorBuilder: (_, __) => const SizedBox(height: 10),
                itemBuilder: (_, i) {
                  final f = list[i];
                  final thumb = f['thumbnail_url'] as String?;
                  return Card(
                    child: ListTile(
                      leading: thumb != null
                          ? ClipRRect(
                              borderRadius: BorderRadius.circular(8),
                              child: Image.network(thumb,
                                  width: 44, height: 44, fit: BoxFit.cover,
                                  errorBuilder: (_, __, ___) =>
                                      const Icon(Icons.image_outlined)),
                            )
                          : const Icon(Icons.insert_drive_file_outlined, size: 32),
                      title: Text('${f['name']}',
                          maxLines: 1, overflow: TextOverflow.ellipsis),
                      subtitle: Text(
                          '${_fmtSize(f['size'])} · ${(f['is_public'] ?? false) as bool ? 'Public' : 'Private'}'),
                      trailing: IconButton(
                        icon: const Icon(Icons.delete_outline),
                        onPressed: () => _delete(context, ref, f['id'] as int),
                      ),
                    ),
                  );
                },
              ),
      ),
    );
  }

  String _fmtSize(dynamic bytes) {
    final b = (bytes is num) ? bytes.toInt() : 0;
    if (b < 1024) return '$b B';
    if (b < 1024 * 1024) return '${(b / 1024).toStringAsFixed(0)} KB';
    return '${(b / (1024 * 1024)).toStringAsFixed(1)} MB';
  }
}
