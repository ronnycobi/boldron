import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../config/brand.dart';
import '../../core/api_exception.dart';
import 'flags_repository.dart';

/// Feature flags (spec §19): turn parts of the app on/off, with a switch that
/// toggles the real flag state. Rollout % and targeting are shown honestly.
class FlagsScreen extends ConsumerWidget {
  final int projectId;
  const FlagsScreen({super.key, required this.projectId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final data = ref.watch(flagsProvider(projectId));
    return Scaffold(
      appBar: AppBar(title: const Text('Feature flags')),
      body: data.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(e.toString())),
        data: (d) {
          final summary =
              (d['summary'] as Map?)?.cast<String, dynamic>() ?? {};
          final flags =
              ((d['flags'] as List?) ?? []).cast<Map<String, dynamic>>();
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              PanelCard(
                child: Row(
                  children: [
                    Text('${summary['on'] ?? 0}',
                        style: Theme.of(context).textTheme.headlineSmall),
                    const SizedBox(width: 6),
                    const Text('on'),
                    const Spacer(),
                    Text('${summary['total'] ?? 0} total',
                        style: Theme.of(context).textTheme.bodySmall),
                  ],
                ),
              ),
              const SizedBox(height: 14),
              if (flags.isEmpty)
                const PanelCard(
                    child: Text('No feature flags yet. Create one from the web '
                        'to gate features on or off.')),
              for (final f in flags)
                _FlagTile(
                  flag: f,
                  onToggle: (v) =>
                      _toggle(context, ref, f['id'] as int, v),
                ),
            ],
          );
        },
      ),
    );
  }

  Future<void> _toggle(
      BuildContext context, WidgetRef ref, int id, bool enabled) async {
    try {
      await ref.read(flagsRepositoryProvider).toggle(id, enabled);
      ref.invalidate(flagsProvider(projectId));
    } on ApiException catch (e) {
      ref.invalidate(flagsProvider(projectId));
      if (context.mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }
}

class _FlagTile extends StatelessWidget {
  final Map<String, dynamic> flag;
  final ValueChanged<bool> onToggle;
  const _FlagTile({required this.flag, required this.onToggle});

  @override
  Widget build(BuildContext context) {
    final rollout = (flag['rollout'] ?? 100) as int;
    final targeted = (flag['targeted'] ?? false) as bool;
    final name = (flag['name'] as String?)?.trim() ?? '';
    final parts = <String>[];
    if (rollout < 100) parts.add('$rollout% rollout');
    if (targeted && rollout >= 100) parts.add('targeted');
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: PanelCard(
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('${flag['key']}',
                      style: const TextStyle(
                          fontFamily: 'monospace', fontWeight: FontWeight.w600)),
                  if (name.isNotEmpty)
                    Text(name, style: Theme.of(context).textTheme.bodyMedium),
                  if (parts.isNotEmpty)
                    Text(parts.join(' · '),
                        style: Theme.of(context).textTheme.bodySmall),
                ],
              ),
            ),
            Switch(
              value: (flag['enabled'] ?? false) as bool,
              onChanged: onToggle,
            ),
          ],
        ),
      ),
    );
  }
}
