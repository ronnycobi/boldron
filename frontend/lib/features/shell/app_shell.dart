import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

/// The signed-in frame: an adaptive bottom navigation over the four primary
/// areas (spec §3). Each branch keeps its own navigation state. On wide screens
/// (tablets) a NavigationRail is used instead (spec §38).
class AppShell extends StatelessWidget {
  final StatefulNavigationShell navShell;
  const AppShell({super.key, required this.navShell});

  static const _destinations = [
    (icon: Icons.auto_awesome_outlined, selected: Icons.auto_awesome, label: 'Build'),
    (icon: Icons.folder_outlined, selected: Icons.folder, label: 'Projects'),
    (icon: Icons.notifications_outlined, selected: Icons.notifications, label: 'Activity'),
    (icon: Icons.person_outline, selected: Icons.person, label: 'Account'),
  ];

  void _go(int index) => navShell.goBranch(
        index,
        initialLocation: index == navShell.currentIndex,
      );

  @override
  Widget build(BuildContext context) {
    final wide = MediaQuery.sizeOf(context).width >= 760;
    if (wide) {
      return Scaffold(
        body: Row(
          children: [
            NavigationRail(
              selectedIndex: navShell.currentIndex,
              onDestinationSelected: _go,
              labelType: NavigationRailLabelType.all,
              destinations: [
                for (final d in _destinations)
                  NavigationRailDestination(
                    icon: Icon(d.icon),
                    selectedIcon: Icon(d.selected),
                    label: Text(d.label),
                  ),
              ],
            ),
            const VerticalDivider(width: 1),
            Expanded(child: navShell),
          ],
        ),
      );
    }
    return Scaffold(
      body: navShell,
      bottomNavigationBar: NavigationBar(
        selectedIndex: navShell.currentIndex,
        onDestinationSelected: _go,
        destinations: [
          for (final d in _destinations)
            NavigationDestination(
              icon: Icon(d.icon),
              selectedIcon: Icon(d.selected),
              label: d.label,
            ),
        ],
      ),
    );
  }
}
