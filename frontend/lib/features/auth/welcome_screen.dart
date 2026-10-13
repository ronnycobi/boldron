import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../config/app_config.dart';
import '../../config/brand.dart';

/// First screen a signed-out user sees: a short welcome with a primary
/// "Get started" (sign up) and a secondary "I already have an account"
/// (sign in). Branding comes from AppConfig (spec §43).
class WelcomeScreen extends StatelessWidget {
  const WelcomeScreen({super.key});

  static const _points = [
    (icon: Icons.chat_bubble_outline, title: 'Describe it in plain words',
     body: 'Tell us what you want to build — no tech setup required.'),
    (icon: Icons.auto_awesome_outlined, title: 'Watch it come together',
     body: 'Follow the build in real time, step by step.'),
    (icon: Icons.rocket_launch_outlined, title: 'Ship and manage anywhere',
     body: 'Preview, deploy and run your software from your phone.'),
  ];

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      body: BrandBackground(
        child: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(24, 32, 24, 24),
          child: Column(
            children: [
              const Spacer(flex: 2),
              BrandText(
                AppConfig.appName,
                style: theme.textTheme.displaySmall,
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 8),
              Text(
                AppConfig.tagline,
                style: theme.textTheme.titleMedium
                    ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
                textAlign: TextAlign.center,
              ),
              const Spacer(flex: 2),
              for (final p in _points)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 10),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      CircleAvatar(
                        radius: 22,
                        backgroundColor: theme.colorScheme.primaryContainer,
                        child: Icon(p.icon,
                            color: theme.colorScheme.onPrimaryContainer),
                      ),
                      const SizedBox(width: 14),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(p.title,
                                style: theme.textTheme.titleSmall
                                    ?.copyWith(fontWeight: FontWeight.w600)),
                            const SizedBox(height: 2),
                            Text(p.body, style: theme.textTheme.bodyMedium),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              const Spacer(flex: 3),
              GradientButton(
                onPressed: () => context.push('/register'),
                child: const Text('Get started'),
              ),
              const SizedBox(height: 8),
              TextButton(
                onPressed: () => context.push('/login'),
                child: const Text('I already have an account'),
              ),
            ],
          ),
        ),
      ),
      ),
    );
  }
}
