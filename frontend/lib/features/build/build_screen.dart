import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../config/app_config.dart';
import '../../config/brand.dart';
import '../../config/theme.dart';
import '../../core/api_exception.dart';
import '../../core/providers.dart';
import '../projects/projects_repository.dart';

/// The most important interaction (spec §7): "What do you want to build?".
/// A plain-language brief with starters — no configuration required.
class BuildScreen extends ConsumerStatefulWidget {
  const BuildScreen({super.key});

  @override
  ConsumerState<BuildScreen> createState() => _BuildScreenState();
}

class _BuildScreenState extends ConsumerState<BuildScreen> {
  final _brief = TextEditingController();
  bool _busy = false;

  static const _starters = <String, String>{
    'CRM': 'Build a CRM with contacts, companies, leads, deals and a sales dashboard.',
    'Website': 'Build a professional website for my business with home, services and contact pages.',
    'E-commerce': 'Build an online store with a product catalog, cart, checkout and orders.',
    'SaaS': 'Build a SaaS platform where teams sign up, manage members and pay a subscription.',
    'Portal': 'Build a customer portal where clients log in, submit requests and track status.',
    'Internal tool': 'Build an internal tool for my team to manage tasks, approvals and reports.',
  };

  @override
  void dispose() {
    _brief.dispose();
    super.dispose();
  }

  Future<void> _build() async {
    final brief = _brief.text.trim();
    if (brief.isEmpty) return;
    FocusScope.of(context).unfocus();
    setState(() => _busy = true);
    try {
      // Build into the active org only when the user can manage it; otherwise
      // let the backend choose a manageable org.
      final activeId = ref.read(activeOrgProvider);
      final orgs = ref.read(authControllerProvider).user?.organizations ?? [];
      int? manageableActive;
      for (final o in orgs) {
        if (o.id == activeId && o.canManage) {
          manageableActive = o.id;
          break;
        }
      }
      await ref
          .read(projectsRepositoryProvider)
          .build(brief, organization: manageableActive);
      ref.invalidate(projectsProvider);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('${AppConfig.appName} is building your app…'),
        ),
      );
      context.go('/projects');
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(e.message)));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final user = ref.watch(authControllerProvider).user;
    final unverified = user != null && !user.emailVerified;
    return Scaffold(
      appBar: AppBar(title: const Text(AppConfig.appName)),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(20),
          children: [
            if (unverified) const _VerifyBanner(),
            const SizedBox(height: 8),
            Text(
              'What do you want to build?',
              style: Theme.of(context).textTheme.headlineSmall,
            ),
            const SizedBox(height: 6),
            Text(
              'Describe it in your own words. ${AppConfig.appName} turns your idea into working software.',
              style: Theme.of(context).textTheme.bodyMedium,
            ),
            const SizedBox(height: 16),
            // The hero prompt box — rounded like the web's big "describe it" field.
            Container(
              decoration: BoxDecoration(
                color: AppTheme.panel2,
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: AppTheme.line2),
              ),
              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
              child: TextField(
                controller: _brief,
                minLines: 5,
                maxLines: 9,
                textInputAction: TextInputAction.newline,
                style: const TextStyle(fontSize: 15, height: 1.5),
                decoration: const InputDecoration(
                  filled: false,
                  border: InputBorder.none,
                  enabledBorder: InputBorder.none,
                  focusedBorder: InputBorder.none,
                  contentPadding: EdgeInsets.all(14),
                  hintText:
                      'e.g. Build a booking system for my salon with reminders…',
                ),
              ),
            ),
            const SizedBox(height: 14),
            GradientButton(
              onPressed: _busy ? null : _build,
              child: _busy
                  ? const Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        SizedBox(
                          height: 18,
                          width: 18,
                          child: CircularProgressIndicator(
                              strokeWidth: 2, color: Colors.white),
                        ),
                        SizedBox(width: 10),
                        Text('Starting…'),
                      ],
                    )
                  : const Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.arrow_forward),
                        SizedBox(width: 8),
                        Text('Build'),
                      ],
                    ),
            ),
            const SizedBox(height: 10),
            Center(
              child: TextButton.icon(
                onPressed: () {
                  final brief = _brief.text.trim();
                  context.push(
                    '/mobile-plan${brief.isEmpty ? '' : '?brief=${Uri.encodeQueryComponent(brief)}'}',
                  );
                },
                icon: const Icon(Icons.phone_iphone, size: 18),
                label: const Text('Plan a mobile app (iOS · Android · Huawei)'),
              ),
            ),
            const SizedBox(height: 14),
            Text('Start with an example',
                style: Theme.of(context).textTheme.labelLarge),
            const SizedBox(height: 10),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                for (final entry in _starters.entries)
                  ActionChip(
                    label: Text(entry.key),
                    onPressed: () => setState(() => _brief.text = entry.value),
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _VerifyBanner extends ConsumerWidget {
  const _VerifyBanner();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final scheme = Theme.of(context).colorScheme;
    return Card(
      color: scheme.tertiaryContainer,
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Row(
          children: [
            Icon(Icons.mark_email_unread_outlined,
                color: scheme.onTertiaryContainer),
            const SizedBox(width: 12),
            Expanded(
              child: Text(
                'Verify your email to start building. Check your inbox.',
                style: TextStyle(color: scheme.onTertiaryContainer),
              ),
            ),
            TextButton(
              onPressed: () async {
                await ref
                    .read(authRepositoryProvider)
                    .resendVerification();
                if (context.mounted) {
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(content: Text('Verification email sent.')),
                  );
                }
              },
              child: const Text('Resend'),
            ),
          ],
        ),
      ),
    );
  }
}
