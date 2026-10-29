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
              const Divider(height: 32),
              const _SmsStatusSection(),
            ],
          );
        },
      ),
    );
  }
}

/// Honest SMS channel readiness. There is no offline path for SMS, so with no
/// gateway connected this reports "not connected" plainly — it never implies SMS
/// is enabled when it isn't.
class _SmsStatusSection extends ConsumerWidget {
  const _SmsStatusSection();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final sms = ref.watch(smsStatusProvider);
    return sms.when(
      loading: () => const LinearProgressIndicator(),
      error: (e, _) => const SizedBox.shrink(),
      data: (s) {
        final configured = (s['configured'] ?? false) as bool;
        final providers = ((s['providers'] as List?) ?? [])
            .map((p) => (p as Map).cast<String, dynamic>())
            .toList();
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Text('SMS', style: Theme.of(context).textTheme.titleMedium),
                const SizedBox(width: 8),
                Chip(
                  label: Text(configured ? 'Connected' : 'Not connected'),
                  visualDensity: VisualDensity.compact,
                  backgroundColor: configured
                      ? Theme.of(context).colorScheme.tertiaryContainer
                      : Theme.of(context).colorScheme.surfaceVariant,
                ),
              ],
            ),
            Text(
              configured
                  ? 'An SMS gateway is connected.'
                  : 'No SMS gateway is connected. Connect a provider in the '
                      'environment to enable SMS — nothing is sent until then.',
              style: Theme.of(context).textTheme.bodySmall,
            ),
            const SizedBox(height: 4),
            for (final p in providers)
              ListTile(
                dense: true,
                contentPadding: EdgeInsets.zero,
                leading: Icon(
                  (p['available'] ?? false) == true
                      ? Icons.check_circle_outline
                      : Icons.radio_button_unchecked,
                  size: 20,
                ),
                title: Text('${p['name']}'),
                subtitle: Text('${p['detail'] ?? ''}'),
              ),
          ],
        );
      },
    );
  }
}
