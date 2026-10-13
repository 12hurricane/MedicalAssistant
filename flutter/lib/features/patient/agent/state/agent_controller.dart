import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/api/api_endpoints.dart';
import '../../../../core/providers.dart';

class ChatMessage {
  final String text;
  final bool isUser;
  
  ChatMessage({required this.text, required this.isUser});
}

class AgentState {
  final List<ChatMessage> messages;
  final bool isLoading;
  final String? error;

  AgentState({
    this.messages = const [],
    this.isLoading = false,
    this.error,
  });

  AgentState copyWith({
    List<ChatMessage>? messages,
    bool? isLoading,
    String? error,
  }) {
    return AgentState(
      messages: messages ?? this.messages,
      isLoading: isLoading ?? this.isLoading,
      error: error, // explicit nulling is fine here since errors are transient
    );
  }
}

final agentControllerProvider = NotifierProvider.autoDispose<AgentController, AgentState>(
  AgentController.new,
);

class AgentController extends AutoDisposeNotifier<AgentState> {
  @override
  AgentState build() {
    return AgentState(
      messages: [
        ChatMessage(
          text: "Hi there! I'm your MedAssist AI. How can I help you with your medications today?",
          isUser: false,
        ),
      ],
    );
  }

  Future<void> sendMessage(String text) async {
    if (text.trim().isEmpty) return;

    final userMessage = ChatMessage(text: text, isUser: true);
    state = state.copyWith(
      messages: [...state.messages, userMessage],
      isLoading: true,
      error: null,
    );

    try {
      final client = ref.read(apiClientProvider);
      final response = await client.postObject(
        ApiEndpoints.agentChat,
        body: {'message': text},
        decode: (json) => json['response'] as String,
      );

      final aiMessage = ChatMessage(text: response, isUser: false);
      state = state.copyWith(
        messages: [...state.messages, aiMessage],
        isLoading: false,
      );
    } catch (e) {
      state = state.copyWith(
        isLoading: false,
        error: "Failed to connect to the AI Agent. Please try again later.",
      );
    }
  }
}
