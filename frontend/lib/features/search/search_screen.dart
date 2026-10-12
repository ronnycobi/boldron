import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/providers.dart';

/// Global search across the user's projects, products, orders, tickets and
/// mobile apps (spec §28), scoped to their organizations by the backend.
class SearchScreen extends ConsumerStatefulWidget {
  const SearchScreen({super.key});

  @override
  ConsumerState<SearchScreen> createState() => _SearchScreenState();
}

class _SearchScreenState extends ConsumerState<SearchScreen> {
  final _controller = TextEditingController();
  Timer? _debounce;
  Map<String, dynamic>? _results;
  bool _loading = false;

  @override
  void dispose() {
    _debounce?.cancel();
    _controller.dispose();
    super.dispose();
  }

  void _onChanged(String q) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 350), () => _search(q));
  }

  Future<void> _search(String q) async {
    if (q.trim().isEmpty) {
      setState(() => _results = null);
      return;
    }
    setState(() => _loading = true);
    try {
      final data =
          await ref.read(apiClientProvider).get('search/', query: {'q': q});
      setState(() => _results = (data as Map)['results'] as Map<String, dynamic>);
    } catch (_) {
      setState(() => _results = null);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: TextField(
          controller: _controller,
          autofocus: true,
          onChanged: _onChanged,
          decoration: const InputDecoration(
            hintText: 'Search projects, products, orders…',
            border: InputBorder.none,
          ),
        ),
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _results == null
              ? const Center(child: Text('Type to search.'))
              : _ResultsList(results: _results!),
    );
  }
}

class _ResultsList extends StatelessWidget {
  final Map<String, dynamic> results;
  const _ResultsList({required this.results});

  @override
  Widget build(BuildContext context) {
    final projects = (results['projects'] as List?) ?? [];
    final products = (results['products'] as List?) ?? [];
    final orders = (results['orders'] as List?) ?? [];
    final tickets = (results['tickets'] as List?) ?? [];
    final apps = (results['mobile_apps'] as List?) ?? [];
    final empty = projects.isEmpty &&
        products.isEmpty &&
        orders.isEmpty &&
        tickets.isEmpty &&
        apps.isEmpty;
    if (empty) return const Center(child: Text('No matches.'));
    return ListView(
      children: [
        _group(context, 'Projects', projects, (p) {
          final m = p as Map;
          return ListTile(
            leading: const Icon(Icons.folder_outlined),
            title: Text('${m['name']}'),
            onTap: () => context.push('/projects/${m['id']}'),
          );
        }),
        _group(context, 'Products', products, (p) {
          final m = p as Map;
          return ListTile(
            leading: const Icon(Icons.shopping_bag_outlined),
            title: Text('${m['name']}'),
            subtitle: Text('${m['price_display']}'),
          );
        }),
        _group(context, 'Orders', orders, (o) {
          final m = o as Map;
          return ListTile(
            leading: const Icon(Icons.receipt_long_outlined),
            title: Text('${m['reference']}'),
            subtitle: Text('${m['status']} · ${m['total_display']}'),
          );
        }),
        _group(context, 'Support', tickets, (t) {
          final m = t as Map;
          return ListTile(
            leading: const Icon(Icons.support_agent),
            title: Text('${m['subject']}'),
            subtitle: Text('${m['number']}'),
            onTap: () => context.push('/support/${m['id']}'),
          );
        }),
        _group(context, 'Mobile apps', apps, (a) {
          final m = a as Map;
          return ListTile(
            leading: const Icon(Icons.phone_iphone),
            title: Text('${m['name']}'),
          );
        }),
      ],
    );
  }

  Widget _group(BuildContext context, String title, List items,
      Widget Function(dynamic) tile) {
    if (items.isEmpty) return const SizedBox.shrink();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
          child: Text(title.toUpperCase(),
              style: Theme.of(context).textTheme.labelSmall),
        ),
        for (final it in items) tile(it),
      ],
    );
  }
}
