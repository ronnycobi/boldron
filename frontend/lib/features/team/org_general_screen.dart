import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_exception.dart';
import 'team_repository.dart';

/// Organization general settings: name + description. Editing is gated by the
/// real RBAC permission (`org.manage`); otherwise the fields are read-only.
class OrgGeneralScreen extends ConsumerStatefulWidget {
  final int orgId;
  const OrgGeneralScreen({super.key, required this.orgId});

  @override
  ConsumerState<OrgGeneralScreen> createState() => _OrgGeneralScreenState();
}

class _OrgGeneralScreenState extends ConsumerState<OrgGeneralScreen> {
  final _name = TextEditingController();
  final _description = TextEditingController();
  bool _prefilled = false;
  bool _saving = false;

  @override
  void dispose() {
    _name.dispose();
    _description.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    setState(() => _saving = true);
    try {
      await ref.read(teamRepositoryProvider).updateOrganization(widget.orgId, {
        'name': _name.text.trim(),
        'description': _description.text.trim(),
      });
      ref.invalidate(organizationProvider(widget.orgId));
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Organization settings saved.')));
      }
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(e.firstFieldError ?? e.message)));
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final org = ref.watch(organizationProvider(widget.orgId));
    return Scaffold(
      appBar: AppBar(title: const Text('Organization')),
      body: org.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(e.toString())),
        data: (o) {
          final canManage =
              ((o['my_permissions'] as List?) ?? []).contains('org.manage');
          if (!_prefilled) {
            _name.text = '${o['name'] ?? ''}';
            _description.text = '${o['description'] ?? ''}';
            _prefilled = true;
          }
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Text('${o['member_count'] ?? 0} members · ${o['slug'] ?? ''}',
                  style: Theme.of(context).textTheme.bodySmall),
              const SizedBox(height: 16),
              TextField(
                controller: _name,
                readOnly: !canManage,
                decoration: const InputDecoration(labelText: 'Organization name'),
              ),
              const SizedBox(height: 10),
              TextField(
                controller: _description,
                readOnly: !canManage,
                maxLines: 4,
                maxLength: 2000,
                decoration: const InputDecoration(labelText: 'Description'),
              ),
              const SizedBox(height: 12),
              if (canManage)
                FilledButton(
                  onPressed: _saving ? null : _save,
                  child: Text(_saving ? 'Saving…' : 'Save'),
                )
              else
                Text('You have view-only access to this organization.',
                    style: Theme.of(context).textTheme.bodySmall),
            ],
          );
        },
      ),
    );
  }
}
