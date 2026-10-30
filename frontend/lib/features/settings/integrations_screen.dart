import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'settings_repository.dart';

/// Integration marketplace (spec §12): every connectable service grouped by
/// category with its real honest status. "Connected" reflects a genuine credential
/// or backend, never a fabricated state; credentials are operator-configured (env),
/// so this view is read-only and shows which variable connects each gated service.
class IntegrationsScreen extends ConsumerWidget {
  const IntegrationsScreen({super.key});

  ({String label, Color color}) _badge(BuildContext context, String status) {
    final scheme = Theme.of(context).colorScheme;
    switch (status) {
      case 'connected':
        return (label: 'Connected', color: const Color(0xFF4AD295));
      case 'available':
        return (label: 'Available', color: const Color(0xFF4AD295));
      case 'connect':
        return (label: 'Connect', color: Colors.orange);
      default:
        return (label: 'Coming', color: scheme.onSurfaceVariant);
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final market = ref.watch(marketplaceProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Integrations')),
      body: market.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(e.toString())),
        data: (m) {
          final groups = ((m['groups'] as List?) ?? []).cast<dynamic>();
          return RefreshIndicator(
            onRefresh: () async => ref.refresh(marketplaceProvider.future),
            child: ListView(
              padding: const EdgeInsets.all(16),
              children: [
                Text(
                  '${m['connected'] ?? 0} connected · ${m['usable'] ?? 0} of '
                  '${m['total'] ?? 0} usable. A service shows as connected only once '
                  'its credentials are genuinely configured.',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
                const SizedBox(height: 8),
                for (final g in groups) ...[
                  const SizedBox(height: 8),
                  Text('${(g as Map)['category']}'.toUpperCase(),
                      style: Theme.of(context)
                          .textTheme
                          .labelSmall
                          ?.copyWith(letterSpacing: 1, fontWeight: FontWeight.bold)),
                  for (final it in ((g['items'] as List?) ?? []).cast<dynamic>())
                    _item(context, (it as Map).cast<String, dynamic>()),
                ],
                const SizedBox(height: 16),
                Text(
                  'Credentials are set via the environment by your operator; a service '
                  'becomes connected automatically once its credential is present.',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ],
            ),
          );
        },
      ),
    );
  }

  Widget _item(BuildContext context, Map<String, dynamic> it) {
    final badge = _badge(context, '${it['status']}');
    final env = ((it['credential_env'] as List?) ?? []).cast<dynamic>();
    final showEnv = it['status'] == 'connect' && env.isNotEmpty;
    return ListTile(
      contentPadding: EdgeInsets.zero,
      title: Text('${it['name']}'),
      subtitle: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('${it['description']}'),
          if (showEnv)
            Text('Set ${env.join(', ')} to connect.',
                style: Theme.of(context).textTheme.bodySmall),
        ],
      ),
      isThreeLine: showEnv,
      trailing: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
        decoration: BoxDecoration(
          color: badge.color.withOpacity(.16),
          borderRadius: BorderRadius.circular(99),
        ),
        child: Text(badge.label,
            style: TextStyle(color: badge.color, fontSize: 12, fontWeight: FontWeight.w600)),
      ),
    );
  }
}
