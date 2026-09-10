import 'dart:ui';

import 'package:flutter/material.dart';

import '../app/theme/app_colors.dart';

/// Layout shell for a future organ-impact visualisation. **Contains no clinical data,
/// and must not be given any until it is fed by the backend.**
///
/// Nothing imports this file. It is kept for its geometry — the responsive two-column
/// split, the glass overlays, the render stage, the step timeline — because Phase 5.5
/// may reuse that language for the clinician safety review. It is not a feature.
///
/// ## What was removed, and why it mattered
///
/// It arrived as a compiled transcription of a Stitch mockup, with the mockup's filler
/// presented as computed output. Every item below was a hardcoded string literal with no
/// engine, model or retrieval behind it. The strings themselves are deliberately *not*
/// reproduced here — an inventory of ready-to-paste fabricated clinical sentences is the
/// same hazard one indirection removed — so this lists only the shape of each:
///
/// - a red "human review required / contraindicated medication detected" alert banner
/// - a named drug–drug interaction, with its mechanism written as established fact and a
///   predicted physiological outcome
/// - a categorical risk-level chip, at the top of the severity scale
/// - an "AI predictive brief": a two-digit probability of a catastrophic event, presented
///   as derived from the patient's age, baseline blood pressure and renal function
/// - a three-step pharmacodynamic sequence for that interaction
/// - an "evidence provenance" list citing a regulatory warning and a drug monograph, as
///   though a retrieval step had returned them for this case
/// - a full patient identity: name, date of birth, medical record number, body weight
/// - a clinician identity — name and specialty — plus an avatar fetched from a
///   third-party stock-photo service, i.e. an outbound request from a clinical screen
/// - the wrong product name
/// - a "last updated: just now" freshness claim about data that did not exist
/// - "Review & Acknowledge" and "Modify Prescription" buttons wired to `() {}`
///
/// In a mockup that is filler. Compiled into a widget it renders with the full visual
/// authority of a computed finding, and it made the highest-stakes claim this app is
/// capable of making: a named patient is one dose from a life-threatening event, act now.
/// Nothing in this codebase produced any of it. The project's own [AppColors] doc explains
/// why the three trust tiers exist; this screen collapsed all three into one confident
/// surface.
///
/// Fabricated clinical text was not replaced with more plausible clinical text. The
/// panels render their genuine empty state, and that state is deliberately drawn in
/// [AppColors.textDisabled] and [AppColors.surfaceMuted] rather than in
/// [AppColors.deterministicFinding] — absence of an assessment must not be dressed as
/// the output of one.
///
/// ## Wiring it up later
///
/// ```text
/// SafetyAssessment → API DTO → controller → OrganImpactViewerScreen → pure painting
/// ```
///
/// The private widgets below take no clinical parameters. That is intentional: the
/// speculative ones they briefly had described a DTO that does not exist yet, and the
/// analyzer flagged every one as never supplied. Add parameters when there is a real
/// response to match them to. When it is wired, delete this section of the doc — not the
/// warning above it.
class OrganImpactViewerScreen extends StatelessWidget {
  const OrganImpactViewerScreen({super.key});

  /// Shown wherever a panel would otherwise display a value it does not have.
  static const String _noData = 'No clinical data available';
  static const String _awaiting = 'Awaiting assessment';

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        backgroundColor: AppColors.surface.withValues(alpha: 0.85),
        flexibleSpace: ClipRect(
          child: BackdropFilter(
            filter: ImageFilter.blur(sigmaX: 20, sigmaY: 20),
            child: Container(color: Colors.transparent),
          ),
        ),
        elevation: 0,
        // No product name and no signed-in clinician. This screen is not part of a
        // session; presenting a user chip would imply it had loaded one.
        title: Row(
          children: [
            Container(
              padding: const EdgeInsets.all(6),
              decoration: BoxDecoration(
                color: AppColors.surfaceMuted,
                borderRadius: BorderRadius.circular(8),
              ),
              child: const Icon(
                Icons.view_in_ar_rounded,
                color: AppColors.textSecondary,
                size: 22,
              ),
            ),
            const SizedBox(width: 12),
            const Text(
              'Visual preview',
              style: TextStyle(
                color: AppColors.textPrimary,
                fontWeight: FontWeight.bold,
                fontSize: 18,
              ),
            ),
          ],
        ),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 24),
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 1280),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const _AccentBanner(
                  icon: Icons.info_outline_rounded,
                  title: 'LAYOUT PREVIEW — NOT CONNECTED',
                  body:
                      'This screen is not wired to the safety engine. It renders its own '
                      'empty state and shows no patient, medication or risk level.',
                ),
                const SizedBox(height: 24),
                const _SubjectHeaderCard(),
                const SizedBox(height: 24),
                LayoutBuilder(
                  builder: (context, constraints) {
                    // The only reason this file is worth keeping: the wide layout puts
                    // the stage beside the panels, the narrow one stacks them.
                    if (constraints.maxWidth > 900) {
                      return const Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Expanded(flex: 8, child: _RenderStage()),
                          SizedBox(width: 24),
                          Expanded(flex: 4, child: _InfoPanels()),
                        ],
                      );
                    }
                    return const Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        _RenderStage(),
                        SizedBox(height: 24),
                        _InfoPanels(),
                      ],
                    );
                  },
                ),
                const SizedBox(height: 100), // clearance for the footer bar
              ],
            ),
          ),
        ),
      ),
      bottomSheet: const _FooterBar(),
    );
  }
}

