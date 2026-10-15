import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../config/app_config.dart';
import '../../config/brand.dart';
import '../../core/providers.dart';

/// Second step of sign-in when the account has MFA enabled: enter a 6-digit code
/// from the authenticator app (or a recovery code). On success the auth state
/// flips to authenticated and the router moves the user into the app.
class MfaChallengeScreen extends ConsumerStatefulWidget {
  const MfaChallengeScreen({super.key});

  @override
  ConsumerState<MfaChallengeScreen> createState() => _MfaChallengeScreenState();
}

class _MfaChallengeScreenState extends ConsumerState<MfaChallengeScreen> {
  final _code = TextEditingController();
  final _formKey = GlobalKey<FormState>();

  @override
  void dispose() {
    _code.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    FocusScope.of(context).unfocus();
    final ok = await ref.read(authControllerProvider.notifier).verifyMfa(_code.text);
    // On success the router redirect carries us into the app; nothing to do.
    if (!ok && mounted) _code.clear();
  }

  void _cancel() {
    ref.read(authControllerProvider.notifier).cancelMfa();
    context.pop();
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(authControllerProvider);
    return Scaffold(
      body: BrandBackground(
        child: SafeArea(
          child: Center(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(24),
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 420),
                child: Form(
                  key: _formKey,
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      const Center(
                          child: BrandLogo(name: AppConfig.appName, size: 44)),
                      const SizedBox(height: 10),
                      Text('Two-step verification',
                          style: Theme.of(context).textTheme.titleLarge,
                          textAlign: TextAlign.center),
                      const SizedBox(height: 4),
                      Text(
                        'Enter the 6-digit code from your authenticator app. '
                        'You can also use a recovery code.',
                        style: Theme.of(context).textTheme.bodyMedium,
                        textAlign: TextAlign.center,
                      ),
                      const SizedBox(height: 24),
                      TextFormField(
                        controller: _code,
                        autofocus: true,
                        keyboardType: TextInputType.text,
                        autofillHints: const [AutofillHints.oneTimeCode],
                        onFieldSubmitted: (_) => _submit(),
                        decoration:
                            const InputDecoration(labelText: 'Verification code'),
                        validator: (v) =>
                            (v == null || v.trim().isEmpty) ? 'Enter the code' : null,
                      ),
                      if (state.error != null) ...[
                        const SizedBox(height: 12),
                        Text(state.error!,
                            style: TextStyle(
                                color: Theme.of(context).colorScheme.error)),
                      ],
                      const SizedBox(height: 20),
                      GradientButton(
                        onPressed: state.busy ? null : _submit,
                        child: state.busy
                            ? const SizedBox(
                                height: 20,
                                width: 20,
                                child: CircularProgressIndicator(
                                    strokeWidth: 2, color: Colors.white),
                              )
                            : const Text('Verify'),
                      ),
                      const SizedBox(height: 8),
                      TextButton(
                        onPressed: state.busy ? null : _cancel,
                        child: const Text('Back to sign in'),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
