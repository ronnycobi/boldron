import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_exception.dart';
import 'team_repository.dart';

/// Members, roles and invitations for an organization (spec §5/§29). Backend
/// authorization is authoritative — the UI just reflects it.
class TeamScreen extends ConsumerWidget {
  final int orgId;
  const TeamScreen({super.key, required this.orgId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final members = ref.watch(membersProvider(orgId));
    final invitations = ref.watch(invitationsProvider(orgId));
    return Scaffold(
      appBar: AppBar(title: const Text('Team')),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => _invite(context, ref),
        icon: const Icon(Icons.person_add_alt),
        label: const Text('Invite'),
      ),
      body: RefreshIndicator(
        onRefresh: () async {
          ref.invalidate(membersProvider(orgId));
          ref.invalidate(invitationsProvider(orgId));
          await ref.read(membersProvider(orgId).future);
        },
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Text('Members', style: Theme.of(context).textTheme.titleMedium),
            members.when(
              loading: () => const Padding(
                padding: EdgeInsets.all(16),
                child: Center(child: CircularProgressIndicator()),
              ),
              error: (e, _) => Text(e.toString()),
              data: (items) => Column(
                children: [
                  for (final m in items)
                    ListTile(
                      leading: CircleAvatar(
                        child: Text(m.displayName.isNotEmpty
                            ? m.displayName[0].toUpperCase()
                            : '?'),
                      ),
                      title: Text(m.displayName),
                      subtitle: Text(m.email),
                      trailing: Chip(label: Text(m.role)),
                    ),
                ],
              ),
            ),
            const SizedBox(height: 16),
            invitations.when(
              loading: () => const SizedBox.shrink(),
              error: (_, __) => const SizedBox.shrink(),
              data: (items) {
                final pending = items.where((i) => i.isPending).toList();
                if (pending.isEmpty) return const SizedBox.shrink();
                return Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Pending invitations',
                        style: Theme.of(context).textTheme.titleMedium),
                    for (final i in pending)
                      ListTile(
                        leading: const Icon(Icons.mail_outline),
                        title: Text(i.email),
                        subtitle: Text(i.role),
                      ),
                  ],
                );
              },
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _invite(BuildContext context, WidgetRef ref) async {
    final email = TextEditingController();
    String role = 'member';
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Invite a teammate'),
        content: StatefulBuilder(
          builder: (ctx, setState) => Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: email,
                keyboardType: TextInputType.emailAddress,
                decoration: const InputDecoration(labelText: 'Email'),
              ),
              const SizedBox(height: 8),
              DropdownButtonFormField<String>(
                value: role,
                decoration: const InputDecoration(labelText: 'Role'),
                items: const [
                  DropdownMenuItem(value: 'member', child: Text('Member')),
                  DropdownMenuItem(value: 'admin', child: Text('Admin')),
                ],
                onChanged: (v) => setState(() => role = v ?? 'member'),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
          FilledButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Send invite')),
        ],
      ),
    );
    if (ok == true && email.text.trim().isNotEmpty) {
      try {
        await ref
            .read(teamRepositoryProvider)
            .invite(orgId, email.text.trim(), role: role);
        ref.invalidate(invitationsProvider(orgId));
      } on ApiException catch (e) {
        if (context.mounted) {
          ScaffoldMessenger.of(context)
              .showSnackBar(SnackBar(content: Text(e.message)));
        }
      }
    }
  }
}