/// A notice strip with a left accent rule.
///
/// The accent is the neutral token, hardcoded. It briefly took the colour as a parameter
/// so a caller could pass [AppColors.deterministicFinding] — but no caller exists, and a
/// colour knob whose only purpose is to make this strip look like a rules-engine result
/// is a knob worth not having until there is a result. Add it back with the finding.
class _AccentBanner extends StatelessWidget {
  const _AccentBanner({
    required this.icon,
    required this.title,
    required this.body,
  });

  final IconData icon;
  final String title;
  final String body;

  static const Color accent = AppColors.textSecondary;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: AppColors.surfaceMuted,
        borderRadius: const BorderRadius.only(
          topRight: Radius.circular(12),
          bottomRight: Radius.circular(12),
        ),
        border: Border(left: BorderSide(color: accent, width: 4)),
        boxShadow: [
          BoxShadow(
            color: AppColors.textPrimary.withValues(alpha: 0.05),
            blurRadius: 10,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      padding: const EdgeInsets.all(16),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            padding: const EdgeInsets.all(8),
            decoration: BoxDecoration(
              color: accent.withValues(alpha: 0.1),
              shape: BoxShape.circle,
            ),
            child: Icon(icon, color: accent),
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: TextStyle(
                    color: accent,
                    fontWeight: FontWeight.bold,
                    fontSize: 14,
                    letterSpacing: 0.5,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  body,
                  style: const TextStyle(
                    color: AppColors.textSecondary,
                    fontSize: 14,
                    fontWeight: FontWeight.w500,
                    height: 1.4,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// Header card geometry: avatar, name line, a row of metadata badges, a status chip.
///
/// Renders with every slot empty. It previously carried a full synthetic patient
/// record — name, date of birth, medical record number and weight — which is both
/// fabricated clinical data and, in shape, exactly what a real record looks like.
class _SubjectHeaderCard extends StatelessWidget {
  const _SubjectHeaderCard();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: AppColors.surface.withValues(alpha: 0.85),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppColors.border, width: 1.5),
        boxShadow: [
          BoxShadow(
            color: AppColors.textPrimary.withValues(alpha: 0.07),
            blurRadius: 32,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: Wrap(
        alignment: WrapAlignment.spaceBetween,
        crossAxisAlignment: WrapCrossAlignment.center,
        spacing: 24,
        runSpacing: 16,
        children: [
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 64,
                height: 64,
                decoration: BoxDecoration(
                  // No NetworkImage. The original pulled a stock face from
                  // i.pravatar.cc, which put a third-party request behind a clinical
                  // header and gave an empty screen a person.
                  gradient: const LinearGradient(
                    colors: [AppColors.surfaceMuted, AppColors.border],
                  ),
                  shape: BoxShape.circle,
                  border: Border.all(color: AppColors.surface, width: 2),
                ),
                alignment: Alignment.center,
                child: const Icon(
                  Icons.person_outline_rounded,
                  color: AppColors.textDisabled,
                  size: 30,
                ),
              ),
              const SizedBox(width: 20),
              const Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    OrganImpactViewerScreen._noData,
                    style: TextStyle(
                      color: AppColors.textDisabled,
                      fontSize: 20,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  SizedBox(height: 8),
                  Wrap(
                    spacing: 20,
                    children: [
                      _InfoBadge(icon: Icons.calendar_month_rounded),
                      _InfoBadge(icon: Icons.badge_rounded),
                      _InfoBadge(icon: Icons.monitor_weight_rounded),
                    ],
                  ),
                ],
              ),
            ],
          ),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
            decoration: BoxDecoration(
              color: AppColors.surfaceMuted,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: AppColors.border),
            ),
            child: const Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  Icons.pending_outlined,
                  color: AppColors.textDisabled,
                  size: 18,
                ),
                SizedBox(width: 8),
                // Where the hardcoded risk-level chip was. A risk level is a
                // SafetyAssessment output; this screen has never seen one.
                Text(
                  OrganImpactViewerScreen._awaiting,
                  style: TextStyle(
                    color: AppColors.textDisabled,
                    fontWeight: FontWeight.bold,
                    fontSize: 13,
                    letterSpacing: 0.5,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// One metadata badge, with no value to show. Renders an em dash.
class _InfoBadge extends StatelessWidget {
  const _InfoBadge({required this.icon});

  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 16, color: AppColors.textDisabled),
        const SizedBox(width: 6),
        const Text(
          '—',
          style: TextStyle(fontSize: 14, color: AppColors.textDisabled),
        ),
      ],
    );
  }
}

/// The dark render stage, with a header rail and a floating glass caption.
///
/// There is no 3D model, no renderer and no anatomy here — there never was. The
/// original was equally empty, but it labelled itself an "Interactive 3D Render Area"
/// underneath a caption asserting a specific drug interaction, so the blank panel read
/// as a visualisation that had been computed and simply had not painted yet.
class _RenderStage extends StatelessWidget {
  const _RenderStage();

