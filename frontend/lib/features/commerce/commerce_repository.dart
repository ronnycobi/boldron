import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_client.dart';
import '../../core/providers.dart';

class Product {
  final int id;
  final String name;
  final String priceDisplay;
  final int priceCents;
  final String currency;
  final bool active;
  final bool trackInventory;
  final int stock;
  final bool inStock;

  const Product({
    required this.id,
    required this.name,
    required this.priceDisplay,
    required this.priceCents,
    required this.currency,
    required this.active,
    required this.trackInventory,
    required this.stock,
    required this.inStock,
  });

  factory Product.fromJson(Map<String, dynamic> j) => Product(
        id: j['id'] as int,
        name: (j['name'] ?? '') as String,
        priceDisplay: (j['price_display'] ?? '') as String,
        priceCents: (j['price_cents'] ?? 0) as int,
        currency: (j['currency'] ?? 'USD') as String,
        active: (j['active'] ?? true) as bool,
        trackInventory: (j['track_inventory'] ?? false) as bool,
        stock: (j['stock'] ?? 0) as int,
        inStock: (j['in_stock'] ?? true) as bool,
      );
}

class Order {
  final int id;
  final String reference;
  final String status;
  final String totalDisplay;
  final String customerName;
  final String createdAt;
  final List<OrderItem> items;

  const Order({
    required this.id,
    required this.reference,
    required this.status,
    required this.totalDisplay,
    required this.customerName,
    required this.createdAt,
    this.items = const [],
  });

  factory Order.fromJson(Map<String, dynamic> j) => Order(
        id: j['id'] as int,
        reference: (j['reference'] ?? '') as String,
        status: (j['status'] ?? '') as String,
        totalDisplay: (j['total_display'] ?? '') as String,
        customerName: (j['customer_name'] ?? '') as String,
        createdAt: (j['created_at'] ?? '') as String,
        items: ((j['items'] as List?) ?? [])
            .map((i) => OrderItem.fromJson(i as Map<String, dynamic>))
            .toList(),
      );
}

class OrderItem {
  final String name;
  final int quantity;
  final int lineTotalCents;
  const OrderItem({
    required this.name,
    required this.quantity,
    required this.lineTotalCents,
  });

  factory OrderItem.fromJson(Map<String, dynamic> j) => OrderItem(
        name: (j['name'] ?? '') as String,
        quantity: (j['quantity'] ?? 0) as int,
        lineTotalCents: (j['line_total_cents'] ?? 0) as int,
      );
}

class CommerceRepository {
  final ApiClient _api;
  CommerceRepository(this._api);

  String _base(int projectId) => 'projects/$projectId/commerce';

  Future<List<Product>> products(int projectId) async {
    final data = await _api.get('${_base(projectId)}/products/');
    return (data as List)
        .map((p) => Product.fromJson(p as Map<String, dynamic>))
        .toList();
  }

  Future<void> createProduct(int projectId,
      {required String name,
      required int priceCents,
      bool trackInventory = false,
      int stock = 0}) {
    return _api.post('${_base(projectId)}/products/', body: {
      'name': name,
      'price_cents': priceCents,
      'track_inventory': trackInventory,
      'stock': stock,
    });
  }

  Future<void> updateProduct(int projectId, int productId,
          Map<String, dynamic> fields) =>
      _api.patch('${_base(projectId)}/products/$productId/', body: fields);

  Future<void> deleteProduct(int projectId, int productId) =>
      _api.delete('${_base(projectId)}/products/$productId/');

  Future<List<Order>> orders(int projectId, {String? status}) async {
    final data = await _api.get('${_base(projectId)}/orders/',
        query: status == null ? null : {'status': status});
    return (data as List)
        .map((o) => Order.fromJson(o as Map<String, dynamic>))
        .toList();
  }

  Future<Order> order(int projectId, int orderId) async {
    final data = await _api.get('${_base(projectId)}/orders/$orderId/');
    return Order.fromJson(data as Map<String, dynamic>);
  }

  Future<void> refund(int projectId, int orderId, {String reason = ''}) =>
      _api.post('${_base(projectId)}/orders/$orderId/refund/',
          body: {'reason': reason});

  Future<Map<String, dynamic>> sales(int projectId) async {
    final data = await _api.get('${_base(projectId)}/sales/');
    return (data as Map).cast<String, dynamic>();
  }

  Future<List<Discount>> discounts(int projectId) async {
    final data = await _api.get('${_base(projectId)}/discounts/');
    return (data as List)
        .map((d) => Discount.fromJson(d as Map<String, dynamic>))
        .toList();
  }

