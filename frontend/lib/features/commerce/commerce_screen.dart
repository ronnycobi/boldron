import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../config/brand.dart';
import '../../core/api_exception.dart';
import 'commerce_repository.dart';

/// Merchant console over the shared commerce engine (spec §20): products,
/// orders + refunds, and sales. Same data as the web store — a change here
/// shows on web immediately, and vice-versa.
class CommerceScreen extends StatelessWidget {
  final int projectId;
  const CommerceScreen({super.key, required this.projectId});

  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 4,
      child: Scaffold(
        appBar: AppBar(
          title: const Text('Store'),
          bottom: const TabBar(isScrollable: true, tabs: [
            Tab(text: 'Products'),
            Tab(text: 'Orders'),
            Tab(text: 'Discounts'),
            Tab(text: 'Sales'),
          ]),
        ),
        body: TabBarView(children: [
          _ProductsTab(projectId: projectId),
          _OrdersTab(projectId: projectId),
          _DiscountsTab(projectId: projectId),
          _SalesTab(projectId: projectId),
        ]),
      ),
    );
  }
}

String _noStore(Object e) => e is ApiException && e.statusCode == 404
    ? 'This project does not have a store yet.'
    : e.toString();

// --- Products ---------------------------------------------------------------

class _ProductsTab extends ConsumerWidget {
  final int projectId;
  const _ProductsTab({required this.projectId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final products = ref.watch(productsProvider(projectId));
    return Scaffold(
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => _editProduct(context, ref, projectId, null),
        icon: const Icon(Icons.add),
        label: const Text('Add product'),
      ),
      body: products.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(_noStore(e), textAlign: TextAlign.center)),
        data: (items) => items.isEmpty
            ? const Center(child: Text('No products yet.'))
            : ListView.separated(
                itemCount: items.length,
                separatorBuilder: (_, __) => const Divider(height: 1),
                itemBuilder: (_, i) {
                  final p = items[i];
                  final low = p.trackInventory && p.stock > 0 && p.stock <= 5;
                  return ListTile(
                    title: Text(p.name),
                    subtitle: Text([
                      p.priceDisplay,
                      if (p.trackInventory) '${p.stock} in stock',
                      if (!p.active) 'hidden',
                    ].join(' · ')),
                    trailing: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        if (p.trackInventory && !p.inStock)
                          const Chip(
                            label: Text('Out'),
                            visualDensity: VisualDensity.compact,
                          )
                        else if (low)
                          Chip(
                            label: const Text('Low'),
                            visualDensity: VisualDensity.compact,
                            backgroundColor: Theme.of(context)
                                .colorScheme
                                .tertiaryContainer,
                          ),
                        const Icon(Icons.edit_outlined),
                      ],
                    ),
                    onTap: () => _editProduct(context, ref, projectId, p),
                  );
                },
              ),
      ),
    );
  }
}

