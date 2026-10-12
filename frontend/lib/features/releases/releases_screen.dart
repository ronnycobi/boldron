import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/api_exception.dart';
import 'releases_repository.dart';

const _storeProviders = {
  'google_play': 'Google Play',
  'apple_app_store': 'Apple App Store',
  'huawei_appgallery': 'Huawei AppGallery',
};

/// Mobile Release Center (spec §18): the project's mobile apps and their
/// per-store readiness. Live store submission stays gated on the backend until
/// the customer connects real store credentials — nothing here fakes it.
class ReleasesScreen extends ConsumerWidget {
  final int projectId;
  const ReleasesScreen({super.key, required this.projectId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final apps = ref.watch(mobileAppsProvider(projectId));
    return Scaffold(
      appBar: AppBar(title: const Text('Mobile releases')),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => _create(context, ref),
        icon: const Icon(Icons.add),
        label: const Text('New app'),
      ),
      body: apps.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(e.toString())),
        data: (items) => items.isEmpty
            ? const Center(child: Text('No mobile apps yet.'))
            : ListView(
                padding: const EdgeInsets.all(16),
                children: [for (final a in items) _AppCard(app: a)],
              ),
      ),
    );
  }

  Future<void> _create(BuildContext context, WidgetRef ref) async {
    final name = TextEditingController();
    final pkg = TextEditingController();
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('New mobile app'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
                controller: name,
                decoration: const InputDecoration(labelText: 'App name')),
            TextField(
                controller: pkg,
                decoration: const InputDecoration(
                    labelText: 'Package id (com.example.app)')),
          ],
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
          FilledButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Create')),
        ],
      ),
    );
    if (ok == true && name.text.trim().isNotEmpty) {
      try {
        await ref.read(releasesRepositoryProvider).create(
              projectId,
              name.text.trim(),
              packageId: pkg.text.trim(),
            );
        ref.invalidate(mobileAppsProvider(projectId));
      } on ApiException catch (e) {
        if (context.mounted) {
          ScaffoldMessenger.of(context)
              .showSnackBar(SnackBar(content: Text(e.message)));
        }
      }
    }
  }
}

class _AppCard extends StatelessWidget {
  final MobileApp app;
  const _AppCard({required this.app});

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(app.name, style: Theme.of(context).textTheme.titleMedium),
            Text('v${app.version} (${app.buildNumber})'
                '${app.packageId.isNotEmpty ? ' · ${app.packageId}' : ''}'),
            const SizedBox(height: 10),
            for (final s in app.storeApps)
              ListTile(
                dense: true,
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.store_outlined),
                title: Text('${s['provider_label'] ?? s['provider']}'),
                subtitle: Text(
                    'metadata ${s['metadata_status']} · review ${s['review_status']}'),
              ),
            const SizedBox(height: 4),
            const Text('Prepare a store listing',
                style: TextStyle(fontSize: 12.5)),
            const SizedBox(height: 6),
            Wrap(
              spacing: 8,
              children: [
                for (final entry in _storeProviders.entries)
                  OutlinedButton(
                    onPressed: () => context.push(
                      '/mobile-apps/${app.id}/stores/${entry.key}/listing',
                    ),
                    child: Text(entry.value),
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