  Future<void> createDiscount(int projectId,
      {required String code, int percentOff = 0}) {
    return _api.post('${_base(projectId)}/discounts/', body: {
      'code': code,
      'kind': 'percent',
      'percent_off': percentOff,
    });
  }

  // --- Invoicing ---
  Future<Map<String, dynamic>> orderInvoice(int projectId, int orderId) async {
    final data = await _api.get('${_base(projectId)}/orders/$orderId/invoice/');
    return (data as Map).cast<String, dynamic>();
  }

  // --- Tax ---
  Future<Map<String, dynamic>> tax(int projectId) async {
    final data = await _api.get('${_base(projectId)}/tax/');
    return (data as Map).cast<String, dynamic>();
  }

  Future<void> setTax(int projectId, {required String name, required num percent}) =>
      _api.post('${_base(projectId)}/tax/', body: {'name': name, 'percent': percent});

  // --- Subscriptions ---
  Future<List<SubscriptionPlan>> plans(int projectId) async {
    final data = await _api.get('${_base(projectId)}/plans/');
    return (data as List)
        .map((p) => SubscriptionPlan.fromJson(p as Map<String, dynamic>))
        .toList();
  }

  Future<void> createPlan(int projectId,
      {required String name, required int amountCents, String interval = 'monthly'}) {
    return _api.post('${_base(projectId)}/plans/', body: {
      'name': name,
      'amount_cents': amountCents,
      'interval': interval,
    });
  }

  Future<SubscriptionsView> subscriptions(int projectId) async {
    final data = await _api.get('${_base(projectId)}/subscriptions/');
    return SubscriptionsView.fromJson((data as Map).cast<String, dynamic>());
  }

  Future<void> subscribe(int projectId,
      {required int planId, String customerName = '', String customerEmail = ''}) {
    return _api.post('${_base(projectId)}/subscriptions/', body: {
      'plan_id': planId,
      'customer_name': customerName,
      'customer_email': customerEmail,
    });
  }

  Future<void> cancelSubscription(int projectId, int subscriptionId) =>
      _api.post('${_base(projectId)}/subscriptions/$subscriptionId/cancel/');

  Future<int> renewSubscriptions(int projectId) async {
    final data = await _api.post('${_base(projectId)}/subscriptions/renew/');
    return ((data as Map)['opened'] ?? 0) as int;
  }

  // --- Multi-currency ---
  Future<Map<String, dynamic>> currency(int projectId) async {
    final data = await _api.get('${_base(projectId)}/currency/');
    return (data as Map).cast<String, dynamic>();
  }

  Future<void> setRate(int projectId,
      {required String base, required String quote, required String rate}) {
    return _api.post('${_base(projectId)}/currency/',
        body: {'base': base, 'quote': quote, 'rate': rate});
  }

  Future<Map<String, dynamic>> currencyRevenue(int projectId, {String? base}) async {
    final data = await _api.get('${_base(projectId)}/currency/revenue/',
        query: base == null ? null : {'base': base});
    return (data as Map).cast<String, dynamic>();
  }

  // --- Email campaigns (under /projects/<id>/campaigns/, not /commerce) ---
  Future<CampaignsView> campaigns(int projectId) async {
    final data = await _api.get('projects/$projectId/campaigns/');
    return CampaignsView.fromJson((data as Map).cast<String, dynamic>());
  }

  Future<void> createCampaign(int projectId,
      {required String subject, required String body, String audienceSource = 'all'}) {
    return _api.post('projects/$projectId/campaigns/', body: {
      'subject': subject,
      'body': body,
      'audience_source': audienceSource,
    });
  }

  Future<void> sendCampaign(int projectId, int campaignId) =>
      _api.post('projects/$projectId/campaigns/$campaignId/send/');
}

class Discount {
  final int id;
  final String code;
  final String kind;
  final int percentOff;
  final int amountOffCents;

  const Discount({
    required this.id,
    required this.code,
    required this.kind,
    required this.percentOff,
    required this.amountOffCents,
  });

  factory Discount.fromJson(Map<String, dynamic> j) => Discount(
        id: j['id'] as int,
        code: (j['code'] ?? '') as String,
        kind: (j['kind'] ?? '') as String,
        percentOff: (j['percent_off'] ?? 0) as int,
        amountOffCents: (j['amount_off_cents'] ?? 0) as int,
      );
}

class SubscriptionPlan {
  final int id;
  final String name;
  final String amountDisplay;
  final String interval;
  final bool active;

  const SubscriptionPlan({
    required this.id,
    required this.name,
    required this.amountDisplay,
    required this.interval,
    required this.active,
  });