Future<void> _editProduct(
    BuildContext context, WidgetRef ref, int projectId, Product? product) async {
  final name = TextEditingController(text: product?.name ?? '');
  final price = TextEditingController(
      text: product == null ? '' : (product.priceCents / 100).toStringAsFixed(2));
  final stock = TextEditingController(text: product?.stock.toString() ?? '0');
  bool track = product?.trackInventory ?? false;
  bool active = product?.active ?? true;

  await showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    builder: (ctx) => Padding(
      padding: EdgeInsets.only(
        bottom: MediaQuery.of(ctx).viewInsets.bottom,
        left: 16, right: 16, top: 16,
      ),
      child: StatefulBuilder(
        builder: (ctx, setState) => Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(product == null ? 'New product' : 'Edit product',
                style: Theme.of(ctx).textTheme.titleMedium),
            const SizedBox(height: 12),
            TextField(
              controller: name,
              decoration: const InputDecoration(labelText: 'Name'),
            ),
            const SizedBox(height: 8),
            TextField(
              controller: price,
              keyboardType:
                  const TextInputType.numberWithOptions(decimal: true),
              decoration: const InputDecoration(labelText: 'Price'),
            ),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('Track inventory'),
              value: track,
              onChanged: (v) => setState(() => track = v),
            ),
            if (track)
              TextField(
                controller: stock,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(labelText: 'Stock'),
              ),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('Visible in store'),
              value: active,
              onChanged: (v) => setState(() => active = v),
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                if (product != null)
                  TextButton(
                    onPressed: () async {
                      Navigator.pop(ctx);
                      await _run(context, ref, projectId,
                          () => ref
                              .read(commerceRepositoryProvider)
                              .deleteProduct(projectId, product.id));
                    },
                    child: const Text('Delete'),
                  ),
                const Spacer(),
                FilledButton(
                  onPressed: () async {
                    final cents =
                        ((double.tryParse(price.text) ?? 0) * 100).round();
                    Navigator.pop(ctx);
                    final repo = ref.read(commerceRepositoryProvider);
                    await _run(context, ref, projectId, () {
                      if (product == null) {
                        return repo.createProduct(projectId,
                            name: name.text.trim(),
                            priceCents: cents,
                            trackInventory: track,
                            stock: int.tryParse(stock.text) ?? 0);
                      }
                      return repo.updateProduct(projectId, product.id, {
                        'name': name.text.trim(),
                        'price_cents': cents,
                        'track_inventory': track,
                        'stock': int.tryParse(stock.text) ?? 0,
                        'active': active,
                      });
                    });
                  },
                  child: const Text('Save'),
                ),
              ],
            ),
            const SizedBox(height: 12),
          ],
        ),
      ),
    ),
  );
}

Future<void> _run(BuildContext context, WidgetRef ref, int projectId,
    Future<void> Function() action) async {
  try {
    await action();
    ref.invalidate(productsProvider(projectId));
  } on ApiException catch (e) {
    if (context.mounted) {
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(e.message)));
    }
  }
}

// --- Orders -----------------------------------------------------------------

class _OrdersTab extends ConsumerWidget {
  final int projectId;
  const _OrdersTab({required this.projectId});

  static const _statuses = ['', 'paid', 'pending', 'refunded', 'cancelled'];

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final orders = ref.watch(ordersProvider(projectId));
    final filter = ref.watch(ordersFilterProvider(projectId));
    return Column(
      children: [
        SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          child: Row(
            children: [
              for (final s in _statuses)
                Padding(
                  padding: const EdgeInsets.only(right: 8),
                  child: ChoiceChip(
                    label: Text(s.isEmpty ? 'All' : s),
                    selected: filter == s,
                    onSelected: (_) =>
                        ref.read(ordersFilterProvider(projectId).notifier).state = s,
                  ),
                ),
            ],
          ),
        ),
        const Divider(height: 1),
        Expanded(
          child: orders.when(
            loading: () => const Center(child: CircularProgressIndicator()),
            error: (e, _) =>
                Center(child: Text(_noStore(e), textAlign: TextAlign.center)),
            data: (items) => items.isEmpty
                ? const Center(child: Text('No orders.'))
                : RefreshIndicator(
                    onRefresh: () async =>
                        ref.refresh(ordersProvider(projectId).future),
                    child: ListView.separated(
                      itemCount: items.length,
                      separatorBuilder: (_, __) => const Divider(height: 1),
                      itemBuilder: (_, i) {
                        final o = items[i];
                        return ListTile(
                          title: Text(o.reference),
                          subtitle: Padding(
                            padding: const EdgeInsets.only(top: 6),
                            child: Row(
                              children: [
                                StatusBadge(o.status),
                                if (o.customerName.isNotEmpty) ...[
                                  const SizedBox(width: 8),
                                  Flexible(
                                    child: Text(o.customerName,
                                        overflow: TextOverflow.ellipsis),
                                  ),
                                ],
                              ],
                            ),
                          ),
                          trailing: Text(o.totalDisplay),
                          onTap: () =>
                              _orderDetail(context, ref, projectId, o.id),
                        );
                      },
                    ),
                  ),
          ),
        ),
      ],
    );
  }
}

