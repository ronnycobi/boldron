import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'settings_repository.dart';

/// Integrations: the connectors the platform supports and whether each is
/// configured. Honest — "connected" reflects a real credential on the
/// deployment, never a fabricated state. Credentials are operator-configured
/// (environment), so this view is read-only.
class IntegrationsScreen extends ConsumerWidget {
  const IntegrationsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final integrations = ref.watch(integrationsProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Integrations')),
      body: integrations.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(e.toString())),
        data: (items) => ListView(
          padding: const EdgeInsets.all(16),
          children: [
            for (final it in items)
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: Icon(
                  (it['configured'] ?? false) as bool
                      ? Icons.check_circle
                      : Icons.circle_outlined,
                  color: (it['configured'] ?? false) as bool
                      ? const Color(0xFF4AD295)
                      : null,
                ),
                title: Text('${it['provider']}'),
                subtitle: Text((it['configured'] ?? false) as bool
                    ? 'Connected'
                    : 'Not connected'),
              ),
            const SizedBox(height: 12),
            Text(
              'Connector credentials are configured by your operator via the '
              'environment. Once set, a connector shows as connected here.',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ],
        ),
      ),
    );
  }
}
