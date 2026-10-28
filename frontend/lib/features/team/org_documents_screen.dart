import 'package:flutter/material.dart';

/// Project documentation export. The archive (README, API spec, data model,
/// generated source) is a real .zip built on demand; downloading a file is a
/// web affordance, so on mobile this points to the web app rather than faking a
/// download that the mobile sandbox can't deliver.
class OrgDocumentsScreen extends StatelessWidget {
  const OrgDocumentsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Documents')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Project documentation export',
                      style: Theme.of(context).textTheme.titleMedium),
                  const SizedBox(height: 8),
                  Text(
                    'Each project can export a real archive — a README, API spec, '
                    'data model and the generated source. Because it is a file '
                    'download, run the export from the web app under '
                    'Settings → Documents.',
                    style: Theme.of(context).textTheme.bodyMedium,
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