  // Local to this file rather than promoted to AppColors: a dark viewport backdrop is
  // stage furniture, not a semantic token, and adding it to the palette would invite
  // reuse as a surface colour.
  static const Color _stageTop = Color(0xFF1E293B);
  static const Color _stageBottom = Color(0xFF0F172A);

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 550,
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(16),
        boxShadow: [
          BoxShadow(
            color: AppColors.textPrimary.withValues(alpha: 0.05),
            blurRadius: 20,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(
        children: [
          Container(
            padding: const EdgeInsets.all(20),
            decoration: const BoxDecoration(
              border: Border(bottom: BorderSide(color: AppColors.border)),
              color: AppColors.surface,
            ),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.all(6),
                      decoration: BoxDecoration(
                        color: AppColors.surfaceMuted,
                        borderRadius: BorderRadius.circular(6),
                      ),
                      child: const Icon(
                        Icons.threed_rotation_rounded,
                        color: AppColors.textSecondary,
                      ),
                    ),
                    const SizedBox(width: 10),
                    const Text(
                      'Spatial viewer',
                      style: TextStyle(
                        fontSize: 17,
                        fontWeight: FontWeight.bold,
                        color: AppColors.textPrimary,
                      ),
                    ),
                  ],
                ),
                // Disabled, not no-op. These were live-looking buttons wired to an
                // empty closure; there is nothing to zoom.
                const Row(
                  children: [
                    IconButton(
                      onPressed: null,
                      icon: Icon(Icons.zoom_in),
                      tooltip: 'Zoom in (unavailable in preview)',
                    ),
                    IconButton(
                      onPressed: null,
                      icon: Icon(Icons.zoom_out),
                      tooltip: 'Zoom out (unavailable in preview)',
                    ),
                  ],
                ),
              ],
            ),
          ),
          Expanded(
            child: Stack(
              fit: StackFit.expand,
              children: [
                Container(
                  decoration: const BoxDecoration(
                    gradient: RadialGradient(
                      colors: [_stageTop, _stageBottom],
                      radius: 1.0,
                    ),
                  ),
                  child: Center(
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(
                          Icons.view_in_ar_outlined,
                          color: AppColors.surface.withValues(alpha: 0.35),
                          size: 64,
                        ),
                        const SizedBox(height: 16),
                        Text(
                          'NO MODEL LOADED',
                          style: TextStyle(
                            color: AppColors.surface.withValues(alpha: 0.5),
                            fontSize: 13,
                            letterSpacing: 1.5,
                            fontWeight: FontWeight.w500,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                const Positioned(
                  bottom: 24,
                  left: 24,
                  right: 24,
                  child: _StageCaption(),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// The frosted caption that floats over the stage.
///
/// Held the fabricated interaction narrative. Kept because the blur-over-dark geometry
/// is the hardest part of this layout to rebuild.
class _StageCaption extends StatelessWidget {
  const _StageCaption();

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(12),
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 16, sigmaY: 16),
        child: Container(
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            color: AppColors.surface.withValues(alpha: 0.85),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: AppColors.surface.withValues(alpha: 0.6)),
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: AppColors.surfaceMuted,
                  shape: BoxShape.circle,
                  border: Border.all(color: AppColors.border),
                ),
                child: const Icon(
                  Icons.help_outline_rounded,
                  color: AppColors.textDisabled,
                ),
              ),
              const SizedBox(width: 16),
              const Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'No impact zone selected',
                      style: TextStyle(
                        fontSize: 15,
                        fontWeight: FontWeight.bold,
                        color: AppColors.textDisabled,
                      ),
                    ),
                    SizedBox(height: 6),
                    Text(
                      OrganImpactViewerScreen._noData,
                      style: TextStyle(
                        fontSize: 14,
                        color: AppColors.textDisabled,
                        fontWeight: FontWeight.w500,
                        height: 1.4,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _InfoPanels extends StatelessWidget {
  const _InfoPanels();

  @override
  Widget build(BuildContext context) {
    return const Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _MetricPanel(),
        SizedBox(height: 24),
        _StepTimeline(),
        SizedBox(height: 24),
        _ProvenancePanel(),
      ],
    );
  }
}

/// A single large figure with a caption beneath it. The figure is an em dash; there is
/// no value and nothing that could produce one.
///
/// This was the worst panel in the file: a high two-digit probability, set in 64pt on a
/// deep gradient, under an "AI predictive brief" heading — a confidence score for a
/// catastrophic outcome, with no model anywhere in the codebase and no input it could
/// have been computed from. Note also that the gradient was itself a claim: per
/// [AppColors], generated content belongs in [AppColors.aiAssisted], deliberately unlike
/// the deterministic and evidence tiers so that it cannot borrow their authority.
class _MetricPanel extends StatelessWidget {
  const _MetricPanel();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: AppColors.surface.withValues(alpha: 0.85),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppColors.border, width: 1.5),
        boxShadow: [
          BoxShadow(
            color: AppColors.textPrimary.withValues(alpha: 0.07),
            blurRadius: 32,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            decoration: BoxDecoration(
              color: AppColors.surfaceMuted,
              borderRadius: BorderRadius.circular(20),
              border: Border.all(color: AppColors.border),
            ),
            child: const Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  Icons.analytics_outlined,
                  color: AppColors.textDisabled,
                  size: 14,
                ),
                SizedBox(width: 6),
                Text(
                  'SUMMARY',
                  style: TextStyle(
                    color: AppColors.textDisabled,
                    fontSize: 12,
                    fontWeight: FontWeight.bold,
                    letterSpacing: 0.5,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          // An em dash, unconditionally — there is no value and no source for one.
          //
          // When this is wired, the rule the rest of the app follows applies here too:
          // a null figure renders as no-data, never as a number. `?? 0` would print 0%
          // and `?? 1` would print 100%, and both are assertions about a patient nothing
          // has assessed. See `spatial_adherence_torus.dart`, which had exactly this bug.
          const Text(
            '—',
            style: TextStyle(
              color: AppColors.textDisabled,
              fontSize: 56,
              fontWeight: FontWeight.bold,
              height: 1,
            ),
          ),
          const SizedBox(height: 8),
          const Text(
            OrganImpactViewerScreen._awaiting,
            style: TextStyle(
              color: AppColors.textSecondary,
              fontSize: 14,
              fontWeight: FontWeight.bold,
              letterSpacing: 0.5,
            ),
          ),
          const SizedBox(height: 12),
          const Text(
            OrganImpactViewerScreen._noData,
            style: TextStyle(
              color: AppColors.textDisabled,
              fontSize: 14,
              fontWeight: FontWeight.w500,
              height: 1.5,
            ),
          ),
        ],
      ),
    );
  }
}

/// Numbered vertical step list.
///
/// Held a three-step pharmacodynamic mechanism written as established fact. The step
/// rows now carry ordinal placeholders only; nothing describes a physiological process.
class _StepTimeline extends StatelessWidget {
  const _StepTimeline();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: AppColors.surface.withValues(alpha: 0.85),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppColors.border, width: 1.5),
        boxShadow: [
          BoxShadow(
            color: AppColors.textPrimary.withValues(alpha: 0.07),
            blurRadius: 32,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(6),
                decoration: BoxDecoration(
                  color: AppColors.surfaceMuted,
                  borderRadius: BorderRadius.circular(6),
                ),
                child: const Icon(
                  Icons.timeline_rounded,
                  color: AppColors.textSecondary,
                ),
              ),
              const SizedBox(width: 10),
              const Text(
                'Sequence',
                style: TextStyle(
                  fontSize: 17,
                  fontWeight: FontWeight.bold,
                  color: AppColors.textPrimary,
                ),
              ),
            ],
          ),
          const SizedBox(height: 20),
          // Three ordinal placeholders. The count is layout, not a claim that an
          // assessment has three stages.
          for (var step = 1; step <= 3; step++) ...[
            _TimelineStep(
              number: '$step',
              title: 'Step $step',
              subtitle: OrganImpactViewerScreen._awaiting,
            ),
            if (step < 3) const SizedBox(height: 16),
          ],
        ],
      ),
    );
  }
}

