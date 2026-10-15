import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_exception.dart';
import 'developer_repository.dart';
import 'team_repository.dart';

/// Developer settings: programmatic API keys + outbound webhooks. Secrets (a
/// key's plaintext, a webhook's signing secret) are shown exactly once, in a
/// dialog, right after creation. Managing requires org rights (org.manage).
class DeveloperScreen extends ConsumerWidget {
  final int orgId;
  const DeveloperScreen({super.key, required this.orgId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final org = ref.watch(organizationProvider(orgId));
    return Scaffold(
      appBar: AppBar(title: const Text('Developer & API')),
      body: org.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(e.toString())),
        data: (o) {
          final canManage =
              ((o['my_permissions'] as List?) ?? []).contains('org.manage');
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              _ApiKeys(orgId: orgId, canManage: canManage),
              const SizedBox(height: 24),
              _Webhooks(orgId: orgId, canManage: canManage),
            ],
          );
        },
      ),
    );
  }
}

Future<void> _showOnce(BuildContext context, String title, String value) {
  return showDialog<void>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: Text(title),
      content: SelectableText(value,
          style: const TextStyle(fontFamily: 'monospace', fontSize: 13)),
      actions: [
        TextButton(
          onPressed: () {
            Clipboard.setData(ClipboardData(text: value));
            Navigator.pop(ctx);
          },
          child: const Text('Copy & close'),
        ),
      ],
    ),
  );
}

class _ApiKeys extends ConsumerWidget {
  final int orgId;
  final bool canManage;
  const _ApiKeys({required this.orgId, required this.canManage});

  Future<void> _create(BuildContext context, WidgetRef ref) async {
    final name = await _askText(context, 'New API key', 'Key name', 'CI pipeline');
    if (name == null || name.trim().isEmpty) return;
    try {
      final created = await ref
          .read(developerRepositoryProvider)
          .createApiKey(orgId, name.trim());
      ref.invalidate(apiKeysProvider(orgId));
      if (!context.mounted) return;
      await _showOnce(context, 'API key — copy it now',
          '${created['key']}\n\nThis is the only time it is shown.');
    } on ApiException catch (e) {
      if (!context.mounted) return;
      _toast(context, e.firstFieldError ?? e.message);
    }
  }

  Future<void> _revoke(BuildContext context, WidgetRef ref, int id) async {
    try {
      await ref.read(developerRepositoryProvider).revokeApiKey(orgId, id);
      ref.invalidate(apiKeysProvider(orgId));
    } on ApiException catch (e) {
      if (!context.mounted) return;
      _toast(context, e.message);
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final keys = ref.watch(apiKeysProvider(orgId));
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(
              child: Text('API keys',
                  style: Theme.of(context).textTheme.titleMedium),
            ),
            if (canManage)
              TextButton.icon(
                onPressed: () => _create(context, ref),
                icon: const Icon(Icons.add, size: 18),
                label: const Text('New'),
              ),
          ],
        ),
        Text('Authenticate the API with  Authorization: Api-Key <key>',
            style: Theme.of(context).textTheme.bodySmall),
        const SizedBox(height: 8),
        keys.when(
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (e, _) => Text(e.toString()),
          data: (list) => list.isEmpty
              ? const Text('No API keys yet.')
              : Column(
                  children: [
                    for (final k in list)
                      ListTile(
                        contentPadding: EdgeInsets.zero,
                        title: Text('${k['masked']}  ·  ${k['name']}'),
                        subtitle: Text((k['is_active'] ?? false) as bool
                            ? 'Active'
                            : 'Revoked'),
                        trailing: (canManage && (k['is_active'] ?? false) as bool)
                            ? TextButton(
                                onPressed: () =>
                                    _revoke(context, ref, k['id'] as int),
                                child: const Text('Revoke'),
                              )
                            : null,
                      ),
                  ],
                ),
        ),
      ],
    );
  }
}

class _Webhooks extends ConsumerWidget {
  final int orgId;
  final bool canManage;
  const _Webhooks({required this.orgId, required this.canManage});

  Future<void> _create(BuildContext context, WidgetRef ref,
      List<Map<String, dynamic>> available) async {
    final url = await _askText(
        context, 'New webhook', 'Endpoint URL', 'https://example.com/hook');
    if (url == null || !url.startsWith('https://')) {
      if (url != null && context.mounted) {
        _toast(context, 'An https:// URL is required.');
      }
      return;
    }
    final events = available.map((e) => '${e['key']}').toList();
    try {
      final created = await ref
          .read(developerRepositoryProvider)
          .createWebhook(orgId, url.trim(), events);
      ref.invalidate(webhooksProvider(orgId));
      if (!context.mounted) return;
      await _showOnce(context, 'Webhook signing secret',
          '${created['secret']}\n\nThis is the only time it is shown.');
    } on ApiException catch (e) {
      if (!context.mounted) return;
      _toast(context, e.firstFieldError ?? e.message);
    }
  }

  Future<void> _delete(BuildContext context, WidgetRef ref, int id) async {
    try {
      await ref.read(developerRepositoryProvider).deleteWebhook(orgId, id);
      ref.invalidate(webhooksProvider(orgId));
    } on ApiException catch (e) {
      if (!context.mounted) return;
      _toast(context, e.message);
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final data = ref.watch(webhooksProvider(orgId));
    return data.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Text(e.toString()),
      data: (d) {
        final hooks = ((d['webhooks'] as List?) ?? [])
            .map((w) => (w as Map).cast<String, dynamic>())
            .toList();
        final available = ((d['available_events'] as List?) ?? [])
            .map((e) => (e as Map).cast<String, dynamic>())
            .toList();
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text('Webhooks',
                      style: Theme.of(context).textTheme.titleMedium),
                ),
                if (canManage)
                  TextButton.icon(
                    onPressed: () => _create(context, ref, available),
                    icon: const Icon(Icons.add, size: 18),
                    label: const Text('New'),
                  ),
              ],
            ),
            Text('Signed JSON POSTs on subscribed events.',
                style: Theme.of(context).textTheme.bodySmall),
            const SizedBox(height: 8),
            if (hooks.isEmpty)
              const Text('No webhooks yet.')
            else
              for (final w in hooks)
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: Text('${w['url']}'),
                  subtitle: Text(((w['events'] as List?) ?? []).isEmpty
                      ? 'all events'
                      : ((w['events'] as List).join(', '))),
                  trailing: canManage
                      ? IconButton(
                          icon: const Icon(Icons.delete_outline),
                          onPressed: () => _delete(context, ref, w['id'] as int),
                        )
                      : null,
                ),
          ],
        );
      },
    );
  }
}

Future<String?> _askText(
    BuildContext context, String title, String label, String hint) {
  final controller = TextEditingController();
  return showDialog<String>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: Text(title),
      content: TextField(
        controller: controller,
        autofocus: true,
        decoration: InputDecoration(labelText: label, hintText: hint),
      ),
      actions: [
        TextButton(
            onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
        FilledButton(
            onPressed: () => Navigator.pop(ctx, controller.text),
            child: const Text('Create')),
      ],
    ),
  );
}

void _toast(BuildContext context, String message) {
  if (context.mounted) {
    ScaffoldMessenger.of(context)
        .showSnackBar(SnackBar(content: Text(message)));
  }
}
