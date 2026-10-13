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
        const Positioned.fill(child: ColoredBox(color: AppTheme.bg)),
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
