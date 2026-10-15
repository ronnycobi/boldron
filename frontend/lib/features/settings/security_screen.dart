import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../config/brand.dart';
import '../../core/api_exception.dart';
import 'settings_repository.dart';

/// Account Security Center (spec §9/§12/§13): password + MFA status, the active
/// sessions signed in to the account (with revoke), and recent login history.
/// Read-only status straight from `/settings/security/`; no secrets are shown.
class SecurityScreen extends ConsumerWidget {
  const SecurityScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final security = ref.watch(securityProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Security')),
      body: security.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(e.toString())),
        data: (s) {
          final status = (s['status'] as Map?) ?? {};
          final sessions = (s['sessions'] as List?) ?? [];
          final history = (s['history'] as List?) ?? [];
          return RefreshIndicator(
            onRefresh: () async => ref.refresh(securityProvider.future),
            child: ListView(
              padding: const EdgeInsets.all(16),
              children: [
                _StatusCard(status),
                const SizedBox(height: 18),
                Text('Active sessions',
                    style: Theme.of(context).textTheme.titleMedium),
                const SizedBox(height: 2),
                Text('Devices signed in to your account.',
                    style: Theme.of(context).textTheme.bodySmall),
                const SizedBox(height: 8),
                if (sessions.isEmpty)
                  const Padding(
                    padding: EdgeInsets.symmetric(vertical: 8),
                    child: Text('No other active sessions.'),
                  )
                else
                  for (final session in sessions)
                    _SessionTile(session as Map, ref),
                const SizedBox(height: 24),
                Text('Recent activity',
                    style: Theme.of(context).textTheme.titleMedium),
                const SizedBox(height: 8),
                if (history.isEmpty)
                  const Padding(
                    padding: EdgeInsets.symmetric(vertical: 8),
                    child: Text('No activity recorded yet.'),
                  )
                else
                  for (final event in history) _EventTile(event as Map),
                const SizedBox(height: 24),
              ],
            ),
          );
        },
      ),
    );
  }
}

class _StatusCard extends StatelessWidget {
  final Map status;
  const _StatusCard(this.status);

  @override
  Widget build(BuildContext context) {
    final passwordSet = (status['password_set'] ?? false) as bool;
    final mfaEnabled = (status['mfa_enabled'] ?? false) as bool;
    final mfaAvailable = (status['mfa_available'] ?? false) as bool;
    final emailVerified = (status['email_verified'] ?? false) as bool;
    final activeSessions = status['active_sessions'] ?? 0;
    const ok = Color(0xFF4AD295), bad = Color(0xFFF2686B);
    const warn = Color(0xFFF5C454);
    return PanelCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _row('Password', passwordSet ? 'Protected' : 'Not set',
              passwordSet ? ok : bad),
          const Divider(height: 18),
          _row(
            'Two-factor auth',
            mfaEnabled ? 'On' : (mfaAvailable ? 'Off' : 'Coming soon'),
            mfaEnabled ? ok : warn,
          ),
          const Divider(height: 18),
          _row('Email', emailVerified ? 'Verified' : 'Unverified',
              emailVerified ? ok : warn),
          const Divider(height: 18),
          Row(
            children: [
              const Expanded(child: Text('Active sessions')),
              Text('$activeSessions',
                  style: const TextStyle(fontWeight: FontWeight.w700)),
            ],
          ),
        ],
      ),
    );
  }

  Widget _row(String label, String value, Color color) {
    return Row(
      children: [
        Expanded(child: Text(label)),
        Text(value,
            style: TextStyle(
                fontSize: 12.5, color: color, fontWeight: FontWeight.w700)),
      ],
    );
  }
}

class _SessionTile extends StatelessWidget {
  final Map session;
  final WidgetRef ref;
  const _SessionTile(this.session, this.ref);

  Future<void> _revoke(BuildContext context) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Sign out of this session?'),
        content: Text('${session['browser']} · ${session['os']}'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Cancel')),
          FilledButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Revoke')),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await ref
          .read(settingsRepositoryProvider)
          .revokeSession((session['id'] as num).toInt());
      ref.invalidate(securityProvider);
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Signed out of that session.')));
      }
    } on ApiException catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final current = (session['current'] ?? false) as bool;
    final ip = '${session['ip'] ?? ''}'.isEmpty ? '—' : '${session['ip']}';
    final lastActive = '${session['last_active'] ?? ''}';
    final lastActiveShort =
        lastActive.length >= 19 ? lastActive.substring(0, 19) : lastActive;
    return ListTile(
      contentPadding: EdgeInsets.zero,
      leading: const Icon(Icons.devices_outlined),
      title: Row(
        children: [
          Flexible(child: Text('${session['browser']} · ${session['os']}')),
          if (current)
            const Padding(
              padding: EdgeInsets.only(left: 8),
              child: StatusBadge('This device'),
            ),
        ],
      ),
      subtitle: Text('$ip · $lastActiveShort'),
      trailing: current
          ? null
          : TextButton(
              onPressed: () => _revoke(context),
              child: const Text('Revoke'),
            ),
    );
  }
}

class _EventTile extends StatelessWidget {
  final Map event;
  const _EventTile(this.event);

  @override
  Widget build(BuildContext context) {
    final kind = '${event['kind']}';
    final color = kind == 'login_success'
        ? const Color(0xFF4AD295)
        : kind == 'login_failed'
            ? const Color(0xFFF2686B)
            : Theme.of(context).colorScheme.outline;
    final at = '${event['created_at'] ?? ''}';
    final atShort = at.length >= 19 ? at.substring(0, 19) : at;
    final meta = [
      '${event['browser']}',
      '${event['os']}',
      if ('${event['ip'] ?? ''}'.isNotEmpty) '${event['ip']}',
    ].join(' · ');
    return ListTile(
      contentPadding: EdgeInsets.zero,
      dense: true,
      leading: Container(
        width: 9,
        height: 9,
        margin: const EdgeInsets.only(top: 6),
        decoration: BoxDecoration(color: color, shape: BoxShape.circle),
      ),
      title: Text('${event['kind_display']}'),
      subtitle: Text(meta, style: Theme.of(context).textTheme.bodySmall),
      trailing: Text(atShort,
          style: Theme.of(context).textTheme.bodySmall),
    );
  }
}
