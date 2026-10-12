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
