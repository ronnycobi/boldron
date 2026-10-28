import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_exception.dart';
import 'projects_repository.dart';

/// Per-project AI preference — overrides the org default for this project's
/// builds. Soft: honoured only when available. Blank inherits the org.
class ProjectAiScreen extends ConsumerStatefulWidget {
  final int projectId;
  const ProjectAiScreen({super.key, required this.projectId});

  @override
  ConsumerState<ProjectAiScreen> createState() => _ProjectAiScreenState();
}

class _ProjectAiScreenState extends ConsumerState<ProjectAiScreen> {
  String _provider = '';
  String _model = '';
  bool _prefilled = false;
  bool _saving = false;

  Future<void> _save() async {
    setState(() => _saving = true);
    try {
      await ref.read(projectsRepositoryProvider)
          .setProjectAi(widget.projectId, provider: _provider, model: _model);
      ref.invalidate(projectAiProvider(widget.projectId));
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Project AI settings saved.')));
      }
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(e.firstFieldError ?? e.message)));
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final ai = ref.watch(projectAiProvider(widget.projectId));
    return Scaffold(
      appBar: AppBar(title: const Text('Project AI')),
      body: ai.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(e.toString())),
        data: (d) {
          final options = ((d['options'] as List?) ?? [])
              .map((o) => (o as Map).cast<String, dynamic>()).toList();
          final effective = (d['effective'] as Map?) ?? {};
          if (!_prefilled) {
            final own = (d['own'] as Map?) ?? {};
            _provider = '${own['preferred_provider'] ?? ''}';
            _model = '${own['preferred_model'] ?? ''}';
            _prefilled = true;
          }
          final models = options.firstWhere(
                  (o) => o['provider'] == _provider,
                  orElse: () => <String, dynamic>{'models': []})['models'] as List? ??
              [];
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Text(
                'Overrides the organization default for this project. '
                'Currently: ${effective['preferred_provider']?.toString().isNotEmpty == true ? effective['preferred_provider'] : 'automatic'}.',
                style: Theme.of(context).textTheme.bodySmall,
              ),
              const SizedBox(height: 14),
              if (options.isEmpty)
                const Text('No AI providers are connected on this deployment.')
              else ...[
                DropdownButtonFormField<String>(
                  value: _provider,
                  decoration: const InputDecoration(labelText: 'Preferred provider'),
                  items: [
                    const DropdownMenuItem(value: '', child: Text('Inherit organization default')),
                    for (final o in options)
                      DropdownMenuItem(
                        value: '${o['provider']}',
                        child: Text('${o['provider']}'
                            '${(o['available'] ?? false) as bool ? '' : ' (not connected)'}'),
                      ),
                  ],
                  onChanged: (v) => setState(() {
                    _provider = v ?? '';
                    _model = '';
                  }),
                ),
                const SizedBox(height: 12),
                DropdownButtonFormField<String>(
                  value: _model.isEmpty ? '' : _model,
                  decoration: const InputDecoration(labelText: 'Preferred model (optional)'),
                  items: [
                    const DropdownMenuItem(value: '', child: Text('Best available')),
                    for (final m in models)
                      DropdownMenuItem(
                          value: '${(m as Map)['model']}', child: Text('${m['label']}')),
                  ],
                  onChanged: _provider.isEmpty
                      ? null
                      : (v) => setState(() => _model = v ?? ''),
                ),
                const SizedBox(height: 18),
                FilledButton(
                  onPressed: _saving ? null : _save,
                  child: Text(_saving ? 'Saving…' : 'Save AI settings'),
                ),
              ],
            ],
          );
        },
      ),
    );
  }
}
