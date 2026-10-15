import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_exception.dart';
import 'settings_repository.dart';

/// Per-user notification preferences (opt-out). Only categories wired to a real
/// optional email are shown; essential mail is always sent and not listed.
class NotificationsScreen extends ConsumerWidget {
  const NotificationsScreen({super.key});

  Future<void> _toggle(
      BuildContext context, WidgetRef ref, String key, bool value) async {
    try {
      await ref
          .read(settingsRepositoryProvider)
          .updateNotificationPrefs({key: value});
      ref.invalidate(notificationPrefsProvider);
    } on ApiException catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final data = ref.watch(notificationPrefsProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Notifications')),
      body: data.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(e.toString())),
        data: (d) {
          final categories = ((d['categories'] as List?) ?? [])
              .map((c) => (c as Map).cast<String, dynamic>())
              .toList();
          final prefs = (d['preferences'] as Map?) ?? {};
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Text(
                'Choose which optional emails you receive. Security and '
                'account-critical emails are always sent.',
                style: Theme.of(context).textTheme.bodySmall,
              ),
              const SizedBox(height: 8),
              for (final c in categories)
                SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  title: Text('${c['label']}'),
                  subtitle: Text('${c['description']}'),
                  value: (prefs['${c['key']}'] ?? true) as bool,
                  onChanged: (v) => _toggle(context, ref, '${c['key']}', v),
                ),
            ],
          );
        },
      ),
    );
  }
}
