"""Message router for processing incoming WebSocket messages with streaming support."""

import asyncio
import time
import uuid
from typing import Dict, Any, Optional
from app.utils.logger import app_logger
from app.cognition.runtime import CognitiveRuntime
from backend.websocket_server import ws_manager


class MessageRouter:
    """Routes incoming WebSocket messages to appropriate handlers."""

    def __init__(self, runtime: CognitiveRuntime):
        self.runtime = runtime
        self._processing_tasks: Dict[str, asyncio.Task] = {}

        # Voice service will be injected after initialization
        self.voice_service = None

    def set_voice_service(self, voice_service):
        """Inject voice service for voice message handling."""
        self.voice_service = voice_service
        app_logger.info("Voice service injected into message router")

    async def handle_message(self, websocket, message: Dict[str, Any]):
        """Route incoming message to appropriate handler."""
        msg_type = message.get("type")

        handlers = {
            "user_message": self._handle_user_message,
            "join_conversation": self._handle_join_conversation,
            "create_conversation": self._handle_create_conversation,
            "list_conversations": self._handle_list_conversations,
            "delete_message": self._handle_delete_message,
            "voice_start": self._handle_voice_start,
            "voice_stop": self._handle_voice_stop,
            "voice_settings": self._handle_voice_settings,
        }

        handler = handlers.get(msg_type)
        if handler:
            await handler(websocket, message)
        else:
            app_logger.warning(f"Unknown message type: {msg_type}")

    async def _handle_user_message(self, websocket, message: Dict[str, Any]):
        """Handle user message with streaming response and action steps."""
        conversation_id = message.get("conversation_id")
        content = message.get("content")

        if not conversation_id or not content:
            if websocket:
                await ws_manager.send_to_connection(websocket, {
                    "type": "error",
                    "message": "Missing conversation_id or content"
                })
            return

        app_logger.info(f"Processing user message in {conversation_id}: {content[:50]}...")

        # Send acknowledgment
        await ws_manager.send_to_conversation(conversation_id, {
            "type": "message_ack",
            "conversation_id": conversation_id,
            "status": "processing"
        })

        try:
            # Generate action steps
            action_steps = self._generate_action_steps(content)

            # Send action steps as they "start"
            message_id = f"msg_{uuid.uuid4().hex[:12]}"

            for i, step in enumerate(action_steps):
                # Mark step as in_progress
                step["status"] = "in_progress"
                await ws_manager.send_to_conversation(conversation_id, {
                    "type": "action_step",
                    "conversation_id": conversation_id,
                    "message_id": message_id,
                    **step,
                })

                # Simulate work
                await asyncio.sleep(0.3)

                # Mark step as complete
                step["status"] = "complete"
                await ws_manager.send_to_conversation(conversation_id, {
                    "type": "action_step",
                    "conversation_id": conversation_id,
                    "message_id": message_id,
                    **step,
                })

            # Generate response with streaming tokens
            response_text = self._generate_response(content)
            tokens = response_text.split(" ")

            # Stream tokens
            for i, token in enumerate(tokens):
                token_with_space = token if i == 0 else f" {token}"
                is_done = i == len(tokens) - 1

                await ws_manager.send_to_conversation(conversation_id, {
                    "type": "message_token",
                    "conversation_id": conversation_id,
                    "message_id": message_id,
                    "token": token_with_space,
                    "done": is_done,
                })

                # Simulate typing delay
                await asyncio.sleep(0.03)

        except asyncio.CancelledError:
            app_logger.info(f"Message processing cancelled for {conversation_id}")
            raise
        except Exception as e:
            app_logger.error(f"Error processing message: {e}", exc_info=True)
            await ws_manager.send_to_conversation(conversation_id, {
                "type": "error",
                "conversation_id": conversation_id,
                "message": f"Error processing message: {str(e)}"
            })

    def _generate_action_steps(self, content: str) -> list:
        """Generate action steps based on message content."""
        content_lower = content.lower()
        steps = []

        # Analyze intent and generate appropriate steps
        if any(word in content_lower for word in ["code", "program", "function", "fix", "bug"]):
            steps = [
                {"id": f"step_{uuid.uuid4().hex[:8]}", "description": "Analyzing code context", "details": "Scanning relevant files"},
                {"id": f"step_{uuid.uuid4().hex[:8]}", "description": "Identifying issue", "details": "Pattern matching"},
                {"id": f"step_{uuid.uuid4().hex[:8]}", "description": "Generating solution", "details": None},
            ]
        elif any(word in content_lower for word in ["search", "find", "look"]):
            steps = [
                {"id": f"step_{uuid.uuid4().hex[:8]}", "description": "Searching files", "details": "Indexing workspace"},
                {"id": f"step_{uuid.uuid4().hex[:8]}", "description": "Filtering results", "details": None},
            ]
        elif any(word in content_lower for word in ["create", "new", "make", "build"]):
            steps = [
                {"id": f"step_{uuid.uuid4().hex[:8]}", "description": "Planning structure", "details": None},
                {"id": f"step_{uuid.uuid4().hex[:8]}", "description": "Creating content", "details": None},
                {"id": f"step_{uuid.uuid4().hex[:8]}", "description": "Validating output", "details": None},
            ]
        elif any(word in content_lower for word in ["explain", "what", "how", "why"]):
            steps = [
                {"id": f"step_{uuid.uuid4().hex[:8]}", "description": "Retrieving knowledge", "details": None},
                {"id": f"step_{uuid.uuid4().hex[:8]}", "description": "Composing explanation", "details": None},
            ]
        else:
            steps = [
                {"id": f"step_{uuid.uuid4().hex[:8]}", "description": "Processing request", "details": None},
                {"id": f"step_{uuid.uuid4().hex[:8]}", "description": "Generating response", "details": None},
            ]

        return steps

    def _generate_response(self, content: str) -> str:
        """Generate a response based on the message content."""
        content_lower = content.lower()

        if "hello" in content_lower or "hi" in content_lower:
            return "Hello! I'm Arena, your cognitive AI assistant. I can help you with code, research, file management, and much more. What would you like to work on?"
        elif "help" in content_lower:
            return "I can help you with:\n\n- **Code**: Writing, debugging, and reviewing code\n- **Research**: Finding information and summarizing topics\n- **Files**: Searching, organizing, and managing files\n- **Tasks**: Planning and tracking project work\n- **Questions**: Explaining concepts and answering questions\n\nJust ask me anything!"
        elif "code" in content_lower or "program" in content_lower:
            return "I'd be happy to help with code! To give you the best assistance, could you share:\n\n1. What language/framework you're working with\n2. What you're trying to accomplish\n3. Any error messages or issues you're seeing\n\nI'll analyze your context and provide a solution."
        elif "search" in content_lower or "find" in content_lower:
            return "I'll search your workspace for relevant files and information. The more specific your query, the better results I can provide. Try including file types, keywords, or directory paths."
        else:
            return f"I received your message: \"{content}\"\n\nI'm currently running in demo mode without the full cognitive runtime connected. In production, I would process this through the belief engine, world model, and goal verifier to provide a comprehensive response.\n\nTo enable full cognitive processing, connect the LLM backend and cognitive runtime services."

    async def _handle_join_conversation(self, websocket, message: Dict[str, Any]):
        """Handle joining a conversation."""
        conversation_id = message.get("conversation_id")

        if not conversation_id:
            await ws_manager.send_to_connection(websocket, {
                "type": "error",
                "message": "Missing conversation_id"
            })
            return

        await ws_manager.join_conversation(websocket, conversation_id)
        await ws_manager.send_to_connection(websocket, {
            "type": "conversation_joined",
            "conversation_id": conversation_id
        })

    async def _handle_create_conversation(self, websocket, message: Dict[str, Any]):
        """Handle creating a new conversation."""
        now = time.time()
        conversation_id = f"conv_{now}"

        await ws_manager.join_conversation(websocket, conversation_id)
        await ws_manager.send_to_connection(websocket, {
            "type": "conversation_created",
            "conversation_id": conversation_id,
            "title": message.get("title", "New Conversation")
        })

    async def _handle_list_conversations(self, websocket, message: Dict[str, Any]):
        """Handle listing active conversations."""
        conversations = ws_manager.get_active_conversations()
        await ws_manager.send_to_connection(websocket, {
            "type": "conversation_list",
            "conversations": conversations
        })

    async def _handle_delete_message(self, websocket, message: Dict[str, Any]):
        """Handle message deletion (client-side only, acknowledged)."""
        conversation_id = message.get("conversation_id")
        message_id = message.get("message_id")
        app_logger.info(f"Message delete requested: {message_id} in {conversation_id}")
        # Deletion is handled client-side in the store
        # This handler exists to acknowledge the request

    async def _handle_voice_start(self, websocket, message: Dict[str, Any]):
        """Handle starting voice input."""
        conversation_id = message.get("conversation_id")

        if not conversation_id:
            if websocket:
                await ws_manager.send_to_connection(websocket, {
                    "type": "error",
                    "message": "Missing conversation_id"
                })
            return

        app_logger.info(f"Voice start requested for conversation {conversation_id}")

        if self.voice_service:
            await self.voice_service.start(conversation_id)
        else:
            app_logger.warning("Voice service not available")
            if websocket:
                await ws_manager.send_to_connection(websocket, {
                    "type": "voice_status",
                    "conversation_id": conversation_id,
                    "status": "unavailable"
                })

    async def _handle_voice_stop(self, websocket, message: Dict[str, Any]):
        """Handle stopping voice input."""
        app_logger.info(f"Voice stop requested")
        if self.voice_service:
            await self.voice_service.stop()

    async def _handle_voice_settings(self, websocket, message: Dict[str, Any]):
        """Handle voice settings update from frontend."""
        settings = message.get("settings", {})
        app_logger.info(f"Voice settings update: {list(settings.keys())}")
        if self.voice_service:
            await self.voice_service.update_settings(settings)


# Global message router instance
message_router: Optional[MessageRouter] = None


def initialize_message_router(runtime: CognitiveRuntime):
    """Initialize the message router with the cognitive runtime."""
    global message_router
    message_router = MessageRouter(runtime)
    app_logger.info("Message router initialized")
