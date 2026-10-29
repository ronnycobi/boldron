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
      length: 7,
      child: Scaffold(
        appBar: AppBar(
          title: const Text('Store'),
          bottom: const TabBar(isScrollable: true, tabs: [
            Tab(text: 'Products'),
            Tab(text: 'Orders'),
            Tab(text: 'Subscriptions'),
            Tab(text: 'Campaigns'),
            Tab(text: 'Discounts'),
            Tab(text: 'Money'),
            Tab(text: 'Sales'),
          ]),
        ),
        body: TabBarView(children: [
          _ProductsTab(projectId: projectId),
          _OrdersTab(projectId: projectId),
          _SubscriptionsTab(projectId: projectId),
          _CampaignsTab(projectId: projectId),
          _DiscountsTab(projectId: projectId),
          _MoneyTab(projectId: projectId),
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
          Row(
            children: [
              OutlinedButton.icon(
                onPressed: () {
                  Navigator.pop(ctx);
                  _showInvoice(context, ref, projectId, orderId);
                },
                icon: const Icon(Icons.receipt_long_outlined),
                label: const Text('Invoice'),
              ),
              const Spacer(),
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
            ],
          ),
          const SizedBox(height: 8),
        ],
      ),
    ),
  );
}

// --- Invoice ----------------------------------------------------------------

Future<void> _showInvoice(
    BuildContext context, WidgetRef ref, int projectId, int orderId) async {
  Map<String, dynamic> inv;
  try {
    inv = await ref.read(commerceRepositoryProvider).orderInvoice(projectId, orderId);
  } on ApiException catch (e) {
    if (context.mounted) {
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(e.message)));
    }
    return;
  }
  if (!context.mounted) return;
  final items = (inv['items'] as List?) ?? [];
  final paid = inv['payment_state'] == 'Paid';
  await showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    builder: (ctx) => Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text('${inv['number']}',
                    style: Theme.of(ctx).textTheme.titleLarge),
              ),
              Chip(
                label: Text('${inv['payment_state']}'),
                backgroundColor: paid
                    ? Theme.of(ctx).colorScheme.tertiaryContainer
                    : Theme.of(ctx).colorScheme.surfaceVariant,
                visualDensity: VisualDensity.compact,
              ),
            ],
          ),
          Text('Order ${inv['reference']}',
              style: Theme.of(ctx).textTheme.bodySmall),
          const Divider(),
          for (final it in items)
            ListTile(
              dense: true,
              contentPadding: EdgeInsets.zero,
              title: Text('${(it as Map)['name']}'),
              trailing: Text('${it['line_total_display']}'),
            ),
          const Divider(),
          _invoiceRow(ctx, 'Subtotal', '${inv['subtotal_display']}'),
          if ((inv['tax_cents'] ?? 0) != 0)
            _invoiceRow(ctx, '${inv['tax_label']}', '${inv['tax_display']}'),
          _invoiceRow(ctx, 'Total', '${inv['total_display']}', bold: true),
          if ((inv['amount_paid_cents'] ?? 0) != 0) ...[
            _invoiceRow(ctx, 'Amount paid', '-${inv['amount_paid_display']}'),
            _invoiceRow(ctx, 'Balance due', '${inv['balance_due_display']}',
                bold: true),
          ],
          const SizedBox(height: 12),
        ],
      ),
    ),
  );
}

