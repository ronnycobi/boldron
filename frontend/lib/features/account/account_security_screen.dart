import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_exception.dart';
import '../../core/providers.dart';
import 'account_repository.dart';

/// Edit profile, change password, and sign out other sessions (spec §4).
class AccountSecurityScreen extends ConsumerStatefulWidget {
  const AccountSecurityScreen({super.key});

  @override
  ConsumerState<AccountSecurityScreen> createState() =>
      _AccountSecurityScreenState();
}

class _AccountSecurityScreenState
    extends ConsumerState<AccountSecurityScreen> {
  late final TextEditingController _name;
  late final TextEditingController _email;
  bool _savingProfile = false;

  @override
  void initState() {
    super.initState();
    final user = ref.read(authControllerProvider).user;
    _name = TextEditingController(text: user?.fullName ?? '');
    _email = TextEditingController(text: user?.email ?? '');
  }

  @override
  void dispose() {
    _name.dispose();
    _email.dispose();
    super.dispose();
  }

  Future<void> _saveProfile() async {
    setState(() => _savingProfile = true);
    try {
      final user = await ref.read(accountRepositoryProvider).updateProfile({
        'full_name': _name.text.trim(),
        'email': _email.text.trim(),
      });
      ref.read(authControllerProvider.notifier).setUser(user);
      _toast('Profile updated.');
    } on ApiException catch (e) {
      _toast(e.firstFieldError ?? e.message);
    } finally {
      if (mounted) setState(() => _savingProfile = false);
    }
  }

  Future<void> _changePassword() async {
    final result = await showDialog<_PasswordInput>(
      context: context,
      builder: (_) => const _PasswordDialog(),
    );
    if (result == null) return;
    try {
      final user = await ref.read(accountRepositoryProvider).changePassword(
            oldPassword: result.oldPassword,
            newPassword: result.newPassword,
          );
      ref.read(authControllerProvider.notifier).setUser(user);
      _toast('Password changed — other sessions were signed out.');
    } on ApiException catch (e) {
      _toast(e.firstFieldError ?? e.message);
    }
  }

  Future<void> _signOutOthers() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Sign out of other sessions?'),
        content: const Text('This device stays signed in.'),
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
    if (ok != true) return;
    try {
      final user = await ref.read(accountRepositoryProvider).logoutOtherSessions();
      ref.read(authControllerProvider.notifier).setUser(user);
      _toast('Signed out of other sessions.');
    } on ApiException catch (e) {
      _toast(e.message);
    }
  }

  void _toast(String message) {
    if (mounted) {
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(message)));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Account & security')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text('Profile', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          TextField(
            controller: _name,
            textCapitalization: TextCapitalization.words,
            decoration: const InputDecoration(labelText: 'Full name'),
          ),
          const SizedBox(height: 10),
          TextField(
            controller: _email,
            keyboardType: TextInputType.emailAddress,
            decoration: const InputDecoration(labelText: 'Email'),
          ),
          const SizedBox(height: 12),
          FilledButton(
            onPressed: _savingProfile ? null : _saveProfile,
            child: Text(_savingProfile ? 'Saving…' : 'Save profile'),
          ),
          const Divider(height: 36),
          Text('Security', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 4),
          ListTile(
            contentPadding: EdgeInsets.zero,
            leading: const Icon(Icons.password),
            title: const Text('Change password'),
            onTap: _changePassword,
          ),
          ListTile(
            contentPadding: EdgeInsets.zero,
            leading: const Icon(Icons.devices_outlined),
            title: const Text('Sign out of other sessions'),
            onTap: _signOutOthers,
          ),
        ],
      ),
    );
  }
}

class _PasswordInput {
  final String oldPassword;
  final String newPassword;
  const _PasswordInput(this.oldPassword, this.newPassword);
}

class _PasswordDialog extends StatefulWidget {
  const _PasswordDialog();

  @override
  State<_PasswordDialog> createState() => _PasswordDialogState();
}

class _PasswordDialogState extends State<_PasswordDialog> {
  final _old = TextEditingController();
  final _new = TextEditingController();
  String? _error;

  @override
  void dispose() {
    _old.dispose();
    _new.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Change password'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          TextField(
            controller: _old,
            obscureText: true,
            decoration: const InputDecoration(labelText: 'Current password'),
          ),
          TextField(
            controller: _new,
            obscureText: true,
            decoration: const InputDecoration(labelText: 'New password'),
          ),
          if (_error != null)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text(_error!,
                  style: TextStyle(color: Theme.of(context).colorScheme.error)),
            ),
        ],
      ),
      actions: [
        TextButton(
            onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
        FilledButton(
          onPressed: () {
            if (_new.text.length < 8) {
              setState(() => _error = 'New password needs at least 8 characters.');
              return;
            }
            Navigator.pop(context, _PasswordInput(_old.text, _new.text));
          },
          child: const Text('Update'),
        ),
      ],
    );
  }
}
