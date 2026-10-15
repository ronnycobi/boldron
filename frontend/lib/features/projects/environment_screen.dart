import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_exception.dart';
import 'projects_repository.dart';

/// A project's environment variables. Values set here are really injected into
/// the project's preview run. Secret values are masked on read (write-only).
/// Setting/deleting requires org management rights (the API enforces it).
class EnvironmentScreen extends ConsumerWidget {
  final int projectId;
  const EnvironmentScreen({super.key, required this.projectId});

  Future<void> _add(BuildContext context, WidgetRef ref) async {
    final result = await showDialog<_NewVar>(
      context: context,
      builder: (_) => const _AddVarDialog(),
    );
    if (result == null) return;
    try {
      await ref.read(projectsRepositoryProvider).setEnvVar(
          projectId, result.key, result.value, isSecret: result.isSecret);
      ref.invalidate(envVarsProvider(projectId));
    } on ApiException catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(e.firstFieldError ?? e.message)));
      }
    }
  }

  Future<void> _delete(BuildContext context, WidgetRef ref, int id) async {
    try {
      await ref.read(projectsRepositoryProvider).deleteEnvVar(projectId, id);
      ref.invalidate(envVarsProvider(projectId));
    } on ApiException catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final vars = ref.watch(envVarsProvider(projectId));
    return Scaffold(
      appBar: AppBar(title: const Text('Environment')),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => _add(context, ref),
        icon: const Icon(Icons.add),
        label: const Text('Variable'),
      ),
      body: vars.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(e.toString())),
        data: (list) => ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Text(
              'Configuration injected into this project when it runs in preview. '
              'Mark sensitive values as secret — they are stored to inject but '
              'never shown again.',
              style: Theme.of(context).textTheme.bodySmall,
            ),
            const SizedBox(height: 10),
            if (list.isEmpty)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 16),
                child: Text('No environment variables yet.'),
              )
            else
              for (final v in list)
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: Text('${v['key']}',
                      style: const TextStyle(fontFamily: 'monospace')),
                  subtitle: Text(
                    (v['is_secret'] ?? false) as bool
                        ? 'secret'
                        : '${v['value']}',
                    style: const TextStyle(fontFamily: 'monospace', fontSize: 12.5),
                  ),
                  trailing: IconButton(
                    icon: const Icon(Icons.delete_outline),
                    onPressed: () => _delete(context, ref, v['id'] as int),
                  ),
                ),
            const SizedBox(height: 72),
          ],
        ),
      ),
    );
  }
}

class _NewVar {
  final String key;
  final String value;
  final bool isSecret;
  const _NewVar(this.key, this.value, this.isSecret);
}

class _AddVarDialog extends StatefulWidget {
  const _AddVarDialog();

  @override
  State<_AddVarDialog> createState() => _AddVarDialogState();
}

class _AddVarDialogState extends State<_AddVarDialog> {
  final _key = TextEditingController();
  final _value = TextEditingController();
  bool _secret = false;

  @override
  void dispose() {
    _key.dispose();
    _value.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Add / update variable'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          TextField(
            controller: _key,
            decoration: const InputDecoration(
                labelText: 'Key', hintText: 'DATABASE_URL'),
          ),
          TextField(
            controller: _value,
            decoration: const InputDecoration(labelText: 'Value'),
          ),
          const SizedBox(height: 6),
          StatefulBuilder(
            builder: (ctx, setInner) => CheckboxListTile(
              contentPadding: EdgeInsets.zero,
              value: _secret,
              title: const Text('Secret (mask after saving)'),
              onChanged: (v) => setInner(() => _secret = v ?? false),
            ),
          ),
        ],
      ),
      actions: [
        TextButton(
            onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
        FilledButton(
          onPressed: () {
            if (_key.text.trim().isEmpty) return;
            Navigator.pop(context,
                _NewVar(_key.text.trim(), _value.text, _secret));
          },
          child: const Text('Save'),
        ),
      ],
    );
  }
}
