import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_exception.dart';
import 'backups_repository.dart';

/// Project restore points (spec §13). Create a snapshot before a big change;
/// restore any time. Restore is code-only (not database data).
class BackupsScreen extends ConsumerStatefulWidget {
  final int projectId;
  const BackupsScreen({super.key, required this.projectId});

  @override
  ConsumerState<BackupsScreen> createState() => _BackupsScreenState();
}

class _BackupsScreenState extends ConsumerState<BackupsScreen> {
  bool _busy = false;

  Future<void> _run(Future<void> Function() action, String ok) async {
    setState(() => _busy = true);
    try {
      await action();
      ref.invalidate(backupsProvider(widget.projectId));
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(ok)));
      }
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(e.message)));
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _create() async {
    final controller = TextEditingController(text: 'Snapshot');
    final label = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Create a backup'),
        content: TextField(
          controller: controller,
          autofocus: true,
          decoration: const InputDecoration(hintText: 'e.g. Before payments'),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
          FilledButton(
              onPressed: () => Navigator.pop(ctx, controller.text.trim()),
              child: const Text('Create')),
        ],
      ),
    );
    if (label != null && label.isNotEmpty) {
      await _run(
          () => ref
              .read(backupsRepositoryProvider)
              .create(widget.projectId, label),
          'Backup created.');
    }
  }

  Future<void> _restore(Backup b) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('Restore "${b.label}"?'),
        content: const Text(
            'Your project files are reset to this snapshot. This restores code, '
            'not database data.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Cancel')),
          FilledButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Restore')),
        ],
      ),
    );
    if (ok == true) {
      await _run(() => ref.read(backupsRepositoryProvider).restore(b.id),
          'Restored.');
    }
  }

  @override
  Widget build(BuildContext context) {
    final backups = ref.watch(backupsProvider(widget.projectId));
    return Scaffold(
      appBar: AppBar(title: const Text('Backups')),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _busy ? null : _create,
        icon: const Icon(Icons.add),
        label: const Text('New backup'),
      ),
      body: backups.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(e.toString())),
        data: (items) => items.isEmpty
            ? const Center(child: Text('No backups yet.'))
            : ListView.separated(
                itemCount: items.length,
                separatorBuilder: (_, __) => const Divider(height: 1),
                itemBuilder: (_, i) {
                  final b = items[i];
                  return ListTile(
                    leading: const Icon(Icons.history),
                    title: Text(b.label),
                    subtitle: Text(b.commitSha.isEmpty
                        ? b.createdAt
                        : '${b.commitSha.substring(0, b.commitSha.length.clamp(0, 10))} · ${b.createdAt}'),
                    trailing: TextButton(
                      onPressed: _busy ? null : () => _restore(b),
                      child: const Text('Restore'),
                    ),
                  );
                },
              ),
      ),
    );
  }
}
