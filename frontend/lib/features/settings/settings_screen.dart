import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../config/brand.dart';
import '../../core/providers.dart';
import 'settings_repository.dart';

/// Settings control center (P0): the same scoped overview the web shows —
/// real alerts + account/org status + the section map. Built sections navigate
/// to their screen; unbuilt ones are honestly marked "soon".
class SettingsScreen extends ConsumerWidget {
  const SettingsScreen({super.key});

  // Map a section key → an in-app route, when one exists today.
  String? _route(WidgetRef ref, String scope, String key) {
    final orgId = ref.read(activeOrgProvider);
    switch ('$scope.$key') {
      case 'account.profile':
        return '/account/security';
      case 'account.security':
      case 'account.sessions':
        return '/settings/security';
      case 'account.appearance': // preferences (language/timezone) live here
        return '/settings/preferences';
      case 'organization.general':
        return orgId == null ? null : '/orgs/$orgId/settings';
      case 'organization.roles':
        return orgId == null ? null : '/orgs/$orgId/roles';
      case 'organization.ai':
        return orgId == null ? null : '/orgs/$orgId/ai';
      case 'organization.developer':
        return orgId == null ? null : '/orgs/$orgId/developer';
      case 'organization.integrations':
        return '/settings/integrations';
      case 'organization.members':
        return orgId == null ? null : '/orgs/$orgId/team';
      case 'organization.billing':
      case 'organization.usage':
        return orgId == null ? null : '/orgs/$orgId/billing';
      default:
        return null;
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final overview = ref.watch(settingsOverviewProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Settings')),
      body: overview.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(e.toString())),
        data: (o) {
          final alerts = (o['alerts'] as List?) ?? [];
          final account = (o['account'] as Map?) ?? {};
          final orgs = (o['organizations'] as List?) ?? [];
          final sections = (o['sections'] as Map?) ?? {};
          return RefreshIndicator(
            onRefresh: () async =>
                ref.refresh(settingsOverviewProvider.future),
            child: ListView(
              padding: const EdgeInsets.all(16),
              children: [
                for (final a in alerts) _AlertCard(a as Map),
                _StatusCard(account: account, orgs: orgs),
                const SizedBox(height: 8),
                _group(context, ref, 'Your account', 'account',
                    (sections['account'] as List?) ?? []),
                _group(context, ref, 'Organization', 'organization',
                    (sections['organization'] as List?) ?? []),
                _group(context, ref, 'Project', 'project',
                    (sections['project'] as List?) ?? []),
                const SizedBox(height: 24),
              ],
            ),
          );
        },
      ),
    );
  }

  Widget _group(BuildContext context, WidgetRef ref, String title, String scope,
      List sections) {
    if (sections.isEmpty) return const SizedBox.shrink();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(2, 18, 0, 8),
          child: Text(title.toUpperCase(),
              style: Theme.of(context).textTheme.labelSmall),
        ),
        for (final s in sections)
          _SectionTile(
            label: '${(s as Map)['label']}',
            available: (s['available'] ?? false) as bool,
            route: (s['available'] ?? false) as bool
                ? _route(ref, scope, '${s['key']}')
                : null,
          ),
      ],
    );
  }
}

class _AlertCard extends StatelessWidget {
  final Map alert;
  const _AlertCard(this.alert);

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: scheme.tertiaryContainer,
          borderRadius: BorderRadius.circular(12),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(Icons.warning_amber_rounded,
                color: scheme.onTertiaryContainer, size: 20),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('${alert['title']}',
                      style: TextStyle(
                          fontWeight: FontWeight.w700,
                          color: scheme.onTertiaryContainer)),
                  const SizedBox(height: 2),
                  Text('${alert['detail']}',
                      style: TextStyle(
                          fontSize: 12.5, color: scheme.onTertiaryContainer)),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _StatusCard extends StatelessWidget {
  final Map account;
  final List orgs;
  const _StatusCard({required this.account, required this.orgs});

  @override
  Widget build(BuildContext context) {
    final verified = (account['email_verified'] ?? false) as bool;
    return PanelCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text('${account['display_name'] ?? ''}',
                    style: const TextStyle(fontWeight: FontWeight.w700)),
              ),
              StatusBadge(verified ? 'verified' : 'unverified'),
            ],
          ),
          Text('${account['email'] ?? ''}',
              style: Theme.of(context).textTheme.bodySmall),
          for (final org in orgs) ...[
            const Divider(height: 18),
            Text('${(org as Map)['name']}',
                style: const TextStyle(fontWeight: FontWeight.w600)),
            Text([
              '${org['role'] ?? ''}',
              '${org['members']} member${org['members'] == 1 ? '' : 's'}',
              if (org['plan'] != null) '${org['plan']}',
              if (org['credits_pct'] != null) '${org['credits_pct']}% credits',
            ].join(' · '), style: Theme.of(context).textTheme.bodySmall),
          ],
        ],
      ),
    );
  }
}

class _SectionTile extends StatelessWidget {
  final String label;
  final bool available;
  final String? route;
  const _SectionTile(
      {required this.label, required this.available, required this.route});

  @override
  Widget build(BuildContext context) {
    final enabled = available && route != null;
    return Opacity(
      opacity: available ? 1 : 0.5,
      child: ListTile(
        contentPadding: const EdgeInsets.symmetric(horizontal: 4),
        title: Text(label),
        trailing: available
            ? const Icon(Icons.chevron_right)
            : const Chip(
                label: Text('soon'),
                visualDensity: VisualDensity.compact,
              ),
        onTap: enabled ? () => context.push(route!) : null,
      ),
    );
  }
}
