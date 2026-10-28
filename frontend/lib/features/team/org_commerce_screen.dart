import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'team_repository.dart';

/// Rollup of the org's stores (real product + order counts per project).
class OrgCommerceScreen extends ConsumerWidget {
  final int orgId;
  const OrgCommerceScreen({super.key, required this.orgId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final commerce = ref.watch(orgCommerceProvider(orgId));
    return Scaffold(
      appBar: AppBar(title: const Text('Commerce')),
      body: commerce.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(e.toString())),
        data: (stores) => stores.isEmpty
            ? const Center(
                child: Padding(
                  padding: EdgeInsets.all(24),
                  child: Text(
                    'No stores yet. Build a project with a store and it appears here.',
                    textAlign: TextAlign.center,
                  ),
                ),
              )
            : ListView(
                padding: const EdgeInsets.all(16),
                children: [
                  for (final s in stores)
                    ListTile(
                      contentPadding: EdgeInsets.zero,
                      leading: const Icon(Icons.storefront_outlined),
                      title: Text('${s['project']}'),
                      subtitle: Text(
                          '${s['products']} products · ${s['orders']} orders'),
                    ),
                ],
              ),
      ),
    );
  }
}