/// One step row: numbered disc, then a filled panel with a title and a subtitle.
///
/// There was an `emphasised` variant that swapped the disc for a lightning bolt and the
/// panel for [AppColors.deterministicFindingSurface]. It is gone rather than left
/// unreachable: an alert style is only meaningful attached to a real finding, and the
/// deterministic tier's colours belong to rules-engine output. Reintroduce it in Phase
/// 5.5, driven by the assessment, not by a bool a preview sets.
class _TimelineStep extends StatelessWidget {
  const _TimelineStep({
    required this.number,
    required this.title,
    required this.subtitle,
  });

  final String number;
  final String title;
  final String subtitle;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          width: 36,
          height: 36,
          decoration: BoxDecoration(
            color: AppColors.surfaceMuted,
            shape: BoxShape.circle,
            border: Border.all(color: AppColors.border, width: 2),
          ),
          alignment: Alignment.center,
          child: Text(
            number,
            style: const TextStyle(
              fontWeight: FontWeight.bold,
              color: AppColors.textDisabled,
              fontSize: 14,
            ),
          ),
        ),
        const SizedBox(width: 16),
        Expanded(
          child: Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: AppColors.surfaceMuted.withValues(alpha: 0.5),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: AppColors.border),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: const TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.bold,
                    color: AppColors.textSecondary,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  subtitle,
                  style: const TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w500,
                    color: AppColors.textDisabled,
                  ),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

