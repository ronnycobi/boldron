import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../config/app_config.dart';
import '../../core/providers.dart';

class AccountScreen extends ConsumerWidget {
  const AccountScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final user = ref.watch(authControllerProvider.select((s) => s.user));
    final orgId = user?.organizations.isNotEmpty == true
        ? user!.organizations.first.id
        : null;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Account'),
        actions: [
          IconButton(
            icon: const Icon(Icons.search),
            onPressed: () => context.push('/search'),
          ),
        ],
      ),
      body: user == null
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              children: [
                const SizedBox(height: 16),
                Center(
                  child: CircleAvatar(
                    radius: 36,
                    backgroundImage: user.avatarUrl.isNotEmpty
                        ? NetworkImage(user.avatarUrl)
                        : null,
                    child: user.avatarUrl.isEmpty
                        ? Text(user.initials,
                            style: const TextStyle(fontSize: 24))
                        : null,
                  ),
                ),
                const SizedBox(height: 12),
                Center(
                  child: Text(user.displayName,
                      style: Theme.of(context).textTheme.titleLarge),
                ),
                Center(child: Text(user.email)),
                if (!user.emailVerified)
                  Center(
                    child: Padding(
                      padding: const EdgeInsets.only(top: 6),
                      child: Chip(
                        label: const Text('Email not verified'),
                        backgroundColor:
                            Theme.of(context).colorScheme.tertiaryContainer,
                      ),
                    ),
                  ),
                const SizedBox(height: 20),
                const _SectionHeader('Organizations'),
                for (final org in user.organizations)
                  ListTile(
                    leading: const Icon(Icons.business_outlined),
                    title: Text(org.name),
                    subtitle: Text(org.role),
                  ),
                const Divider(),
                const _SectionHeader('Manage'),
                if (orgId != null)
                  ListTile(
                    leading: const Icon(Icons.credit_card),
                    title: const Text('Billing & usage'),
                    onTap: () => context.push('/orgs/$orgId/billing'),
                  ),
                if (orgId != null)
                  ListTile(
                    leading: const Icon(Icons.group_outlined),
                    title: const Text('Team'),
                    onTap: () => context.push('/orgs/$orgId/team'),
                  ),
                ListTile(
                  leading: const Icon(Icons.help_outline),
                  title: const Text('Help & support'),
                  onTap: () => context.push('/support'),
                ),
                ListTile(
                  leading: const Icon(Icons.settings_outlined),
                  title: const Text('Settings'),
                  onTap: () => context.push('/settings'),
                ),
                const Divider(),
                ListTile(
                  leading: Icon(Icons.logout,
                      color: Theme.of(context).colorScheme.error),
                  title: Text('Sign out',
                      style: TextStyle(
                          color: Theme.of(context).colorScheme.error)),
                  onTap: () => _confirmLogout(context, ref),
                ),
                const SizedBox(height: 24),
                Center(
                  child: Text(
                    '${AppConfig.appName} · v1.0.0',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ),
                const SizedBox(height: 24),
              ],
            ),
    );
  }

  Future<void> _confirmLogout(BuildContext context, WidgetRef ref) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Sign out?'),
        content: const Text('You can sign back in any time.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Cancel')),
          FilledButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Sign out')),
        ],
      ),
    );
    if (ok == true) {
      await ref.read(authControllerProvider.notifier).logout();
    }
  }
}

class _SectionHeader extends StatelessWidget {
  final String title;
  const _SectionHeader(this.title);

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
        child: Text(
          title.toUpperCase(),
          style: Theme.of(context).textTheme.labelSmall?.copyWith(
                letterSpacing: 1,
                color: Theme.of(context).colorScheme.primary,
              ),
        ),
      );
}
