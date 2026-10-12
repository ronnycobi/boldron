import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart';

import '../../config/app_config.dart';
import '../../core/api_exception.dart';
import '../../core/providers.dart';
import 'account_repository.dart';

/// Builds an absolute image URL from the (possibly relative) avatar path the
/// API returns, using the API host origin.
String? _avatarUrl(String raw) {
  if (raw.isEmpty) return null;
  if (raw.startsWith('http')) return raw;
  final origin = Uri.parse(AppConfig.apiBaseUrl).replace(path: '', query: '');
  return '$origin$raw';
}

class AccountScreen extends ConsumerWidget {
  const AccountScreen({super.key});

  Future<void> _changeAvatar(BuildContext context, WidgetRef ref) async {
    final hasAvatar =
        ref.read(authControllerProvider).user?.avatarUrl.isNotEmpty ?? false;
    final choice = await showModalBottomSheet<String>(
      context: context,
      builder: (ctx) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              leading: const Icon(Icons.photo_camera_outlined),
              title: const Text('Take photo'),
              onTap: () => Navigator.pop(ctx, 'camera'),
            ),
            ListTile(
              leading: const Icon(Icons.photo_library_outlined),
              title: const Text('Choose from gallery'),
              onTap: () => Navigator.pop(ctx, 'gallery'),
            ),
            if (hasAvatar)
              ListTile(
                leading: const Icon(Icons.delete_outline),
                title: const Text('Remove photo'),
                onTap: () => Navigator.pop(ctx, 'remove'),
              ),
          ],
        ),
      ),
    );
    if (choice == null) return;
    final repo = ref.read(accountRepositoryProvider);
    try {
      if (choice == 'remove') {
        ref.read(authControllerProvider.notifier).setUser(await repo.removeAvatar());
        return;
      }
      final picked = await ImagePicker().pickImage(
        source: choice == 'camera' ? ImageSource.camera : ImageSource.gallery,
        maxWidth: 1024,
        imageQuality: 85,
      );
      if (picked == null) return;
      final user = await repo.uploadAvatar(picked.path);
      ref.read(authControllerProvider.notifier).setUser(user);
    } on ApiException catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final user = ref.watch(authControllerProvider.select((s) => s.user));
    final orgId = ref.watch(activeOrgProvider);
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
                  child: GestureDetector(
                    onTap: () => _changeAvatar(context, ref),
                    child: Stack(
                      children: [
                        CircleAvatar(
                          radius: 36,
                          backgroundImage: _avatarUrl(user.avatarUrl) != null
                              ? NetworkImage(_avatarUrl(user.avatarUrl)!)
                              : null,
                          child: _avatarUrl(user.avatarUrl) == null
                              ? Text(user.initials,
                                  style: const TextStyle(fontSize: 24))
                              : null,
                        ),
                        Positioned(
                          right: 0,
                          bottom: 0,
                          child: CircleAvatar(
                            radius: 12,
                            backgroundColor:
                                Theme.of(context).colorScheme.primary,
                            child: Icon(Icons.edit,
                                size: 14,
                                color:
                                    Theme.of(context).colorScheme.onPrimary),
                          ),
                        ),
                      ],
                    ),
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
                  RadioListTile<int>(
                    value: org.id,
                    groupValue: orgId,
                    onChanged: user.organizations.length > 1
                        ? (v) {
                            if (v != null) setActiveOrg(ref, v);
                          }
                        : null,
                    secondary: const Icon(Icons.business_outlined),
                    title: Text(org.name),
                    subtitle: Text(org.role),
                  ),
                const Divider(),
                const _SectionHeader('Manage'),
                ListTile(
                  leading: const Icon(Icons.manage_accounts_outlined),
                  title: const Text('Account & security'),
                  onTap: () => context.push('/account/security'),
                ),
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
