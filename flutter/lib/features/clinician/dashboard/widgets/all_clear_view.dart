import 'package:flutter/material.dart';
import '../../../../app/theme/app_colors.dart';
import '../../../../core/api/generated/api_models.dart';

class AllClearView extends StatelessWidget {
  const AllClearView({super.key, required this.analysis});

  final AdherenceAnalysisResult analysis;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _buildEmeraldBanner(),
        const SizedBox(height: 16),
        _buildScheduleProgress(),
        const SizedBox(height: 16),
        _buildSafetyMatrix(),
      ],
    );
  }

  Widget _buildEmeraldBanner() {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0x4D022C22), // emerald-950/30
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xB310B981), width: 1.5), // emerald-500/70
        boxShadow: const [
          BoxShadow(
            color: Color(0x2610B981), // emerald-500/15
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
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                decoration: BoxDecoration(
                  color: const Color(0xCC022C22), // emerald-950/80
                  borderRadius: BorderRadius.circular(4),
                  border: Border.all(color: const Color(0x8010B981)), // emerald-500/50
                ),
                child: Row(
                  children: [
                    const Icon(Icons.verified, color: Color(0xFF6EE7B7), size: 14), // emerald-300
                    const SizedBox(width: 4),
                    const Text(
                      '[TIER 1] DETERMINISTIC SAFETY FINDING',
                      style: TextStyle(
                        fontSize: 10,
                        fontWeight: FontWeight.bold,
                        letterSpacing: 0.5,
                        color: Color(0xFF6EE7B7),
                      ),
                    ),
                  ],
                ),
              ),
              const Text(
                'STATUS: ZERO RISK',
                style: TextStyle(
                  fontFamily: 'JetBrains Mono',
                  fontSize: 11,
                  fontWeight: FontWeight.bold,
                  color: Color(0xFF34D399), // emerald-400
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: 40,
                height: 40,
                decoration: BoxDecoration(
                  color: const Color(0x3310B981), // emerald-500/20
                  shape: BoxShape.circle,
                  border: Border.all(color: const Color(0x6610B981)), // emerald-500/40
                ),
                child: const Icon(Icons.task_alt, color: Color(0xFF34D399), size: 24),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'All Clear: No Safety Concerns Detected',
                      style: TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.w600,
                        letterSpacing: -0.5,
                        color: Color(0xFFA7F3D0), // emerald-200
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      'Engine checked 4 active prescriptions against 1,280 drug-drug & food interactions. No contraindications or timing collisions found.',
                      style: TextStyle(
                        fontSize: 14,
                        height: 1.5,
                        color: const Color(0xFF6EE7B7).withValues(alpha: 0.9),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: AppColors.surface.withValues(alpha: 0.8),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: const Color(0x3310B981)),
            ),
            child: Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        'ACTIVE REGIMEN',
                        style: TextStyle(fontSize: 10, color: Color(0xFF34D399)),
                      ),
                      const Text(
                        '4 Prescriptions Verified',
                        style: TextStyle(fontFamily: 'JetBrains Mono', fontSize: 13, color: AppColors.textPrimary),
                      ),
                    ],
                  ),
                ),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        'INTERACTION KERNEL',
                        style: TextStyle(fontSize: 10, color: Color(0xFF34D399)),
                      ),
                      const Text(
                        'v4.2 (Zero Collision)',
                        style: TextStyle(fontFamily: 'JetBrains Mono', fontSize: 13, color: AppColors.textPrimary),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildScheduleProgress() {
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
              const Text(
                'Today\'s Schedule Progress',
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600, color: AppColors.textPrimary),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                decoration: BoxDecoration(
                  color: const Color(0x2610B981), // emerald-500/15
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(color: const Color(0xFF10B981)),
                ),
                child: Row(
                  children: [
                    const Icon(Icons.check, color: Color(0xFF6EE7B7), size: 13),
                    const SizedBox(width: 4),
                    const Text(
                      '3 of 4 doses on track',
                      style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, letterSpacing: 0.2, color: Color(0xFF6EE7B7)),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: const LinearProgressIndicator(
              value: 0.75,
              minHeight: 8,
              backgroundColor: AppColors.surfaceVariant,
              valueColor: AlwaysStoppedAnimation<Color>(AppColors.primary),
            ),
          ),
          const SizedBox(height: 12),
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: AppColors.surfaceMuted,
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: AppColors.border),
            ),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Row(
                  children: [
                    Container(
                      width: 36,
                      height: 36,
                      decoration: BoxDecoration(
                        color: AppColors.surfaceVariant,
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(color: AppColors.border),
                      ),
                      child: const Icon(Icons.medication, color: AppColors.primary, size: 20),
                    ),
                    const SizedBox(width: 12),
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text(
                          'NEXT UP TODAY',
                          style: TextStyle(fontSize: 10, letterSpacing: 0.5, color: AppColors.textSecondary),
                        ),
                        const Text(
                          'Atorvastatin 20mg',
                          style: TextStyle(fontFamily: 'JetBrains Mono', fontSize: 14, fontWeight: FontWeight.w600, color: AppColors.textPrimary),
                        ),
                        const Text(
                          'Scheduled at 08:00 PM',
                          style: TextStyle(fontSize: 12, color: AppColors.textSecondary),
                        ),
                      ],
                    ),
                  ],
                ),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    border: Border.all(color: Colors.blueGrey),
                    borderRadius: BorderRadius.circular(4),
                  ),
                  child: const Text(
                    'PENDING',
                    style: TextStyle(fontSize: 10, letterSpacing: 0.5, fontWeight: FontWeight.bold, color: Colors.blueGrey),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              const Icon(Icons.verified, color: AppColors.primary, size: 16),
              const SizedBox(width: 8),
              const Text(
                'Next routine automated cross-check scheduled at 12:00 PM.',
                style: TextStyle(fontSize: 12, color: AppColors.textSecondary),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildSafetyMatrix() {
    return Row(
      children: [
        Expanded(
          child: Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: AppColors.surfaceMuted,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: AppColors.border.withValues(alpha: 0.6)),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'FOOD INTERACTIONS',
                  style: TextStyle(fontSize: 10, color: AppColors.textSecondary),
                ),
                const SizedBox(height: 4),
                const Text(
                  'None Reported',
                  style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600, color: AppColors.textPrimary),
                ),
                const SizedBox(height: 4),
                const Text(
                  'Grapefruit & dairy safety verified across current active Rx.',
                  style: TextStyle(fontSize: 11, color: AppColors.textSecondary),
                ),
              ],
            ),
          ),
        ),
        const SizedBox(width: 8),
        Expanded(
          child: Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: AppColors.surfaceMuted,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: AppColors.border.withValues(alpha: 0.6)),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'CARE TEAM SYNC',
                  style: TextStyle(fontSize: 10, color: AppColors.textSecondary),
                ),
                const SizedBox(height: 4),
                const Text(
                  'In Sync',
                  style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600, color: AppColors.primary),
                ),
                const SizedBox(height: 4),
                const Text(
                  'Dr. Lin reviewed record during 08:15 AM rounds.',
                  style: TextStyle(fontSize: 11, color: AppColors.textSecondary),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}
