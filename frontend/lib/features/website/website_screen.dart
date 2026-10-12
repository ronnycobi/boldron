import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_exception.dart';
import 'website_repository.dart';

/// Website management (spec §16): status, publish, versions, custom domains.
class WebsiteScreen extends ConsumerStatefulWidget {
  final int projectId;
  const WebsiteScreen({super.key, required this.projectId});

  @override
  ConsumerState<WebsiteScreen> createState() => _WebsiteScreenState();
}

class _WebsiteScreenState extends ConsumerState<WebsiteScreen> {
  bool _busy = false;

  Future<void> _run(Future<void> Function() action, String ok) async {
    setState(() => _busy = true);
    try {
      await action();
      ref.invalidate(websiteProvider(widget.projectId));
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(ok)));
      }
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(e.message)));
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _addDomain() async {
    final controller = TextEditingController();
    final hostname = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Connect a domain'),
        content: TextField(
          controller: controller,
          autofocus: true,
          decoration: const InputDecoration(hintText: 'shop.example.com'),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
          FilledButton(
              onPressed: () => Navigator.pop(ctx, controller.text.trim()),
              child: const Text('Connect')),
        ],
      ),
    );
    if (hostname != null && hostname.isNotEmpty) {
      await _run(
        () => ref
            .read(websiteRepositoryProvider)
            .connectDomain(widget.projectId, hostname),
        'Domain added — follow the DNS steps to verify it.',
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final site = ref.watch(websiteProvider(widget.projectId));
    final repo = ref.read(websiteRepositoryProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Website')),
      body: site.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Text(
              e is ApiException && e.statusCode == 404
                  ? 'This project does not have a website yet.'
                  : e.toString(),
              textAlign: TextAlign.center,
            ),
          ),
        ),
        data: (info) => ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Card(
              child: ListTile(
                title: Text(info.subdomain),
                subtitle: Text(info.current == null
                    ? 'Not published yet'
                    : '${info.current!.version} · ${info.current!.state}'),
                trailing: info.url.isEmpty ? null : const Icon(Icons.open_in_new),
              ),
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                Expanded(
                  child: FilledButton(
                    onPressed: _busy
                        ? null
                        : () => _run(() => repo.publish(widget.projectId),
                            'Publish started.'),
                    child: const Text('Publish'),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: OutlinedButton(
                    onPressed: _busy
                        ? null
                        : () => _run(() => repo.rollback(widget.projectId),
                            'Rolled back.'),
                    child: const Text('Roll back'),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 20),
            Row(
              children: [
                Text('Custom domains',
                    style: Theme.of(context).textTheme.titleMedium),
                const Spacer(),
                TextButton.icon(
                  onPressed: _busy ? null : _addDomain,
                  icon: const Icon(Icons.add),
                  label: const Text('Add'),
                ),
              ],
            ),
            if (info.domains.isEmpty)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 8),
                child: Text('No custom domains connected.'),
              ),
            for (final d in info.domains)
              Card(
                child: ListTile(
                  title: Text(d.hostname),
                  subtitle: Text(
                      'Verify: ${d.verificationStatus} · SSL: ${d.sslStatus}'),
                  trailing: Icon(
                    d.isLive ? Icons.verified : Icons.pending_outlined,
                    color: d.isLive ? Colors.green : null,
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
