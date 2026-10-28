import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'settings_repository.dart';

/// Single sign-on status. Honest: a provider shows only when configured in the
/// deployment's environment — nothing is presented as linkable unless it is.
class ConnectedAccountsScreen extends ConsumerWidget {
  const ConnectedAccountsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final data = ref.watch(connectedAccountsProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Connected accounts')),
      body: data.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(e.toString())),
        data: (d) {
          final providers = ((d['providers'] as List?) ?? [])
              .map((p) => (p as Map).cast<String, dynamic>()).toList();
          final anyConfigured = (d['any_configured'] ?? false) as bool;
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              for (final p in providers)
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: Text('${p['name']}'),
                  trailing: Text(
                    (p['configured'] ?? false) as bool ? 'Available' : 'Not configured',
                    style: TextStyle(
                        color: (p['configured'] ?? false) as bool
                            ? const Color(0xFF4AD295)
                            : const Color(0xFFF5C454)),
                  ),
                ),
              if (!anyConfigured)
                Padding(
                  padding: const EdgeInsets.only(top: 12),
                  child: Text(
                    'No single sign-on provider is configured on this deployment, '
                    'so there is nothing to connect yet. You sign in with email and '
                    'password; two-factor is under Security.',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ),
            ],
          );
        },
      ),
    );
  }
}
