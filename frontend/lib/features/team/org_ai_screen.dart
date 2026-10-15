import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_exception.dart';
import 'team_repository.dart';

/// Organization AI settings: a soft preferred provider/model for the org's
/// builds. The preference only applies when that provider/model is connected —
/// the router falls back otherwise. API keys are environment-only and never
/// shown here.
class OrgAiScreen extends ConsumerStatefulWidget {
  final int orgId;
  const OrgAiScreen({super.key, required this.orgId});

  @override
  ConsumerState<OrgAiScreen> createState() => _OrgAiScreenState();
}

class _OrgAiScreenState extends ConsumerState<OrgAiScreen> {
  String _provider = '';
  String _model = '';
  bool _prefilled = false;
  bool _saving = false;

  Future<void> _save() async {
    setState(() => _saving = true);
    try {
      await ref.read(teamRepositoryProvider).updateAiSettings(
            widget.orgId,
            provider: _provider,
            model: _model,
          );
      ref.invalidate(orgAiProvider(widget.orgId));
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('AI settings saved.')));
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
    final ai = ref.watch(orgAiProvider(widget.orgId));
    return Scaffold(
      appBar: AppBar(title: const Text('AI settings')),
      body: ai.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(e.toString())),
        data: (d) {
          final canManage = (d['can_manage'] ?? false) as bool;
          final generation = (d['generation'] as Map?) ?? {};
          final options = ((d['options'] as List?) ?? [])
              .map((o) => (o as Map).cast<String, dynamic>())
              .toList();
          if (!_prefilled) {
            final prefs = (d['preferences'] as Map?) ?? {};
            _provider = '${prefs['preferred_provider'] ?? ''}';
            _model = '${prefs['preferred_model'] ?? ''}';
            _prefilled = true;
          }
          final live = (generation['live'] ?? false) as bool;
          final models = options
              .firstWhere((o) => o['provider'] == _provider,
                  orElse: () => <String, dynamic>{'models': []})['models'] as List? ??
              [];
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Container(
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  color: live
                      ? Theme.of(context).cardColor
                      : Theme.of(context).colorScheme.tertiaryContainer,
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Text('${generation['message'] ?? ''}',
                    style: Theme.of(context).textTheme.bodySmall),
              ),
              const SizedBox(height: 16),
              if (options.isEmpty)
                const Text(
                  'No AI providers are connected on this deployment. Provider keys '
                  'are set via the environment; once connected they appear here.',
                )
              else ...[
                Text('Preferred provider',
                    style: Theme.of(context).textTheme.labelLarge),
                const SizedBox(height: 6),
                DropdownButtonFormField<String>(
                  value: _provider,
                  decoration: const InputDecoration(),
                  items: [
                    const DropdownMenuItem(
                        value: '', child: Text('Platform default (automatic)')),
                    for (final o in options)
                      DropdownMenuItem(
                        value: '${o['provider']}',
                        child: Text('${o['provider']}'
                            '${(o['available'] ?? false) as bool ? '' : ' (not connected)'}'),
                      ),
                  ],
                  onChanged: canManage
                      ? (v) => setState(() {
                            _provider = v ?? '';
                            _model = '';
                          })
                      : null,
                ),
                const SizedBox(height: 14),
                Text('Preferred model (optional)',
                    style: Theme.of(context).textTheme.labelLarge),
                const SizedBox(height: 6),
                DropdownButtonFormField<String>(
                  value: _model.isEmpty ? '' : _model,
                  decoration: const InputDecoration(),
                  items: [
                    const DropdownMenuItem(
                        value: '', child: Text('Best available for the provider')),
                    for (final m in models)
                      DropdownMenuItem(
                          value: '${(m as Map)['model']}',
                          child: Text('${m['label']}')),
                  ],
                  onChanged: (canManage && _provider.isNotEmpty)
                      ? (v) => setState(() => _model = v ?? '')
                      : null,
                ),
                const SizedBox(height: 18),
                if (canManage)
                  FilledButton(
                    onPressed: _saving ? null : _save,
                    child: Text(_saving ? 'Saving…' : 'Save AI settings'),
                  )
                else
                  Text('You need owner or admin rights to change AI settings.',
                      style: Theme.of(context).textTheme.bodySmall),
              ],
            ],
          );
        },
      ),
    );
  }
}
