import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_exception.dart';
import 'projects_repository.dart';

/// A project's environment variables, per environment (development / staging /
/// production). Values are really injected into the project's run for that
/// environment. Secret values are masked on read (write-only) and encrypted at
/// rest. Setting/deleting requires org management rights (the API enforces it).
class EnvironmentScreen extends ConsumerStatefulWidget {
  final int projectId;
  const EnvironmentScreen({super.key, required this.projectId});

  @override
  ConsumerState<EnvironmentScreen> createState() => _EnvironmentScreenState();
}

class _EnvironmentScreenState extends ConsumerState<EnvironmentScreen> {
  String _env = 'development';

  static const _envs = <(String, String)>[
    ('development', 'Development'),
    ('staging', 'Staging'),
    ('production', 'Production'),
  ];

  ({int projectId, String environment}) get _key =>
      (projectId: widget.projectId, environment: _env);

  Future<void> _add(BuildContext context) async {
    final result = await showDialog<_NewVar>(
      context: context,
      builder: (_) => const _AddVarDialog(),
    );
    if (result == null) return;
    try {
      await ref.read(projectsRepositoryProvider).setEnvVar(
          widget.projectId, result.key, result.value,
          isSecret: result.isSecret, environment: _env);
      ref.invalidate(envVarsProvider(_key));
    } on ApiException catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(e.firstFieldError ?? e.message)));
      }
    }
  }

  Future<void> _delete(BuildContext context, int id) async {
    try {
      await ref.read(projectsRepositoryProvider).deleteEnvVar(widget.projectId, id);
      ref.invalidate(envVarsProvider(_key));
    } on ApiException catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final vars = ref.watch(envVarsProvider(_key));
    return Scaffold(
      appBar: AppBar(title: const Text('Environment')),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => _add(context),
        icon: const Icon(Icons.add),
        label: const Text('Variable'),
      ),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 10, 12, 4),
            child: SegmentedButton<String>(
              segments: [
                for (final e in _envs)
                  ButtonSegment(value: e.$1, label: Text(e.$2)),
              ],
              selected: {_env},
              showSelectedIcon: false,
              onSelectionChanged: (s) => setState(() => _env = s.first),
            ),
          ),
          Expanded(
            child: vars.when(
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (e, _) => Center(child: Text(e.toString())),
              data: (payload) {
                final list = ((payload['variables'] as List?) ?? [])
                    .map((e) => (e as Map).cast<String, dynamic>())
                    .toList();
                return ListView(
                  padding: const EdgeInsets.all(16),
                  children: [
                    Text(
                      'Configuration injected into this project when it runs in the '
                      '$_env environment. Mark sensitive values as secret — they are '
                      'encrypted at rest and never shown again.',
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                    const SizedBox(height: 10),
                    if (list.isEmpty)
                      const Padding(
                        padding: EdgeInsets.symmetric(vertical: 16),
                        child: Text('No variables in this environment yet.'),
                      )
                    else
                      for (final v in list)
                        ListTile(
                          contentPadding: EdgeInsets.zero,
                          title: Text('${v['key']}',
                              style: const TextStyle(fontFamily: 'monospace')),
                          subtitle: Text(
                            (v['is_secret'] ?? false) as bool
                                ? 'secret · encrypted'
                                : '${v['value']}',
                            style: const TextStyle(
                                fontFamily: 'monospace', fontSize: 12.5),
                          ),
                          trailing: IconButton(
                            icon: const Icon(Icons.delete_outline),
                            onPressed: () => _delete(context, v['id'] as int),
                          ),
                        ),
                    const SizedBox(height: 72),
                  ],
                );
              },
            ),
          ),
        ],
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
