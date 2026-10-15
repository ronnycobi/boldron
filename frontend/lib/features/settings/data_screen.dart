import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_exception.dart';
import '../../core/providers.dart';
import 'settings_repository.dart';

/// Data export. Downloading a file is awkward on mobile, so here each export is
/// fetched and copied to the clipboard as JSON (the web app offers a file
/// download). Secrets are never included — the server masks them.
class DataScreen extends ConsumerWidget {
  const DataScreen({super.key});

  Future<void> _copy(BuildContext context, Future<Map<String, dynamic>> future,
      String what) async {
    try {
      final data = await future;
      await Clipboard.setData(
          ClipboardData(text: const JsonEncoder.withIndent('  ').convert(data)));
      if (context.mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('$what copied to clipboard.')));
      }
    } on ApiException catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final repo = ref.watch(settingsRepositoryProvider);
    final user = ref.watch(authControllerProvider).user;
    final manageOrgs =
        (user?.organizations ?? []).where((o) => o.canManage).toList();
    return Scaffold(
      appBar: AppBar(title: const Text('Your data')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text(
            'Copy a JSON copy of your data. Secrets are never included. '
            'The web app can download these as files.',
            style: Theme.of(context).textTheme.bodySmall,
          ),
          const SizedBox(height: 12),
          Card(
            child: ListTile(
              title: const Text('Account data'),
              subtitle: const Text('Your profile and organizations'),
              trailing: const Icon(Icons.copy),
              onTap: () => _copy(context, repo.accountExport(), 'Account data'),
            ),
          ),
          for (final o in manageOrgs)
            Card(
              child: ListTile(
                title: Text('${o.name} — organization data'),
                subtitle: const Text('Members, projects, API keys (masked)'),
                trailing: const Icon(Icons.copy),
                onTap: () =>
                    _copy(context, repo.orgExport(o.id), '${o.name} data'),
              ),
            ),
        ],
      ),
    );
  }
}
