import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'team_repository.dart';

/// Roles & permissions reference: the role → permission matrix the backend
/// enforces, shown honestly. Role assignment lives on the Members screen.
class OrgRolesScreen extends ConsumerWidget {
  final int orgId;
  const OrgRolesScreen({super.key, required this.orgId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final data = ref.watch(orgRolesProvider(orgId));
    return Scaffold(
      appBar: AppBar(title: const Text('Roles & permissions')),
      body: data.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(e.toString())),
        data: (d) {
          final roles = ((d['roles'] as List?) ?? [])
              .map((r) => (r as Map).cast<String, dynamic>())
              .toList();
          final matrix = ((d['matrix'] as List?) ?? [])
              .map((m) => (m as Map).cast<String, dynamic>())
              .toList();
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Text(
                'What each built-in role can do. Assign roles on the Members screen.',
                style: Theme.of(context).textTheme.bodySmall,
              ),
              const SizedBox(height: 14),
              for (final row in matrix)
                _PermissionRow(row: row, roles: roles),
              const SizedBox(height: 16),
              Text(
                'Everyone can use the product. The rows above are management '
                'capabilities on top of that. Custom roles aren’t available — '
                'these three cover every current capability.',
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ],
          );
        },
      ),
    );
  }
}

class _PermissionRow extends StatelessWidget {
  final Map<String, dynamic> row;
  final List<Map<String, dynamic>> roles;
  const _PermissionRow({required this.row, required this.roles});

  @override
  Widget build(BuildContext context) {
    final grants = (row['roles'] as Map?)?.cast<String, dynamic>() ?? {};
    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('${row['label']}',
                style: const TextStyle(fontWeight: FontWeight.w700)),
            const SizedBox(height: 2),
            Text('${row['description']}',
                style: Theme.of(context).textTheme.bodySmall),
            const SizedBox(height: 10),
            Wrap(
              spacing: 8,
              runSpacing: 6,
              children: [
                for (final r in roles)
                  _RoleChip(
                    label: '${r['label']}',
                    granted: (grants['${r['key']}'] ?? false) as bool,
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _RoleChip extends StatelessWidget {
  final String label;
  final bool granted;
  const _RoleChip({required this.label, required this.granted});

  @override
  Widget build(BuildContext context) {
    final color = granted ? const Color(0xFF4AD295) : Theme.of(context).disabledColor;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        border: Border.all(color: color.withOpacity(0.5)),
        borderRadius: BorderRadius.circular(99),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(granted ? Icons.check : Icons.remove, size: 14, color: color),
          const SizedBox(width: 4),
          Text(label, style: TextStyle(fontSize: 12, color: color)),
        ],
      ),
    );
  }
}