  factory SubscriptionPlan.fromJson(Map<String, dynamic> j) => SubscriptionPlan(
        id: j['id'] as int,
        name: (j['name'] ?? '') as String,
        amountDisplay: (j['amount_display'] ?? '') as String,
        interval: (j['interval'] ?? 'monthly') as String,
        active: (j['active'] ?? true) as bool,
      );
}

class Subscription {
  final int id;
  final String plan;
  final String status;
  final String customerEmail;
  final String amountDisplay;
  final String interval;
  final int renewals;

  const Subscription({
    required this.id,
    required this.plan,
    required this.status,
    required this.customerEmail,
    required this.amountDisplay,
    required this.interval,
    required this.renewals,
  });

  factory Subscription.fromJson(Map<String, dynamic> j) => Subscription(
        id: j['id'] as int,
        plan: (j['plan'] ?? '') as String,
        status: (j['status'] ?? '') as String,
        customerEmail: (j['customer_email'] ?? '') as String,
        amountDisplay: (j['amount_display'] ?? '') as String,
        interval: (j['interval'] ?? '') as String,
        renewals: (j['renewals'] ?? 0) as int,
      );
}

class SubscriptionsView {
  final Map<String, dynamic> overview;
  final List<Subscription> subscriptions;
  const SubscriptionsView({required this.overview, required this.subscriptions});

  factory SubscriptionsView.fromJson(Map<String, dynamic> j) => SubscriptionsView(
        overview: ((j['overview'] as Map?) ?? {}).cast<String, dynamic>(),
        subscriptions: ((j['subscriptions'] as List?) ?? [])
            .map((s) => Subscription.fromJson(s as Map<String, dynamic>))
            .toList(),
      );
}

class Campaign {
  final int id;
  final String subject;
  final String status;
  final int total;
  final int sentCount;
  final int failedCount;

  const Campaign({
    required this.id,
    required this.subject,
    required this.status,
    required this.total,
    required this.sentCount,
    required this.failedCount,
  });

  factory Campaign.fromJson(Map<String, dynamic> j) => Campaign(
        id: j['id'] as int,
        subject: (j['subject'] ?? '') as String,
        status: (j['status'] ?? '') as String,
        total: (j['total'] ?? 0) as int,
        sentCount: (j['sent_count'] ?? 0) as int,
        failedCount: (j['failed_count'] ?? 0) as int,
      );
}

class CampaignsView {
  final int audienceSize;
  final List<Campaign> campaigns;
  const CampaignsView({required this.audienceSize, required this.campaigns});

  factory CampaignsView.fromJson(Map<String, dynamic> j) => CampaignsView(
        audienceSize: (j['audience_size'] ?? 0) as int,
        campaigns: ((j['campaigns'] as List?) ?? [])
            .map((c) => Campaign.fromJson(c as Map<String, dynamic>))
            .toList(),
      );
}

final commerceRepositoryProvider = Provider<CommerceRepository>(
  (ref) => CommerceRepository(ref.watch(apiClientProvider)),
);

final productsProvider =
    FutureProvider.family<List<Product>, int>((ref, projectId) {
  return ref.watch(commerceRepositoryProvider).products(projectId);
});

final ordersProvider =
    FutureProvider.family<List<Order>, int>((ref, projectId) {
  final status = ref.watch(ordersFilterProvider(projectId));
  return ref
      .watch(commerceRepositoryProvider)
      .orders(projectId, status: status.isEmpty ? null : status);
});

final salesProvider =
    FutureProvider.family<Map<String, dynamic>, int>((ref, projectId) {
  return ref.watch(commerceRepositoryProvider).sales(projectId);
});

/// Orders filtered by status; pass ('', projectId) for all.
final ordersFilterProvider = StateProvider.family<String, int>((ref, _) => '');

final discountsProvider =
    FutureProvider.family<List<Discount>, int>((ref, projectId) {
  return ref.watch(commerceRepositoryProvider).discounts(projectId);
});

final plansProvider =
    FutureProvider.family<List<SubscriptionPlan>, int>((ref, projectId) {
  return ref.watch(commerceRepositoryProvider).plans(projectId);
});

final subscriptionsProvider =
    FutureProvider.family<SubscriptionsView, int>((ref, projectId) {
  return ref.watch(commerceRepositoryProvider).subscriptions(projectId);
});

final currencyProvider =
    FutureProvider.family<Map<String, dynamic>, int>((ref, projectId) {
  return ref.watch(commerceRepositoryProvider).currency(projectId);
});

final campaignsProvider =
    FutureProvider.family<CampaignsView, int>((ref, projectId) {
  return ref.watch(commerceRepositoryProvider).campaigns(projectId);
});

final taxProvider =
    FutureProvider.family<Map<String, dynamic>, int>((ref, projectId) {
  return ref.watch(commerceRepositoryProvider).tax(projectId);
});