Widget _invoiceRow(BuildContext ctx, String label, String value,
    {bool bold = false}) {
  final style = bold
      ? Theme.of(ctx).textTheme.titleMedium
      : Theme.of(ctx).textTheme.bodyMedium;
  return Padding(
    padding: const EdgeInsets.symmetric(vertical: 2),
    child: Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [Text(label, style: style), Text(value, style: style)],
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

// --- Subscriptions ----------------------------------------------------------

class _SubscriptionsTab extends ConsumerWidget {
  final int projectId;
  const _SubscriptionsTab({required this.projectId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final view = ref.watch(subscriptionsProvider(projectId));
    return Scaffold(
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => _subscribe(context, ref),
        icon: const Icon(Icons.person_add_alt),
        label: const Text('Subscribe'),
      ),
      body: view.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(_noStore(e), textAlign: TextAlign.center)),
        data: (v) => RefreshIndicator(
          onRefresh: () async => ref.refresh(subscriptionsProvider(projectId).future),
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceAround,
                    children: [
                      _stat(context, '${v.overview['active'] ?? 0}', 'Active'),
                      _stat(context, '${v.overview['mrr_display'] ?? '—'}', 'MRR'),
                      _stat(context, '${v.overview['past_due'] ?? 0}', 'Past due'),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(
                    child: Text('Subscribers',
                        style: Theme.of(context).textTheme.titleMedium),
                  ),
                  TextButton.icon(
                    onPressed: () => _managePlans(context, ref),
                    icon: const Icon(Icons.sell_outlined, size: 18),
                    label: const Text('Plans'),
                  ),
                  TextButton.icon(
                    onPressed: () async {
                      final n = await _runValue(context, ref, projectId,
                          () => ref.read(commerceRepositoryProvider).renewSubscriptions(projectId));
                      if (context.mounted && n != null) {
                        ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(content: Text('Opened $n due cycle(s).')));
                      }
                    },
                    icon: const Icon(Icons.autorenew, size: 18),
                    label: const Text('Renew'),
                  ),
                ],
              ),
              if (v.subscriptions.isEmpty)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 24),
                  child: Center(child: Text('No subscribers yet.')),
                ),
              for (final s in v.subscriptions)
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: Text(s.customerEmail.isEmpty ? s.plan : s.customerEmail),
                  subtitle: Padding(
                    padding: const EdgeInsets.only(top: 6),
                    child: Row(children: [
                      StatusBadge(s.status),
                      const SizedBox(width: 8),
                      Flexible(
                        child: Text('${s.plan} · ${s.amountDisplay}/${s.interval}',
                            overflow: TextOverflow.ellipsis),
                      ),
                    ]),
                  ),
                  trailing: s.status == 'cancelled'
                      ? null
                      : IconButton(
                          icon: const Icon(Icons.cancel_outlined),
                          tooltip: 'Cancel',
                          onPressed: () => _run(context, ref, projectId, () async {
                            await ref
                                .read(commerceRepositoryProvider)
                                .cancelSubscription(projectId, s.id);
                            ref.invalidate(subscriptionsProvider(projectId));
                          }),
                        ),
                ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _managePlans(BuildContext context, WidgetRef ref) async {
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      builder: (ctx) => Consumer(
        builder: (ctx, r, _) {
          final plans = r.watch(plansProvider(projectId));
          return Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Plans', style: Theme.of(ctx).textTheme.titleLarge),
                const SizedBox(height: 8),
                plans.when(
                  loading: () => const Center(child: CircularProgressIndicator()),
                  error: (e, _) => Text(_noStore(e)),
                  data: (items) => Column(
                    children: [
                      for (final p in items)
                        ListTile(
                          dense: true,
                          contentPadding: EdgeInsets.zero,
                          title: Text(p.name),
                          trailing: Text('${p.amountDisplay}/${p.interval}'),
                        ),
                      if (items.isEmpty) const Text('No plans yet.'),
                    ],
                  ),
                ),
                const Divider(),
                FilledButton.icon(
                  onPressed: () {
                    Navigator.pop(ctx);
                    _createPlan(context, ref);
                  },
                  icon: const Icon(Icons.add),
                  label: const Text('New plan'),
                ),
                const SizedBox(height: 8),
              ],
            ),
          );
        },
      ),
    );
  }

  Future<void> _createPlan(BuildContext context, WidgetRef ref) async {
    final name = TextEditingController();
    final price = TextEditingController();
    String interval = 'monthly';
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('New plan'),
        content: StatefulBuilder(
          builder: (ctx, setState) => Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                  controller: name,
                  decoration: const InputDecoration(labelText: 'Name (e.g. Pro)')),
              TextField(
                  controller: price,
                  keyboardType:
                      const TextInputType.numberWithOptions(decimal: true),
                  decoration: const InputDecoration(labelText: 'Price per interval')),
              const SizedBox(height: 8),
              DropdownButtonFormField<String>(
                value: interval,
                decoration: const InputDecoration(labelText: 'Interval'),
                items: const [
                  DropdownMenuItem(value: 'weekly', child: Text('Weekly')),
                  DropdownMenuItem(value: 'monthly', child: Text('Monthly')),
                  DropdownMenuItem(value: 'yearly', child: Text('Yearly')),
                ],
                onChanged: (v) => setState(() => interval = v ?? 'monthly'),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
          FilledButton(
              onPressed: () => Navigator.pop(ctx, true), child: const Text('Create')),
        ],
      ),
    );
    if (ok == true && name.text.trim().isNotEmpty) {
      final cents = ((double.tryParse(price.text) ?? 0) * 100).round();
      if (!context.mounted) return;
      await _run(context, ref, projectId, () async {
        await ref.read(commerceRepositoryProvider).createPlan(projectId,
            name: name.text.trim(), amountCents: cents, interval: interval);
        ref.invalidate(plansProvider(projectId));
      });
    }
  }

  Future<void> _subscribe(BuildContext context, WidgetRef ref) async {
    final plans = await ref.read(commerceRepositoryProvider).plans(projectId).catchError(
          (_) => <SubscriptionPlan>[],
        );
    if (!context.mounted) return;
    if (plans.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Create a plan first (Plans button).')));
      return;
    }
    final email = TextEditingController();
    final name = TextEditingController();
    int planId = plans.first.id;
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Subscribe a customer'),
        content: StatefulBuilder(
          builder: (ctx, setState) => Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              DropdownButtonFormField<int>(
                value: planId,
                decoration: const InputDecoration(labelText: 'Plan'),
                items: [
                  for (final p in plans)
                    DropdownMenuItem(
                        value: p.id,
                        child: Text('${p.name} · ${p.amountDisplay}/${p.interval}')),
                ],
                onChanged: (v) => setState(() => planId = v ?? planId),
              ),
              TextField(
                  controller: name,
                  decoration: const InputDecoration(labelText: 'Customer name')),
              TextField(
                  controller: email,
                  keyboardType: TextInputType.emailAddress,
                  decoration: const InputDecoration(labelText: 'Customer email')),
            ],
          ),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
          FilledButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Subscribe')),
        ],
      ),
    );
    if (ok == true) {
      if (!context.mounted) return;
      await _run(context, ref, projectId, () async {
        await ref.read(commerceRepositoryProvider).subscribe(projectId,
            planId: planId,
            customerName: name.text.trim(),
            customerEmail: email.text.trim());
        ref.invalidate(subscriptionsProvider(projectId));
      });
    }
  }
}

