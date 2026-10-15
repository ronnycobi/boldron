import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../config/brand.dart';
import '../../core/api_exception.dart';
import 'settings_repository.dart';

/// Enrol a TOTP second factor: fetch a secret, let the user add it to their
/// authenticator app (manual key — no QR dependency on mobile), verify a live
/// code, then show the one-time recovery codes.
class MfaSetupScreen extends ConsumerStatefulWidget {
  const MfaSetupScreen({super.key});

  @override
  ConsumerState<MfaSetupScreen> createState() => _MfaSetupScreenState();
}

class _MfaSetupScreenState extends ConsumerState<MfaSetupScreen> {
  final _code = TextEditingController();
  String? _secret;
  List<String>? _recoveryCodes;
  bool _loading = true;
  bool _busy = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _enroll();
  }

  @override
  void dispose() {
    _code.dispose();
    super.dispose();
  }

  Future<void> _enroll() async {
    try {
      final data = await ref.read(settingsRepositoryProvider).mfaEnroll();
      setState(() {
        _secret = '${data['secret']}';
        _loading = false;
      });
    } on ApiException catch (e) {
      setState(() {
        _error = e.message;
        _loading = false;
      });
    }
  }

  Future<void> _confirm() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final codes = await ref.read(settingsRepositoryProvider).mfaConfirm(_code.text);
      ref.invalidate(securityProvider);
      setState(() {
        _recoveryCodes = codes;
        _busy = false;
      });
    } on ApiException catch (e) {
      setState(() {
        _error = e.firstFieldError ?? e.message;
        _busy = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
          title: Text(_recoveryCodes == null
              ? 'Set up two-factor'
              : 'Recovery codes')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _recoveryCodes != null
              ? _RecoveryCodes(codes: _recoveryCodes!)
              : _setupBody(context),
    );
  }

  Widget _setupBody(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text('1. Add this key to your authenticator app',
            style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 4),
        Text('Google Authenticator, 1Password, Authy…',
            style: Theme.of(context).textTheme.bodySmall),
        const SizedBox(height: 10),
        if (_secret != null)
          PanelCard(
            child: Row(
              children: [
                Expanded(
                  child: SelectableText(
                    _secret!,
                    style: const TextStyle(
                        fontFamily: 'monospace', letterSpacing: 2, fontSize: 15),
                  ),
                ),
                IconButton(
                  icon: const Icon(Icons.copy, size: 18),
                  tooltip: 'Copy key',
                  onPressed: () {
                    Clipboard.setData(ClipboardData(text: _secret!));
                    ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(content: Text('Key copied.')));
                  },
                ),
              ],
            ),
          ),
        const SizedBox(height: 20),
        Text('2. Enter the 6-digit code',
            style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 10),
        TextField(
          controller: _code,
          keyboardType: TextInputType.number,
          autofocus: true,
          decoration: const InputDecoration(labelText: 'Verification code'),
          onSubmitted: (_) => _confirm(),
        ),
        if (_error != null) ...[
          const SizedBox(height: 10),
          Text(_error!,
              style: TextStyle(color: Theme.of(context).colorScheme.error)),
        ],
        const SizedBox(height: 18),
        FilledButton(
          onPressed: _busy ? null : _confirm,
          child: Text(_busy ? 'Verifying…' : 'Verify & enable'),
        ),
      ],
    );
  }
}

class _RecoveryCodes extends StatelessWidget {
  final List<String> codes;
  const _RecoveryCodes({required this.codes});

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text('Two-factor is on',
            style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 6),
        Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: Theme.of(context).colorScheme.tertiaryContainer,
            borderRadius: BorderRadius.circular(12),
          ),
          child: Text(
            'Save these recovery codes somewhere safe. Each works once if you '
            'lose your authenticator. This is the only time they are shown.',
            style: TextStyle(
                color: Theme.of(context).colorScheme.onTertiaryContainer,
                fontSize: 13),
          ),
        ),
        const SizedBox(height: 14),
        PanelCard(
          child: Column(
            children: [
              for (final c in codes)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 5),
                  child: SelectableText(
                    c,
                    style: const TextStyle(
                        fontFamily: 'monospace', letterSpacing: 2, fontSize: 15),
                  ),
                ),
            ],
          ),
        ),
        const SizedBox(height: 10),
        OutlinedButton.icon(
          icon: const Icon(Icons.copy, size: 18),
          label: const Text('Copy all codes'),
          onPressed: () {
            Clipboard.setData(ClipboardData(text: codes.join('\n')));
            ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(content: Text('Recovery codes copied.')));
          },
        ),
        const SizedBox(height: 8),
        FilledButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Done'),
        ),
      ],
    );
  }
}
