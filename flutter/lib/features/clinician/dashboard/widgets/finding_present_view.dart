import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../../app/theme/app_colors.dart';
import '../../../../app/theme/app_typography.dart';
import '../../../../core/api/generated/api_models.dart';
import '../../../../widgets/organ_impact_viewer.dart';
import '../state/safety_assessment_provider.dart';

class FindingPresentView extends ConsumerStatefulWidget {
  const FindingPresentView({super.key, required this.analysis});

  final AdherenceAnalysisResult analysis;

  @override
  ConsumerState<FindingPresentView> createState() => _FindingPresentViewState();
}

class _FindingPresentViewState extends ConsumerState<FindingPresentView> {
  bool _showMonograph = false;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _buildCriticalBanner(),
        const SizedBox(height: 16),
        _buildTier1Card(),
        const SizedBox(height: 16),
        _buildTier2Card(),
        const SizedBox(height: 16),
        _buildTier3Card(),
        const SizedBox(height: 16),
        _buildPatientContextCard(),
      ],
    );
  }

  Widget _buildCriticalBanner() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
      decoration: BoxDecoration(
        color: AppColors.surfaceVariant.withValues(alpha: 0.8),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.border.withValues(alpha: 0.6)),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Flexible(
            child: Row(
              children: [
                const Icon(Icons.priority_high, color: Color(0xFFBA1A1A), size: 20),
                const SizedBox(width: 8),
                const Flexible(
                  child: Text(
                    '1 Critical Finding Requires Triage',
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                      letterSpacing: 0.2,
                      color: AppColors.textPrimary,
                    ),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(width: 8),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
            decoration: BoxDecoration(
              color: const Color(0xFFBA1A1A).withValues(alpha: 0.2),
              borderRadius: BorderRadius.circular(4),
              border: Border.all(color: const Color(0xFFBA1A1A).withValues(alpha: 0.5)),
            ),
            child: const Text(
              'Action Needed',
              style: TextStyle(
                fontFamily: 'JetBrains Mono',
                fontSize: 11,
                fontWeight: FontWeight.w500,
                color: Color(0xFFBA1A1A),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildTier1Card() {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0x4D881337), // #881337/30
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFFF43F5E), width: 1.5),
        boxShadow: const [
          BoxShadow(
            color: Color(0x2EF43F5E),
            blurRadius: 20,
            spreadRadius: 0,
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Flexible(
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                  decoration: BoxDecoration(
                    color: const Color(0x99881337),
                    borderRadius: BorderRadius.circular(4),
                    border: Border.all(color: const Color(0x99F43F5E)),
                  ),
                  child: const Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(Icons.shield, color: Color(0xFFFECDD3), size: 14),
                      SizedBox(width: 4),
                      Flexible(
                        child: Text(
                          '[TIER 1] DETERMINISTIC SAFETY FINDING',
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            fontSize: 10,
                            fontWeight: FontWeight.bold,
                            letterSpacing: 0.5,
                            color: Color(0xFFFECDD3),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              const SizedBox(width: 8),
              Text(
                'CRITICALITY: ${widget.analysis.safetyRiskLevel.toUpperCase()}',
                style: TextStyle(
                  fontFamily: 'JetBrains Mono',
                  fontSize: 11,
                  color: const Color(0xFFFECDD3).withValues(alpha: 0.8),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Icon(Icons.report_problem, color: Color(0xFFBA1A1A), size: 20),
              const SizedBox(width: 6),
              Expanded(
                child: Text(
                  'Deterministic Safety Finding',
                  style: const TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w600,
                    color: Color(0xFFFECDD3),
                  ),
                ),
              ),
            ],
          ),
          if (widget.analysis.requiresHumanReview) ...[
            const SizedBox(height: 4),
            Align(
              alignment: Alignment.centerLeft,
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(
                  color: const Color(0x80881337),
                  borderRadius: BorderRadius.circular(4),
                  border: Border.all(color: const Color(0x66F43F5E)),
                ),
                child: const Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.assignment_ind, color: Color(0xFFBA1A1A), size: 16),
                    SizedBox(width: 4),
                    Flexible(
                      child: Text(
                        'Human Review Required: Flagged for Clinician Review',
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(fontSize: 12, color: Color(0xE6FECDD3)),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
          const SizedBox(height: 12),
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: AppColors.surface.withValues(alpha: 0.6),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: const Color(0x33F43F5E)),
            ),
            child: Text(
              widget.analysis.recommendedAction,
              style: const TextStyle(
                fontSize: 14,
                height: 1.5,
                color: Color(0xFFFECDD3),
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
          const SizedBox(height: 12),

          const SizedBox(height: 16),
          Row(
            children: [
              Expanded(
                child: ElevatedButton.icon(
                  onPressed: () {},
                  icon: const Icon(Icons.contact_support, size: 18),
                  label: const Text('Notify Care Team', style: TextStyle(fontWeight: FontWeight.bold)),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: AppColors.primaryLight,
                    foregroundColor: AppColors.surface,
                    padding: const EdgeInsets.symmetric(vertical: 12),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                  ),
                ),
              ),
              const SizedBox(width: 8),
              OutlinedButton(
                onPressed: () {},
                style: OutlinedButton.styleFrom(
                  foregroundColor: AppColors.textPrimary,
                  backgroundColor: AppColors.surfaceVariant,
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                  side: const BorderSide(color: AppColors.border),
                ),
                child: const Text('Hold Dose', style: TextStyle(fontWeight: FontWeight.bold)),
              ),
            ],
          ),
          const SizedBox(height: 8),
          SizedBox(
            width: double.infinity,
            child: OutlinedButton.icon(
              onPressed: () async {
                final patientId = widget.analysis.patientId;
                try {
                  final assessment = await ref.read(safetyAssessmentProvider(patientId).future);
                  if (!mounted) return;
                  Navigator.of(context).push(
                    MaterialPageRoute(
                      builder: (_) => OrganImpactViewerScreen(assessment: assessment),
                    ),
                  );
                } catch (e) {
                  if (!mounted) return;
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(content: Text('Failed to load safety assessment: $e')),
                  );
                }
              },
              icon: const Icon(Icons.view_in_ar_rounded, size: 18),
              label: const Text('View Spatial Impact', style: TextStyle(fontWeight: FontWeight.bold)),
              style: OutlinedButton.styleFrom(
                foregroundColor: const Color(0xFF6366F1),
                backgroundColor: const Color(0x0D6366F1),
                padding: const EdgeInsets.symmetric(vertical: 12),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                side: const BorderSide(color: Color(0x806366F1)),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildTier2Card() {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0x661E1B4B), // #1E1B4B/40
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0x806366F1)), // #6366F1/50
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Flexible(
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                  decoration: BoxDecoration(
                    color: const Color(0xFF1E1B4B),
                    borderRadius: BorderRadius.circular(4),
                    border: Border.all(color: const Color(0x666366F1)),
                  ),
                  child: const Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(Icons.menu_book, color: Color(0xFFC7D2FE), size: 14),
                      SizedBox(width: 4),
                      Flexible(
                        child: Text(
                          '[TIER 2] VERIFIED CLINICAL EVIDENCE',
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            fontSize: 10,
                            fontWeight: FontWeight.bold,
                            letterSpacing: 0.5,
                            color: Color(0xFFC7D2FE),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              const SizedBox(width: 8),
              if (widget.analysis.clinicalBrief.citations?.isNotEmpty == true)
                Text(
                  'CITATIONS: ${widget.analysis.clinicalBrief.citations!.length}',
                  style: const TextStyle(
                    fontFamily: 'JetBrains Mono',
                    fontSize: 11,
                    color: Color(0xFFC7D2FE),
                  ),
                )
              else
                const Text(
                  'NO CITATIONS',
                  style: TextStyle(
                    fontFamily: 'JetBrains Mono',
                    fontSize: 11,
                    color: Color(0x80C7D2FE),
                  ),
                ),
            ],
          ),
          const SizedBox(height: 12),
          if (widget.analysis.clinicalBrief.citations?.isNotEmpty == true)
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: widget.analysis.clinicalBrief.citations!.map((c) => Padding(
                padding: const EdgeInsets.only(bottom: 8.0),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Icon(Icons.menu_book, size: 14, color: Color(0xFF818CF8)),
                    const SizedBox(width: 6),
                    Expanded(
                      child: Text(
                        c,
                        style: const TextStyle(
                          fontSize: 14,
                          height: 1.5,
                          color: Color(0xFFC7D2FE),
                        ),
                      ),
                    ),
                  ],
                ),
              )).toList(),
            )
          else
            const Text(
              'Deterministic finding triggered by invariant check. No document-backed RAG citations provided.',
              style: TextStyle(
                fontSize: 14,
                fontStyle: FontStyle.italic,
                color: Color(0x80C7D2FE),
              ),
            ),
          const SizedBox(height: 12),
          Container(
            decoration: const BoxDecoration(
              border: Border(top: BorderSide(color: Color(0x336366F1))),
            ),
            child: InkWell(
              onTap: () => setState(() => _showMonograph = !_showMonograph),
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 8),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Row(
                      children: [
                        const Icon(Icons.policy, size: 18, color: Color(0xFFA5B4FC)),
                        const SizedBox(width: 4),
                        const Text(
                          'View Full Monograph Excerpt',
                          style: TextStyle(
                            fontSize: 12,
                            fontWeight: FontWeight.w600,
                            letterSpacing: 0.2,
                            color: Color(0xFFA5B4FC),
                          ),
                        ),
                      ],
                    ),
                    Icon(
                      _showMonograph ? Icons.expand_less : Icons.expand_more,
                      size: 18,
                      color: const Color(0xFFA5B4FC),
                    ),
                  ],
                ),
              ),
            ),
          ),
          if (_showMonograph)
            Container(
              margin: const EdgeInsets.only(top: 8),
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: AppColors.surface.withValues(alpha: 0.8),
                borderRadius: BorderRadius.circular(4),
                border: Border.all(color: const Color(0x4D6366F1)),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'FDA Monograph Code: 074-ATV-FLC',
                    style: TextStyle(fontSize: 12, color: AppColors.textSecondary),
                  ),
                  const SizedBox(height: 4),
                  const Text(
                    'Pharmacokinetic profile: Fluconazole is a moderate CYP3A4 inhibitor at standard dosages. When co-administered with statins with high CYP3A4 dependence, substitute Pravastatin or Rosuvastatin under primary care guidance.',
                    style: TextStyle(fontFamily: 'JetBrains Mono', fontSize: 11, height: 1.4, color: Color(0xFFC7D2FE)),
                  ),
                  const SizedBox(height: 8),
                  GestureDetector(
                    onTap: () {},
                    child: const Text(
                      'Open Clinical Dossier in EHR External Browser ↗',
                      style: TextStyle(
                        fontSize: 12,
                        color: AppColors.primary,
                        decoration: TextDecoration.underline,
                      ),
                    ),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildTier3Card() {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0x4D3B0764), // #3B0764/30
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0x80A855F7)), // #A855F7/50
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Flexible(
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                  decoration: BoxDecoration(
                    color: const Color(0xB33B0764),
                    borderRadius: BorderRadius.circular(4),
                    border: Border.all(color: const Color(0x80A855F7)),
                  ),
                  child: const Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(Icons.auto_awesome, color: Color(0xFFE9D5FF), size: 14),
                      SizedBox(width: 4),
                      Flexible(
                        child: Text(
                          '[TIER 3] AI-ASSISTED SUMMARY (NON-DETERMINISTIC)',
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            fontSize: 10,
                            fontWeight: FontWeight.bold,
                            letterSpacing: 0.5,
                            color: Color(0xFFE9D5FF),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              const SizedBox(width: 8),
              const Icon(Icons.arrow_back_ios_new, color: Color(0xFF842BD2), size: 18),
            ],
          ),
          const SizedBox(height: 12),
          Text.rich(
              TextSpan(
                children: [
                  const TextSpan(
                    text: 'Patient-friendly summary: ',
                    style: TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                      letterSpacing: 0.3,
                      color: Color(0xFFD8B4FE),
                    ),
                  ),
                  TextSpan(
                    text: widget.analysis.patientExplanation.summary,
                    style: AppTypography.narrative.copyWith(
                      color: const Color(0xFFF3E8FF),
                    ),
                  ),
                ],
              ),
            ),
            if (widget.analysis.clinicalBrief.insights != null) ...[
              const SizedBox(height: 12),
              if (widget.analysis.clinicalBrief.insights!.trend != null)
                Align(
                  alignment: Alignment.centerLeft,
                  child: Container(
                    margin: const EdgeInsets.only(bottom: 8),
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                    decoration: BoxDecoration(
                      color: AppColors.surfaceMuted,
                      borderRadius: BorderRadius.circular(4),
                      border: Border.all(color: const Color(0x33A855F7)),
                    ),
                    child: Text(
                      'Trend: ${widget.analysis.clinicalBrief.insights!.trend}',
                      style: const TextStyle(
                        fontFamily: 'JetBrains Mono',
                        fontSize: 11,
                        fontWeight: FontWeight.w500,
                        color: Color(0xFFD8B4FE),
                      ),
                    ),
                  ),
                ),
              if (widget.analysis.clinicalBrief.insights!.concerningPatterns?.isNotEmpty == true) ...[
                const Text(
                  'CONCERNING PATTERNS',
                  style: TextStyle(
                    fontSize: 10,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 0.5,
                    color: Color(0xFFD8B4FE),
                  ),
                ),
                const SizedBox(height: 4),
                ...widget.analysis.clinicalBrief.insights!.concerningPatterns!.map(
                  (pattern) => Padding(
                    padding: const EdgeInsets.only(bottom: 4),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text('• ',
                            style: TextStyle(
                                color: Color(0xFFA855F7), fontSize: 14)),
                        Expanded(
                          child: Text(
                            pattern,
                            style: AppTypography.narrative.copyWith(
                              fontSize: 13,
                              color: const Color(0xFFF3E8FF),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ],
              if (widget.analysis.clinicalBrief.insights!.possibleBarriers?.isNotEmpty == true) ...[
                const SizedBox(height: 8),
                const Text(
                  'POSSIBLE BARRIERS',
                  style: TextStyle(
                    fontSize: 10,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 0.5,
                    color: Color(0xFFD8B4FE),
                  ),
                ),
                const SizedBox(height: 4),
                ...widget.analysis.clinicalBrief.insights!.possibleBarriers!.map(
                  (barrier) => Container(
                    margin: const EdgeInsets.only(bottom: 4),
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                    decoration: BoxDecoration(
                      color: AppColors.surfaceMuted.withValues(alpha: 0.5),
                      borderRadius: BorderRadius.circular(4),
                    ),
                    child: Row(
                      children: [
                        Text(
                          barrier.category.name.toUpperCase(),
                          style: const TextStyle(
                            fontFamily: 'JetBrains Mono',
                            fontSize: 10,
                            fontWeight: FontWeight.w600,
                            color: Color(0xFFA855F7),
                          ),
                        ),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(
                            barrier.observedPattern,
                            style: AppTypography.narrative.copyWith(
                              fontSize: 12,
                              color: const Color(0xFFE9D5FF),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ],
            const SizedBox(height: 6),
            Row(
              children: [
                const Icon(Icons.info_outline, color: Color(0xCCD8B4FE), size: 13),
                const SizedBox(width: 4),
                const Expanded(
                  child: Text(
                    'Generated via MedAssist Clinical LLM — Always verify with clinician.',
                    style: TextStyle(fontSize: 11, color: Color(0xCCD8B4FE)),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Container(
              padding: const EdgeInsets.only(top: 8),
              decoration: const BoxDecoration(
                border: Border(top: BorderSide(color: Color(0x33A855F7))),
              ),
              child: const Text(
                'LLM Confidence: Generated via Medical Safety Agent',
                style: TextStyle(fontSize: 10, letterSpacing: 0.5, color: Color(0xFFD8B4FE)),
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildPatientContextCard() {
    final barriers = widget.analysis.clinicalBrief.insights?.possibleBarriers;
    final barrier = barriers != null && barriers.isNotEmpty ? barriers.first : null;
    
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Expanded(
                child: Text(
                  'PATIENT-REPORTED CONTEXT',
                  style: TextStyle(
                    fontSize: 11,
                    fontWeight: FontWeight.bold,
                    letterSpacing: 0.5,
                    color: AppColors.textSecondary,
                  ),
                ),
              ),
              const SizedBox(width: 8),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                decoration: BoxDecoration(
                  color: const Color(0x2610B981), // emerald-500/15
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(color: const Color(0xFF10B981)),
                ),
                child: const Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.check_circle, color: Color(0xFF34D399), size: 12),
                    SizedBox(width: 4),
                    Text(
                      'Confidence: Observed (Self-reported)',
                      style: TextStyle(
                        fontSize: 10,
                        letterSpacing: 0.5,
                        fontWeight: FontWeight.w600,
                        color: Color(0xFF34D399),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              const Icon(Icons.history_edu, color: Colors.amber, size: 18),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  barrier != null ? '${barrier.category.name} — ${barrier.observedPattern}' : 'Patient-reported context recorded during session',
                  style: const TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w600,
                    color: AppColors.textPrimary,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: AppColors.surfaceMuted,
              borderRadius: BorderRadius.circular(8),
              border: const Border(left: BorderSide(color: AppColors.primary, width: 2)),
            ),
            child: Text(
              '“${widget.analysis.patientExplanation.whatTheSystemFound}”',
              style: const TextStyle(
                fontSize: 14,
                fontStyle: FontStyle.italic,
                color: AppColors.textPrimary,
              ),
            ),
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              const Icon(Icons.verified_user, color: AppColors.primary, size: 15),
              const SizedBox(width: 6),
              const Expanded(
                child: Text(
                  'Note authored by patient — Entered into permanent EHR record for review by care team.',
                  style: TextStyle(fontSize: 11, color: AppColors.textSecondary),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
