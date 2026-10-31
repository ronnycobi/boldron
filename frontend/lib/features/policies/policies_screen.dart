import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../config/brand.dart';
import '../../core/api_exception.dart';
import 'policies_repository.dart';

/// Governance policies (spec §44): guardrails on platform actions, with the
/// platform's own built-in guardrails shown read-only. A block policy really
/// stops a deploy — the switch toggles whether it's enforced.
class PoliciesScreen extends ConsumerWidget {
  final int projectId;
  const PoliciesScreen({super.key, required this.projectId});

  static Color _effectColor(String e) => switch (e) {
        'block' => Colors.red,
        'require_approval' => const Color(0xFFC99A00),
        _ => Colors.grey,
      };

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final data = ref.watch(policiesProvider(projectId));
    return Scaffold(
      appBar: AppBar(title: const Text('Governance policies')),
      body: data.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(e.toString())),
        data: (d) {
          final summary =
              (d['summary'] as Map?)?.cast<String, dynamic>() ?? {};
          final policies =
              ((d['policies'] as List?) ?? []).cast<Map<String, dynamic>>();
          final builtIn =
              ((d['built_in'] as List?) ?? []).cast<Map<String, dynamic>>();
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              PanelCard(
                child: Row(
                  children: [
                    Text('${summary['enabled'] ?? 0}',
                        style: Theme.of(context).textTheme.headlineSmall),
                    const SizedBox(width: 6),
                    const Text('active'),
                    const Spacer(),
                    if ((summary['blocking'] ?? 0) as int > 0)
                      Chip(
                        label: Text('${summary['blocking']} blocking'),
                        visualDensity: VisualDensity.compact,
                      ),
                  ],
                ),
              ),
              const SizedBox(height: 14),
              if (policies.isEmpty)
                const PanelCard(
                    child: Text('No custom policies yet. Create one from the web '
                        'to guard deploys.')),
              for (final p in policies)
                _PolicyCard(
                  policy: p,
                  onToggle: (v) =>
                      _toggle(context, ref, p['id'] as int, v),
                ),
              const SizedBox(height: 8),
              Text('Built-in guardrails · always on',
                  style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 8),
              for (final g in builtIn) _BuiltInCard(guardrail: g),
            ],
          );
        },
      ),
    );
  }

  Future<void> _toggle(
      BuildContext context, WidgetRef ref, int id, bool enabled) async {
    try {
      await ref.read(policiesRepositoryProvider).toggle(id, enabled);
      ref.invalidate(policiesProvider(projectId));
    } on ApiException catch (e) {
      ref.invalidate(policiesProvider(projectId));
      if (context.mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }
}

class _PolicyCard extends StatelessWidget {
  final Map<String, dynamic> policy;
  final ValueChanged<bool> onToggle;
  const _PolicyCard({required this.policy, required this.onToggle});

  @override
  Widget build(BuildContext context) {
    final effect = '${policy['effect']}';
    final message = (policy['message'] as String?)?.trim() ?? '';
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: PanelCard(
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('${policy['name']}',
                      style: Theme.of(context).textTheme.titleMedium),
                  const SizedBox(height: 4),
                  Wrap(
                    spacing: 6,
                    children: [
                      Chip(
                        label: Text('${policy['effect_label']}'),
                        backgroundColor: PoliciesScreen._effectColor(effect)
                            .withOpacity(0.15),
                        visualDensity: VisualDensity.compact,
                      ),
                      Chip(
                        label: Text('on ${policy['scope']}'),
                        visualDensity: VisualDensity.compact,
                      ),
                    ],
                  ),
                  if (message.isNotEmpty)
                    Padding(
                      padding: const EdgeInsets.only(top: 4),
                      child: Text('“$message”',
                          style: Theme.of(context).textTheme.bodySmall),
                    ),
                ],
              ),
            ),
            Switch(
              value: (policy['enabled'] ?? false) as bool,
              onChanged: onToggle,
            ),
          ],
        ),
      ),
    );
  }
}

class _BuiltInCard extends StatelessWidget {
  final Map<String, dynamic> guardrail;
  const _BuiltInCard({required this.guardrail});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: PanelCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text('${guardrail['name']}',
                      style: Theme.of(context).textTheme.titleSmall),
                ),
                Chip(
                  label: Text('${guardrail['effect']}'),
                  visualDensity: VisualDensity.compact,
                ),
              ],
            ),
            const SizedBox(height: 4),
            Text('${guardrail['detail']}',
                style: Theme.of(context).textTheme.bodySmall),
          ],
        ),
      ),
    );
  }
}
