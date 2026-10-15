import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_exception.dart';
import '../../core/providers.dart';
import 'settings_repository.dart';

/// Preferences (language, timezone) + the integrations the platform supports.
class PreferencesScreen extends ConsumerStatefulWidget {
  const PreferencesScreen({super.key});

  @override
  ConsumerState<PreferencesScreen> createState() => _PreferencesScreenState();
}

class _PreferencesScreenState extends ConsumerState<PreferencesScreen> {
  static const _languages = {
    '': 'Default', 'en-us': 'English (US)', 'en-gb': 'English (UK)',
    'es': 'Español', 'fr': 'Français', 'de': 'Deutsch', 'pt': 'Português',
    'af': 'Afrikaans', 'ar': 'العربية',
  };
  static const _timezones = [
    '', 'UTC', 'Africa/Johannesburg', 'Europe/London', 'America/New_York',
    'America/Los_Angeles', 'Asia/Dubai', 'Asia/Singapore', 'Australia/Sydney',
  ];

  String _language = '';
  String _timezone = '';
  bool _saving = false;

  Future<void> _save() async {
    setState(() => _saving = true);
    try {
      await ref.read(settingsRepositoryProvider).updateAccount({
        'language': _language,
        'timezone': _timezone,
      });
      await ref.read(authControllerProvider.notifier).refreshUser();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Preferences saved.')));
      }
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(e.message)));
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final integrations = ref.watch(integrationsProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Preferences')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text('Preferences', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          DropdownButtonFormField<String>(
            value: _language,
            decoration: const InputDecoration(labelText: 'Language'),
            items: [
              for (final e in _languages.entries)
                DropdownMenuItem(value: e.key, child: Text(e.value)),
            ],
            onChanged: (v) => setState(() => _language = v ?? ''),
          ),
          const SizedBox(height: 10),
          DropdownButtonFormField<String>(
            value: _timezone,
            decoration: const InputDecoration(labelText: 'Timezone'),
            items: [
              for (final tz in _timezones)
                DropdownMenuItem(
                    value: tz, child: Text(tz.isEmpty ? 'Default' : tz)),
            ],
            onChanged: (v) => setState(() => _timezone = v ?? ''),
          ),
          const SizedBox(height: 12),
          FilledButton(
            onPressed: _saving ? null : _save,
            child: Text(_saving ? 'Saving…' : 'Save preferences'),
          ),
          const SizedBox(height: 24),
          Text('Integrations', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          integrations.when(
            loading: () => const Center(child: CircularProgressIndicator()),
            error: (e, _) => Text(e.toString()),
            data: (items) => Column(
              children: [
                for (final it in items)
                  ListTile(
                    leading: Icon(
                      (it['configured'] ?? false) as bool
                          ? Icons.check_circle
                          : Icons.circle_outlined,
                      color: (it['configured'] ?? false) as bool
                          ? Colors.green
                          : null,
                    ),
                    title: Text('${it['provider']}'),
                    subtitle: Text((it['configured'] ?? false) as bool
                        ? 'Connected'
                        : 'Not connected'),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
