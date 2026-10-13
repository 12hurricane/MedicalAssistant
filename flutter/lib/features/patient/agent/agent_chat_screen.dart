import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../app/theme/app_colors.dart';
import '../../../../app/theme/app_typography.dart';
import 'state/agent_controller.dart';

/// Clinical medication assistant chat screen.
///
/// Designed under the flat, information-dense clinical-tool aesthetic:
/// - No glassmorphism, no blur filters, no glowing highlights.
/// - Flat AppColors tokens with solid borders and clear contrast.
/// - Clear distinction between patient-entered input and AI-generated narrative
///   (using [AppTypography.narrative] serif style for generated text).
class AgentChatScreen extends ConsumerStatefulWidget {
  const AgentChatScreen({super.key});

  @override
  ConsumerState<AgentChatScreen> createState() => _AgentChatScreenState();
}

class _AgentChatScreenState extends ConsumerState<AgentChatScreen> {
  final TextEditingController _textController = TextEditingController();
  final ScrollController _scrollController = ScrollController();

  void _sendMessage() {
    final text = _textController.text;
    if (text.trim().isEmpty) return;

    _textController.clear();
    ref.read(agentControllerProvider.notifier).sendMessage(text);
    _scrollToBottom();
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 200),
          curve: Curves.easeOut,
        );
      }
    });
  }

  @override
  void dispose() {
    _textController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(agentControllerProvider);

    ref.listen<AgentState>(agentControllerProvider, (previous, next) {
      if (previous?.messages.length != next.messages.length) {
        _scrollToBottom();
      }
    });

    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        backgroundColor: AppColors.surface,
        elevation: 0,
        scrolledUnderElevation: 0,
        shape: const Border(
          bottom: BorderSide(color: AppColors.border, width: 1),
        ),
        titleSpacing: 0,
        title: const Row(
          children: [
            Icon(Icons.smart_toy_outlined, color: AppColors.primary, size: 20),
            SizedBox(width: 8),
            Text(
              'MedAssist AI',
              style: AppTypography.titleMedium,
            ),
          ],
        ),
      ),
      body: SafeArea(
        child: Column(
          children: [
            Expanded(
              child: ListView.builder(
                controller: _scrollController,
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
                itemCount: state.messages.length,
                itemBuilder: (context, index) {
                  final message = state.messages[index];
                  return _ChatBubble(message: message);
                },
              ),
            ),
            if (state.isLoading)
              Container(
                padding: const EdgeInsets.symmetric(vertical: 8),
                alignment: Alignment.center,
                child: const SizedBox(
                  width: 20,
                  height: 20,
                  child: CircularProgressIndicator(
                    strokeWidth: 2,
                    valueColor: AlwaysStoppedAnimation<Color>(AppColors.primary),
                  ),
                ),
              ),
            if (state.error != null)
              Container(
                margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: AppColors.dangerSurface,
                  borderRadius: BorderRadius.circular(6),
                  border: Border.all(color: AppColors.danger),
                ),
                child: Text(
                  state.error!,
                  style: AppTypography.bodyMedium.copyWith(color: AppColors.danger),
                ),
              ),
            _ChatInputBox(
              controller: _textController,
              onSend: _sendMessage,
              isLoading: state.isLoading,
            ),
          ],
        ),
      ),
    );
  }
}

class _ChatBubble extends StatelessWidget {
  final ChatMessage message;

  const _ChatBubble({required this.message});

  @override
  Widget build(BuildContext context) {
    final isUser = message.isUser;

    return Container(
      margin: const EdgeInsets.symmetric(vertical: 6),
      alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: ConstrainedBox(
        constraints: BoxConstraints(
          maxWidth: MediaQuery.sizeOf(context).width * 0.82,
        ),
        child: Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: isUser ? AppColors.surfaceMuted : AppColors.surface,
            borderRadius: BorderRadius.circular(8),
            border: Border.all(
              color: isUser ? AppColors.outlineLight : AppColors.border,
              width: 1,
            ),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (!isUser) ...[
                Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Container(
                      width: 6,
                      height: 6,
                      decoration: const BoxDecoration(
                        color: AppColors.aiAssisted,
                        shape: BoxShape.circle,
                      ),
                    ),
                    const SizedBox(width: 6),
                    Text(
                      'AI ASSISTANT · GUIDANCE ONLY',
                      style: AppTypography.tierBadge.copyWith(
                        color: AppColors.aiAssisted,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
              ],
              Text(
                message.text,
                style: isUser
                    ? AppTypography.bodyMedium.copyWith(
                        color: AppColors.textPrimary,
                      )
                    : AppTypography.narrative,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ChatInputBox extends StatelessWidget {
  final TextEditingController controller;
  final VoidCallback onSend;
  final bool isLoading;

  const _ChatInputBox({
    required this.controller,
    required this.onSend,
    required this.isLoading,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      decoration: const BoxDecoration(
        color: AppColors.surface,
        border: Border(
          top: BorderSide(color: AppColors.border, width: 1),
        ),
      ),
      child: Row(
        children: [
          Expanded(
            child: TextField(
              controller: controller,
              style: AppTypography.bodyMedium.copyWith(color: AppColors.textPrimary),
              decoration: InputDecoration(
                hintText: 'Ask about your medications...',
                hintStyle: AppTypography.bodyMedium.copyWith(color: AppColors.textDisabled),
                contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                fillColor: AppColors.surfaceMuted,
                filled: true,
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(6),
                  borderSide: const BorderSide(color: AppColors.outlineLight),
                ),
                enabledBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(6),
                  borderSide: const BorderSide(color: AppColors.outlineLight),
                ),
                focusedBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(6),
                  borderSide: const BorderSide(color: AppColors.primary),
                ),
              ),
              textInputAction: TextInputAction.send,
              onSubmitted: (_) => onSend(),
              enabled: !isLoading,
            ),
          ),
          const SizedBox(width: 8),
          IconButton(
            onPressed: isLoading ? null : onSend,
            icon: const Icon(Icons.send_rounded),
            color: AppColors.primary,
            disabledColor: AppColors.textDisabled,
            tooltip: 'Send message',
          ),
        ],
      ),
    );
  }
}
