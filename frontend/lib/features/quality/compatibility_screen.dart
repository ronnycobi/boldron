import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'quality_repository.dart';

/// Compatibility (spec §9) on mobile: the honest static analysis — per-target risks
/// only (never a fabricated pass), with live cross-browser/device runs reported as
/// not connected.
class CompatibilityScreen extends ConsumerWidget {
  final int projectId;
  const CompatibilityScreen({super.key, required this.projectId});

  Widget _targetTile(BuildContext context, Map<String, dynamic> t) {
    final risks = ((t['risks'] as List?) ?? []).cast<dynamic>();
    final isRisk = t['status'] == 'risk';
    return ListTile(
      dense: true,
      contentPadding: EdgeInsets.zero,
      title: Text('${t['name']}'),
      trailing: isRisk
          ? Chip(
              label: Text('⚠ ${risks.length} risk${risks.length == 1 ? '' : 's'}'),
              visualDensity: VisualDensity.compact,
              backgroundColor: Theme.of(context).colorScheme.surfaceVariant,
            )
          : Text('— not verified',
              style: Theme.of(context).textTheme.bodySmall),
    );
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final compat = ref.watch(compatibilityProvider(projectId));
    return Scaffold(
      appBar: AppBar(title: const Text('Compatibility')),
      body: compat.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(e.toString())),
        data: (c) {
          final browsers = ((c['browsers'] as List?) ?? []).cast<dynamic>();
          final platforms = ((c['platforms'] as List?) ?? []).cast<dynamic>();
          final risks = ((c['risks'] as List?) ?? []).cast<dynamic>();
          final live = (c['live_testing'] as Map?)?.cast<String, dynamic>() ?? {};
          final analysed = (c['analysed'] ?? false) as bool;
          return RefreshIndicator(
            onRefresh: () async =>
                ref.refresh(compatibilityProvider(projectId).future),
            child: ListView(
              padding: const EdgeInsets.all(16),
              children: [
                Text('${c['note']}', style: Theme.of(context).textTheme.bodySmall),
                const SizedBox(height: 12),
                Card(
                  color: Theme.of(context).colorScheme.tertiaryContainer,
                  child: Padding(
                    padding: const EdgeInsets.all(14),
                    child: Row(
                      children: [
                        const Icon(Icons.cloud_off_outlined),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Text(
                            '${live['detail'] ?? 'Live cross-browser & device testing isn\'t connected.'}',
                            style: Theme.of(context).textTheme.bodySmall,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                if (analysed) ...[
                  const SizedBox(height: 16),
                  Text('Browsers', style: Theme.of(context).textTheme.titleSmall),
                  for (final b in browsers)
                    _targetTile(context, (b as Map).cast<String, dynamic>()),
                  const SizedBox(height: 12),
                  Text('Devices', style: Theme.of(context).textTheme.titleSmall),
                  for (final p in platforms)
                    _targetTile(context, (p as Map).cast<String, dynamic>()),
                  const Divider(height: 24),
                  Text('Compatibility risks',
                      style: Theme.of(context).textTheme.titleSmall),
                  if (risks.isEmpty)
                    Padding(
                      padding: const EdgeInsets.only(top: 8),
                      child: Text(
                          'No risks found in static analysis. That isn\'t a pass — '
                          'targets stay "not verified" until a live run.',
                          style: Theme.of(context).textTheme.bodySmall),
                    ),
                  for (final r in risks)
                    ListTile(
                      dense: true,
                      contentPadding: EdgeInsets.zero,
                      leading: const Icon(Icons.warning_amber_rounded),
                      title: Text('${(r as Map)['message']}'),
                      subtitle: Text(
                          'Affects: ${((r['targets'] as List?) ?? []).join(', ')} · ${r['path']}'),
                    ),
                ],
              ],
            ),
          );
        },
      ),
    );
  }
}