// --- Campaigns --------------------------------------------------------------

class _CampaignsTab extends ConsumerWidget {
  final int projectId;
  const _CampaignsTab({required this.projectId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final view = ref.watch(campaignsProvider(projectId));
    return Scaffold(
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => _create(context, ref),
        icon: const Icon(Icons.add),
        label: const Text('New campaign'),
      ),
      body: view.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(_noStore(e), textAlign: TextAlign.center)),
        data: (v) => ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Text('Audience: ${v.audienceSize} contact(s) (leads + customers)',
                style: Theme.of(context).textTheme.bodyMedium),
            const Divider(),
            if (v.campaigns.isEmpty)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 24),
                child: Center(child: Text('No campaigns yet.')),
              ),
            for (final c in v.campaigns)
              ListTile(
                contentPadding: EdgeInsets.zero,
                title: Text(c.subject),
                subtitle: Padding(
                  padding: const EdgeInsets.only(top: 6),
                  child: Row(children: [
                    StatusBadge(c.status),
                    const SizedBox(width: 8),
                    if (c.status == 'sent')
                      Text('${c.sentCount} sent'
                          '${c.failedCount > 0 ? ' · ${c.failedCount} failed' : ''}'),
                  ]),
                ),
                trailing: c.status == 'draft' || c.status == 'failed'
                    ? TextButton(
                        onPressed: () => _run(context, ref, projectId, () async {
                          await ref
                              .read(commerceRepositoryProvider)
                              .sendCampaign(projectId, c.id);
                          ref.invalidate(campaignsProvider(projectId));
                        }),
                        child: const Text('Send'),
                      )
                    : null,
              ),
          ],
        ),
      ),
    );
  }

  Future<void> _create(BuildContext context, WidgetRef ref) async {
    final subject = TextEditingController();
    final body = TextEditingController();
    String audience = 'all';
    final ok = await showModalBottomSheet<bool>(
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
              Text('New campaign', style: Theme.of(ctx).textTheme.titleMedium),
              const SizedBox(height: 8),
              TextField(
                  controller: subject,
                  decoration: const InputDecoration(labelText: 'Subject')),
              TextField(
                  controller: body,
                  maxLines: 4,
                  decoration: const InputDecoration(
                      labelText: 'Message (use {{name}} to personalise)')),
              const SizedBox(height: 8),
              DropdownButtonFormField<String>(
                value: audience,
                decoration: const InputDecoration(labelText: 'Audience'),
                items: const [
                  DropdownMenuItem(value: 'all', child: Text('Leads + customers')),
                  DropdownMenuItem(value: 'leads', child: Text('Leads')),
                  DropdownMenuItem(value: 'customers', child: Text('Customers')),
                ],
                onChanged: (v) => setState(() => audience = v ?? 'all'),
              ),
              const SizedBox(height: 12),
              SizedBox(
                width: double.infinity,
                child: FilledButton(
                  onPressed: () => Navigator.pop(ctx, true),
                  child: const Text('Create draft'),
                ),
              ),
              const SizedBox(height: 12),
            ],
          ),
        ),
      ),
    );
    if (ok == true && subject.text.trim().isNotEmpty) {
      if (!context.mounted) return;
      await _run(context, ref, projectId, () async {
        await ref.read(commerceRepositoryProvider).createCampaign(projectId,
            subject: subject.text.trim(),
            body: body.text.trim(),
            audienceSource: audience);
        ref.invalidate(campaignsProvider(projectId));
      });
    }
  }
}

