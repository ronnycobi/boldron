import 'package:boldron_app/features/auth/auth_models.dart';
import 'package:boldron_app/features/changes/changes_repository.dart';
import 'package:boldron_app/features/commerce/commerce_repository.dart';
import 'package:boldron_app/features/deployments/deployments_repository.dart';
import 'package:boldron_app/features/projects/project_models.dart';
import 'package:boldron_app/features/support/support_repository.dart';
import 'package:boldron_app/features/website/website_repository.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('AuthUser parses user + organizations', () {
    final u = AuthUser.fromJson({
      'id': 1,
      'email': 'a@b.com',
      'full_name': 'Ada Lovelace',
      'display_name': 'Ada',
      'initials': 'AL',
      'avatar_url': '/media/a.jpg',
      'email_verified': true,
      'organizations': [
        {'id': 7, 'name': 'Acme', 'slug': 'acme', 'role': 'owner'},
      ],
    });
    expect(u.email, 'a@b.com');
    expect(u.emailVerified, isTrue);
    expect(u.organizations.single.canManage, isTrue); // owner
  });

  test('AuthUser tolerates missing optional fields', () {
    final u = AuthUser.fromJson({'id': 2, 'email': 'x@y.com'});
    expect(u.fullName, '');
    expect(u.organizations, isEmpty);
    expect(u.emailVerified, isFalse);
  });

  test('Project and BuildStatus parse', () {
    final p = Project.fromJson({
      'id': 3,
      'name': 'Store',
      'slug': 'store',
      'description': 'd',
      'status': 'active',
      'mode': 'build',
      'organization': 7,
      'organization_slug': 'acme',
    });
    expect(p.name, 'Store');

    final s = BuildStatus.fromJson({
      'state': 'Building',
      'progress': 50,
      'demo_mode': true,
      'steps': [
        {'key': 'backend', 'status': 'completed', 'detail': 'done'},
      ],
    });
    expect(s.state, 'Building');
    expect(s.demoMode, isTrue);
    expect(s.steps.single.key, 'backend');
  });

  test('ChangeRequest parses plan/estimate maps', () {
    final c = ChangeRequest.fromJson({
      'id': 1,
      'project': 3,
      'description': 'Add payments',
      'status': 'planned',
      'status_display': 'Planned',
      'plan': {'summary': 'Adds PayFast'},
      'estimate': {
        'credits': [10, 20]
      },
      'requires_approval': true,
      'approved': false,
      'risk': 'low',
      'can_rollback': false,
    });
    expect(c.plan['summary'], 'Adds PayFast');
    expect(c.requiresApproval, isTrue);
  });

  test('Product and Order parse (commerce)', () {
    final p = Product.fromJson({
      'id': 1,
      'name': 'Candle',
      'price_display': 'USD 15.00',
      'price_cents': 1500,
      'currency': 'USD',
      'active': true,
      'track_inventory': true,
      'stock': 3,
      'in_stock': true,
    });
    expect(p.priceCents, 1500);
    expect(p.stock, 3);

    final o = Order.fromJson({
      'id': 9,
      'reference': 'ORD-1',
      'status': 'paid',
      'total_display': 'USD 30.00',
      'customer_name': 'Jo',
      'created_at': '2026-10-12T00:00:00Z',
      'items': [
        {'name': 'Candle', 'quantity': 2, 'line_total_cents': 3000},
      ],
    });
    expect(o.status, 'paid');
    expect(o.items.single.quantity, 2);
  });

  test('EnvironmentSummary parses with and without latest', () {
    final withDep = EnvironmentSummary.fromJson({
      'environment': 'staging',
      'label': 'Staging',
      'latest': {
        'id': 5,
        'environment': 'staging',
        'provider': 'local',
        'status': 'succeeded',
        'url': 'http://x',
        'log': 'ok',
        'approved': true,
        'created_at': '2026-10-12T00:00:00Z',
      },
    });
    expect(withDep.latest, isNotNull);
    expect(withDep.latest!.status, 'succeeded');

    final none = EnvironmentSummary.fromJson(
        {'environment': 'development', 'label': 'Development', 'latest': null});
    expect(none.latest, isNull);
  });

  test('WebsiteInfo parses current version + domains', () {
    final w = WebsiteInfo.fromJson({
      'subdomain': 'site-x',
      'site_type': 'business',
      'current_version': {
        'id': 1,
        'version': 'v1.0.0',
        'state': 'published',
        'url': 'http://x',
        'is_current': true,
      },
      'url': 'http://x',
      'domains': [
        {
          'id': 2,
          'hostname': 'shop.example.com',
          'verification_status': 'pending',
          'ssl_status': 'none',
          'is_live': false,
        },
      ],
    });
    expect(w.current!.version, 'v1.0.0');
    expect(w.domains.single.isLive, isFalse);
  });

  test('Ticket parses thread messages', () {
    final t = Ticket.fromJson({
      'id': 1,
      'number': 'TKT-1',
      'subject': 'Help',
      'status': 'open',
      'category': 'question',
      'priority': 'normal',
      'organization': 7,
      'messages': [
        {
          'id': 1,
          'body': 'hi',
          'author': 'Ada',
          'from_staff': false,
          'created_at': '2026-10-12T00:00:00Z',
        },
      ],
    });
    expect(t.number, 'TKT-1');
    expect(t.messages.single.fromStaff, isFalse);
  });
}