/// Source list geometry.
///
/// Cited a regulatory warning and a drug monograph as though a retrieval step had
/// returned them for this case. `app/rag/` is a lexical bag-of-words index and this
/// screen never called it. Citations are the one thing that must never be placeholder
/// text — a clinician checking provenance is checking exactly this.
class _ProvenancePanel extends StatelessWidget {
  const _ProvenancePanel();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppColors.border),
        boxShadow: [
          BoxShadow(
            color: AppColors.textPrimary.withValues(alpha: 0.05),
            blurRadius: 10,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: const Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'SOURCES',
            style: TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.bold,
              color: AppColors.textSecondary,
              letterSpacing: 1.0,
            ),
          ),
          SizedBox(height: 12),
          _ProvenanceRow(),
        ],
      ),
    );
  }
}

class _ProvenanceRow extends StatelessWidget {
  const _ProvenanceRow();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.surfaceMuted,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.border),
      ),
      child: const Row(
        children: [
          Icon(
            Icons.link_off_rounded,
            color: AppColors.textDisabled,
            size: 18,
          ),
          SizedBox(width: 12),
          Expanded(
            child: Text(
              'No sources retrieved',
              style: TextStyle(
                fontSize: 14,
                fontWeight: FontWeight.w600,
                color: AppColors.textDisabled,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// Sticky action rail.
///
/// Both buttons are disabled. They read 'Review & Acknowledge' and 'Modify
/// Prescription' and were wired to `() {}` — a prescription-modifying control that
/// silently did nothing, on a screen showing a critical alert. There is also no
/// timestamp chip any more: it said 'Last updated: Just now' about nothing.
class _FooterBar extends StatelessWidget {
  const _FooterBar();

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 80,
      decoration: BoxDecoration(
        color: AppColors.surface.withValues(alpha: 0.85),
        border: const Border(top: BorderSide(color: AppColors.border, width: 1.5)),
        boxShadow: [
          BoxShadow(
            color: AppColors.textPrimary.withValues(alpha: 0.1),
            blurRadius: 30,
            offset: const Offset(0, -10),
          ),
        ],
      ),
      child: ClipRect(
        child: BackdropFilter(
          filter: ImageFilter.blur(sigmaX: 20, sigmaY: 20),
          child: const Padding(
            padding: EdgeInsets.symmetric(horizontal: 32),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(
                  'Preview only — no actions available',
                  style: TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w500,
                    color: AppColors.textDisabled,
                  ),
                ),
                Row(
                  children: [
                    OutlinedButton(
                      onPressed: null,
                      child: Text('Secondary action'),
                    ),
                    SizedBox(width: 16),
                    ElevatedButton(
                      onPressed: null,
                      child: Text('Primary action'),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