// --- Money (tax + currency) -------------------------------------------------

class _MoneyTab extends ConsumerWidget {
  final int projectId;
  const _MoneyTab({required this.projectId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final tax = ref.watch(taxProvider(projectId));
    final currency = ref.watch(currencyProvider(projectId));
    return RefreshIndicator(
      onRefresh: () async {
        ref.invalidate(taxProvider(projectId));
        ref.invalidate(currencyProvider(projectId));
      },
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text('Tax', style: Theme.of(context).textTheme.titleMedium),
          tax.when(
            loading: () => const Padding(
                padding: EdgeInsets.all(8), child: LinearProgressIndicator()),
            error: (e, _) => Text(_noStore(e)),
            data: (t) => ListTile(
              contentPadding: EdgeInsets.zero,
              title: Text(t['percent'] == null
                  ? 'No tax rate set'
                  : '${t['name']} · ${t['rate_display']}'),
              trailing: TextButton(
                onPressed: () => _setTax(context, ref, t),
                child: const Text('Set'),
              ),
            ),
          ),
          const Divider(height: 24),
          Row(
            children: [
              Expanded(
                child: Text('Exchange rates',
                    style: Theme.of(context).textTheme.titleMedium),
              ),
              TextButton.icon(
                onPressed: () => _setRate(context, ref),
                icon: const Icon(Icons.add, size: 18),
                label: const Text('Rate'),
              ),
            ],
          ),
          currency.when(
            loading: () => const Padding(
                padding: EdgeInsets.all(8), child: LinearProgressIndicator()),
            error: (e, _) => Text(_noStore(e)),
            data: (c) {
              final rates = (c['rates'] as List?) ?? [];
              final feed = (c['live_feed'] as Map?) ?? {};
              return Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (rates.isEmpty) const Text('No stored rates yet.'),
                  for (final r in rates)
                    ListTile(
                      dense: true,
                      contentPadding: EdgeInsets.zero,
                      title: Text(
                          '1 ${(r as Map)['base']} = ${r['rate']} ${r['quote']}'),
                      subtitle: Text('${r['source']}'),
                    ),
                  const SizedBox(height: 8),
                  Card(
                    color: Theme.of(context).colorScheme.surfaceVariant,
                    child: Padding(
                      padding: const EdgeInsets.all(12),
                      child: Row(
                        children: [
                          Icon(
                            (feed['connected'] ?? false) == true
                                ? Icons.cloud_done_outlined
                                : Icons.cloud_off_outlined,
                            size: 18,
                          ),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(
                              '${feed['detail'] ?? 'Live FX feed not connected.'}',
                              style: Theme.of(context).textTheme.bodySmall,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ],
              );
            },
          ),
        ],
      ),
    );
  }

  Future<void> _setTax(
      BuildContext context, WidgetRef ref, Map<String, dynamic> current) async {
    final name = TextEditingController(text: (current['name'] ?? 'VAT') as String);
    final percent =
        TextEditingController(text: current['percent']?.toString() ?? '');
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Set tax rate'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
                controller: name,
                decoration: const InputDecoration(labelText: 'Name (e.g. VAT)')),
            TextField(
                controller: percent,
                keyboardType:
                    const TextInputType.numberWithOptions(decimal: true),
                decoration: const InputDecoration(labelText: 'Percent (e.g. 15)')),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
          FilledButton(
              onPressed: () => Navigator.pop(ctx, true), child: const Text('Save')),
        ],
      ),
    );
    if (ok == true) {
      if (!context.mounted) return;
      await _run(context, ref, projectId, () async {
        await ref.read(commerceRepositoryProvider).setTax(projectId,
            name: name.text.trim().isEmpty ? 'Tax' : name.text.trim(),
            percent: double.tryParse(percent.text) ?? 0);
        ref.invalidate(taxProvider(projectId));
      });
    }
  }

  Future<void> _setRate(BuildContext context, WidgetRef ref) async {
    final base = TextEditingController(text: 'USD');
    final quote = TextEditingController(text: 'ZAR');
    final rate = TextEditingController();
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Add exchange rate'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
                controller: base,
                textCapitalization: TextCapitalization.characters,
                decoration: const InputDecoration(labelText: 'From (e.g. USD)')),
            TextField(
                controller: quote,
                textCapitalization: TextCapitalization.characters,
                decoration: const InputDecoration(labelText: 'To (e.g. ZAR)')),
            TextField(
                controller: rate,
                keyboardType:
                    const TextInputType.numberWithOptions(decimal: true),
                decoration: const InputDecoration(labelText: 'Rate (1 from = ? to)')),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
          FilledButton(
              onPressed: () => Navigator.pop(ctx, true), child: const Text('Save')),
        ],
      ),
    );
    if (ok == true && rate.text.trim().isNotEmpty) {
      if (!context.mounted) return;
      await _run(context, ref, projectId, () async {
        await ref.read(commerceRepositoryProvider).setRate(projectId,
            base: base.text.trim(), quote: quote.text.trim(), rate: rate.text.trim());
        ref.invalidate(currencyProvider(projectId));
      });
    }
  }
}

Widget _stat(BuildContext context, String value, String label) => Column(
      children: [
        Text(value, style: Theme.of(context).textTheme.titleLarge),
        Text(label, style: Theme.of(context).textTheme.bodySmall),
      ],
    );

/// Like [_run] but returns the action's value (null on error), and invalidates
/// the subscriptions view.
Future<T?> _runValue<T>(BuildContext context, WidgetRef ref, int projectId,
    Future<T> Function() action) async {
  try {
    final result = await action();
    ref.invalidate(subscriptionsProvider(projectId));
    return result;
  } on ApiException catch (e) {
    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    }
    return null;
  }
}
