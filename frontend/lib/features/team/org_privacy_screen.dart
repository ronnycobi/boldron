import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_exception.dart';
import '../settings/data_screen.dart';
import 'team_repository.dart';

/// Privacy & data: what is stored, a copy via the data export, and a genuine
/// deletion request (filed as a support ticket — never an instant wipe).
class OrgPrivacyScreen extends ConsumerWidget {
  final int orgId;
  final String orgName;
  const OrgPrivacyScreen({super.key, required this.orgId, this.orgName = ''});

  Future<void> _requestDeletion(BuildContext context, WidgetRef ref) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Request data deletion?'),
        content: Text('This files a request for ${orgName.isEmpty ? 'this organization' : orgName}. '
            'Our team confirms before anything is removed — nothing is deleted instantly.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Request')),
        ],
      ),
    );
    if (ok != true) return;
    try {
      final ticket = await ref.read(teamRepositoryProvider).requestDeletion(orgId);
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('Deletion request submitted ($ticket).')));
      }
    } on ApiException catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Scaffold(
      appBar: AppBar(title: const Text('Privacy & data')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text('What we store',
              style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 6),
          Text(
            'Your account profile, organizations and projects, build and '
            'deployment history, and audit events. Secrets are never stored in '
            'readable form.',
            style: Theme.of(context).textTheme.bodyMedium,
          ),
          const SizedBox(height: 20),
          Text('Get a copy', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 6),
          OutlinedButton.icon(
            icon: const Icon(Icons.download),
            label: const Text('Data export'),
            onPressed: () => Navigator.of(context).push(
                MaterialPageRoute(builder: (_) => const DataScreen())),
          ),
          const SizedBox(height: 20),
          Text('Request deletion', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 6),
          Text(
            'Deletion is handled by our team so it can be confirmed first.',
            style: Theme.of(context).textTheme.bodySmall,
          ),
          const SizedBox(height: 8),
          FilledButton.tonal(
            onPressed: () => _requestDeletion(context, ref),
            child: const Text('Request data deletion'),
          ),
        ],
      ),
    );
  }
}
