import 'package:flutter/material.dart';

import 'theme.dart';

/// The brand wordmark: text painted with the blue→purple gradient, matching the
/// gradient-clipped logo on the web.
class BrandText extends StatelessWidget {
  final String text;
  final TextStyle? style;
  final TextAlign? textAlign;
  const BrandText(this.text, {super.key, this.style, this.textAlign});

  @override
  Widget build(BuildContext context) {
    return ShaderMask(
      shaderCallback: (bounds) => AppTheme.brandGradient.createShader(
        Rect.fromLTWH(0, 0, bounds.width, bounds.height),
      ),
      blendMode: BlendMode.srcIn,
      child: Text(
        text,
        textAlign: textAlign,
        style: (style ?? const TextStyle()).copyWith(
          color: Colors.white,
          fontWeight: FontWeight.w800,
        ),
      ),
    );
  }
}

/// The brand logo: a gradient rounded-square mark + the gradient wordmark,
/// mirroring the web header logo.
class BrandLogo extends StatelessWidget {
  final String name;
  final double size;
  const BrandLogo({super.key, required this.name, this.size = 34});

  @override
  Widget build(BuildContext context) {
    final mark = name.isNotEmpty ? name[0].toUpperCase() : 'B';
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: size,
          height: size,
          decoration: BoxDecoration(
            gradient: AppTheme.brandGradient,
            borderRadius: BorderRadius.circular(size * 0.28),
          ),
          alignment: Alignment.center,
          child: Text(
            mark,
            style: TextStyle(
              color: Colors.white,
              fontWeight: FontWeight.w900,
              fontSize: size * 0.56,
            ),
          ),
        ),
        SizedBox(width: size * 0.32),
        BrandText(
          name,
          style: TextStyle(fontSize: size * 0.72, letterSpacing: -0.5),
        ),
      ],
    );
  }
}

/// A content panel matching the web card: a subtle top→bottom gradient with a
/// hairline border and rounded corners.
class PanelCard extends StatelessWidget {
  final Widget child;
  final EdgeInsetsGeometry padding;
  final VoidCallback? onTap;
  const PanelCard({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(16),
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final card = DecoratedBox(
      decoration: BoxDecoration(
        color: scheme.surface,
        border: Border.all(color: scheme.outlineVariant),
        borderRadius: BorderRadius.circular(14),
      ),
      child: Padding(padding: padding, child: child),
    );
    if (onTap == null) return card;
    return Material(
      color: Colors.transparent,
      child: InkWell(
        borderRadius: BorderRadius.circular(14),
        onTap: onTap,
        child: card,
      ),
    );
  }
}

/// A status pill coloured like the web badges (green/blue/amber/red/grey).
class StatusBadge extends StatelessWidget {
  final String status;
  const StatusBadge(this.status, {super.key});

  static (Color, Color) _colors(String s) {
    s = s.toLowerCase();
    const okbg = Color(0x2434D399), failbg = Color(0x24F87171);
    const runbg = Color(0x2460A5FA), waitbg = Color(0x24FBBF24);
    const idle = Color(0xFF8A93AD), idlebg = Color(0x1F8A93AD);
    if (['completed', 'succeeded', 'deployed', 'done', 'active', 'paid', 'published']
        .contains(s)) {
      return (AppTheme.ok, okbg);
    }
    if (['failed', 'timeout', 'error', 'cancelled', 'refunded'].contains(s)) {
      return (AppTheme.fail, failbg);
    }
    if (['running', 'planning', 'deploying', 'building', 'implementing', 'analyzing']
        .contains(s)) {
      return (AppTheme.run, runbg);
    }
    if (s.startsWith('waiting') ||
        ['planned', 'awaiting_approval', 'pending', 'awaiting payment', 'draft']
            .contains(s)) {
      return (AppTheme.wait, waitbg);
    }
    return (idle, idlebg);
  }

  @override
  Widget build(BuildContext context) {
    final (fg, bg) = _colors(status);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(99),
      ),
      child: Text(
        status.isEmpty ? '—' : status,
        style: TextStyle(color: fg, fontSize: 11.5, fontWeight: FontWeight.w700),
      ),
    );
  }
}

/// Primary call-to-action with the brand gradient (the web's gradient buttons).
class GradientButton extends StatelessWidget {
  final VoidCallback? onPressed;
  final Widget child;
  final double height;
  const GradientButton({
    super.key,
    required this.onPressed,
    required this.child,
    this.height = 50,
  });

  @override
  Widget build(BuildContext context) {
    final enabled = onPressed != null;
    return Opacity(
      opacity: enabled ? 1 : 0.5,
      child: DecoratedBox(
        decoration: BoxDecoration(
          gradient: AppTheme.brandGradient,
          borderRadius: BorderRadius.circular(10),
          boxShadow: enabled
              ? [
                  BoxShadow(
                    color: AppTheme.brand.withOpacity(0.35),
                    blurRadius: 18,
                    offset: const Offset(0, 6),
                  ),
                ]
              : null,
        ),
        child: Material(
          color: Colors.transparent,
          child: InkWell(
            borderRadius: BorderRadius.circular(10),
            onTap: onPressed,
            child: SizedBox(
              height: height,
              child: Center(
                child: DefaultTextStyle.merge(
                  style: const TextStyle(
                    color: Colors.white,
                    fontWeight: FontWeight.w700,
                    fontSize: 15,
                  ),
                  child: IconTheme.merge(
                    data: const IconThemeData(color: Colors.white, size: 20),
                    child: child,
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

/// A full-screen background with the web's two faint radial glows (purple
/// top-right, blue top-left) over the dark ground. Wrap auth/hero screens in it.
class BrandBackground extends StatelessWidget {
  final Widget child;
  const BrandBackground({super.key, required this.child});

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        Positioned.fill(
            child: ColoredBox(color: Theme.of(context).scaffoldBackgroundColor)),
        Positioned(
          top: -160,
          right: -120,
          child: _glow(AppTheme.brand2.withOpacity(0.22)),
        ),
        Positioned(
          top: -120,
          left: -140,
          child: _glow(AppTheme.brand.withOpacity(0.20)),
        ),
        child,
      ],
    );
  }

  Widget _glow(Color color) => Container(
        width: 360,
        height: 360,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          gradient: RadialGradient(
            colors: [color, color.withOpacity(0)],
          ),
        ),
      );
}