class _DiscountsTab extends ConsumerWidget {
  final int projectId;
  const _DiscountsTab({required this.projectId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final discounts = ref.watch(discountsProvider(projectId));
    return Scaffold(
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => _create(context, ref),
        icon: const Icon(Icons.add),
        label: const Text('Add code'),
      ),
      body: discounts.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) =>
            Center(child: Text(_noStore(e), textAlign: TextAlign.center)),
        data: (items) => items.isEmpty
            ? const Center(child: Text('No discount codes yet.'))
            : ListView(
                children: [
                  for (final d in items)
                    ListTile(
                      leading: const Icon(Icons.local_offer_outlined),
                      title: Text(d.code),
                      subtitle: Text(d.kind == 'percent'
                          ? '${d.percentOff}% off'
                          : '${d.amountOffCents / 100} off'),
                    ),
                ],
              ),
      ),
    );
  }

  Future<void> _create(BuildContext context, WidgetRef ref) async {
    final code = TextEditingController();
    final percent = TextEditingController(text: '10');
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('New discount code'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
                controller: code,
                textCapitalization: TextCapitalization.characters,
                decoration: const InputDecoration(labelText: 'Code (e.g. SAVE10)')),
            TextField(
                controller: percent,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(labelText: 'Percent off')),
          ],
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
          FilledButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Create')),
        ],
      ),
    );
    if (ok == true && code.text.trim().isNotEmpty) {
      try {
        await ref.read(commerceRepositoryProvider).createDiscount(
              projectId,
              code: code.text.trim(),
              percentOff: int.tryParse(percent.text) ?? 0,
            );
        ref.invalidate(discountsProvider(projectId));
      } on ApiException catch (e) {
        if (context.mounted) {
          ScaffoldMessenger.of(context)
              .showSnackBar(SnackBar(content: Text(e.message)));
        }
      }
    }
  }
}

Future<void> _orderDetail(
    BuildContext context, WidgetRef ref, int projectId, int orderId) async {
  final repo = ref.read(commerceRepositoryProvider);
  Order order;
  try {
    order = await repo.order(projectId, orderId);
  } on ApiException catch (e) {
    if (context.mounted) {
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(e.message)));
    }
    return;
  }
  if (!context.mounted) return;
  await showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    builder: (ctx) => Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(order.reference, style: Theme.of(ctx).textTheme.titleLarge),
          Text('${order.status} · ${order.totalDisplay}'),
          const Divider(),
          for (final it in order.items)
            ListTile(
              dense: true,
              contentPadding: EdgeInsets.zero,
              title: Text(it.name),
              trailing: Text('×${it.quantity}'),
            ),
          const SizedBox(height: 8),
          if (order.status == 'paid')
            FilledButton.tonal(
              onPressed: () async {
                Navigator.pop(ctx);
                try {
                  await repo.refund(projectId, orderId);
                  ref.invalidate(ordersProvider(projectId));
                } on ApiException catch (e) {
                  if (context.mounted) {
                    ScaffoldMessenger.of(context)
                        .showSnackBar(SnackBar(content: Text(e.message)));
                  }
                }
              },
              child: const Text('Refund'),
            ),
          const SizedBox(height: 8),
        ],
      ),
    ),
  );
}

// --- Sales ------------------------------------------------------------------

class _SalesTab extends ConsumerWidget {
  final int projectId;
  const _SalesTab({required this.projectId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final sales = ref.watch(salesProvider(projectId));
    return sales.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Center(child: Text(_noStore(e), textAlign: TextAlign.center)),
      data: (s) {
        final revenue = (s['revenue'] as List?) ?? [];
        final top = (s['top_products'] as List?) ?? [];
        return ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Text('Revenue', style: Theme.of(context).textTheme.titleMedium),
            if (revenue.isEmpty) const Text('No paid orders yet.'),
            for (final r in revenue)
              ListTile(
                contentPadding: EdgeInsets.zero,
                title: Text('${(r as Map)['net']}'),
                subtitle: Text('Gross ${r['gross']} · Refunded ${r['refunded']}'),
              ),
            const SizedBox(height: 8),
            Text('Paid orders: ${s['paid_orders'] ?? 0} · Units: ${s['units_sold'] ?? 0}'),
            const SizedBox(height: 16),
            if (top.isNotEmpty) ...[
              Text('Top products',
                  style: Theme.of(context).textTheme.titleMedium),
              for (final t in top)
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: Text('${(t as Map)['name']}'),
                  trailing: Text('${t['units']} sold'),
                ),
            ],
          ],
        );
      },
    );
  }
}
