"""Message router for processing incoming WebSocket messages with LLM integration and streaming."""

import asyncio
import time
import uuid
from typing import Dict, Any, Optional, List
from app.utils.logger import app_logger
from app.cognition.runtime import CognitiveRuntime
from app.database import db
from backend.websocket_server import ws_manager


# System prompt for the AI assistant
SYSTEM_PROMPT = """You are Arena, an advanced cognitive AI assistant running locally on the user's PC.
You are helpful, knowledgeable, and concise. You can help with:
- Code: Writing, debugging, reviewing, and explaining code
- Research: Finding information and summarizing topics
- Files: Searching, organizing, and managing files
- Tasks: Planning and tracking project work
- Questions: Explaining concepts and answering questions

You have access to tools and a cognitive architecture that includes:
- A world model for understanding context
- A belief engine for reasoning
- Memory for recalling past conversations
- Goal tracking for multi-step tasks

Respond naturally and helpfully. Use markdown formatting when appropriate."""


# Conversation history storage (in-memory cache, persisted to SQLite)
_conversation_histories: Dict[str, List[Dict[str, str]]] = {}
MAX_HISTORY_MESSAGES = 50  # Keep last 50 messages per conversation


def get_conversation_history(conversation_id: str) -> List[Dict[str, str]]:
    """Get conversation history for a given conversation (SQLite-backed)."""
    if conversation_id not in _conversation_histories:
        # Load from persistent storage so history survives restarts.
        try:
            _conversation_histories[conversation_id] = db.get_conversation_messages(
                conversation_id, limit=MAX_HISTORY_MESSAGES
            )
        except Exception as e:
            app_logger.warning(f"Could not load conversation history: {e}")
            _conversation_histories[conversation_id] = []
    return _conversation_histories[conversation_id]


def add_to_history(conversation_id: str, role: str, content: str):
    """Add a message to conversation history (in-memory cache + SQLite persistence)."""
    history = get_conversation_history(conversation_id)
    history.append({"role": role, "content": content})
    # Trim to max size
    if len(history) > MAX_HISTORY_MESSAGES:
        _conversation_histories[conversation_id] = history[-MAX_HISTORY_MESSAGES:]
    # Persist to SQLite so the conversation survives restarts.
    try:
        db.add_conversation_message(conversation_id, role, content)
    except Exception as e:
        app_logger.warning(f"Could not persist conversation message: {e}")


class MessageRouter:
    """Routes incoming WebSocket messages to appropriate handlers."""

    def __init__(self, runtime: CognitiveRuntime):
        self.runtime = runtime
        self._processing_tasks: Dict[str, asyncio.Task] = {}
        self._rate_limits: Dict[str, List[float]] = {}  # conversation_id -> timestamps
        self._rate_limit_max = 30  # max messages per minute
        self._rate_limit_window = 60  # seconds

        # Voice service will be injected after initialization
        self.voice_service = None

    def set_voice_service(self, voice_service):
        """Inject voice service for voice message handling."""
        self.voice_service = voice_service
        app_logger.info("Voice service injected into message router")

    def _check_rate_limit(self, conversation_id: str) -> bool:
        """Check if conversation has exceeded rate limit. Returns True if allowed."""
        now = time.time()
        if conversation_id not in self._rate_limits:
            self._rate_limits[conversation_id] = []

        # Clean old entries
        self._rate_limits[conversation_id] = [
            t for t in self._rate_limits[conversation_id]
            if now - t < self._rate_limit_window
        ]

        if len(self._rate_limits[conversation_id]) >= self._rate_limit_max:
            return False

        self._rate_limits[conversation_id].append(now)
        return True

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
            "wake_word_detected": self._handle_wake_word_detected,
            "action_approval": self._handle_action_approval,
            "get_history": self._handle_get_history,
        }

        handler = handlers.get(msg_type)
        if handler:
            return await handler(websocket, message)
        else:
            app_logger.warning(f"Unknown message type: {msg_type}")
            return None

    async def _handle_user_message(self, websocket, message: Dict[str, Any]):
        """Handle user message with LLM-powered streaming response (now multimodal).

        P2 AGI: Accepts optional image_path, audio_path, attachments so chat can be
        multimodal (text + vision + files) through the ONE cognitive runtime.
        """
        conversation_id = message.get("conversation_id")
        content = message.get("content")
        image_path = message.get("image_path") or message.get("image") or None
        audio_path = message.get("audio_path") or None
        attachments = message.get("attachments") or []

        if not conversation_id or not content:
            if websocket:
                await ws_manager.send_to_connection(websocket, {
                    "type": "error",
                    "message": "Missing conversation_id or content"
                })
            return

        # Rate limiting
        if not self._check_rate_limit(conversation_id):
            await ws_manager.send_to_conversation(conversation_id, {
                "type": "error",
                "conversation_id": conversation_id,
                "message": "Rate limit exceeded. Please wait a moment before sending another message."
            })
            return

        app_logger.info(f"Processing user message in {conversation_id}: {content[:80]}...")

        # Delivery guarantee: the sender's socket joins the conversation it is
        # messaging. Clients may send to a room they never joined (e.g. a
        # native client selecting a server-side conversation); without this,
        # replies stream to an empty room and the sender hangs on "thinking".
        if websocket is not None:
            try:
                await ws_manager.join_conversation(websocket, conversation_id)
            except Exception as exc:
                app_logger.warning(f"Could not join sender to {conversation_id}: {exc}")

        # Send acknowledgment
        await ws_manager.send_to_conversation(conversation_id, {
            "type": "message_ack",
            "conversation_id": conversation_id,
            "status": "processing"
        })

        # Store user message in history
        add_to_history(conversation_id, "user", content)

        message_id = f"msg_{uuid.uuid4().hex[:12]}"

        # Cross-client sync: broadcast the question to the room so every
        # client (web tabs, desktop) renders messages from the others, not
        # just the replies. Named room_message to avoid the client->server
        # user_message type; clients dedupe their own pending copy.
        await ws_manager.send_to_conversation(conversation_id, {
            "type": "room_message",
            "conversation_id": conversation_id,
            "message_id": message_id,
            "content": content,
        })

        try:
            # Generate action steps based on content analysis
            action_steps = self._generate_action_steps(content)

            # Send action steps as they progress
            for step in action_steps:
                step["status"] = "in_progress"
                await ws_manager.send_to_conversation(conversation_id, {
                    "type": "action_step",
                    "conversation_id": conversation_id,
                    "message_id": message_id,
                    **step,
                })
                await asyncio.sleep(0.2)

                step["status"] = "complete"
                await ws_manager.send_to_conversation(conversation_id, {
                    "type": "action_step",
                    "conversation_id": conversation_id,
                    "message_id": message_id,
                    **step,
                })

            # Build messages for LLM with conversation history
            history = get_conversation_history(conversation_id)
            llm_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
            llm_messages.extend(history)

            # Route through the authoritative cognitive runtime (world model, beliefs,
            # reasoning loop, goal verification, memory) rather than a raw LLM call.
            # P2: Pass multimodal context (image_path, attachments) so vision is grounded
            response_text = await self._call_cognitive_runtime(
                content,
                image_path=image_path,
                audio_path=audio_path,
                attachments=attachments,
            )

            # Surface the exact pending scope to the owner. This event is only a
            # request; approval mints a separate short-lived authorization grant.
            try:
                from app.cognition.approval_store import approval_store
                pending = [
                    req for req in approval_store.list_pending()
                    if req.conversation_id == conversation_id
                ]
                if pending:
                    latest = max(pending, key=lambda req: req.created_at)
                    await ws_manager.send_to_conversation(conversation_id, {
                        "type": "approval_request",
                        "conversation_id": conversation_id,
                        **latest.to_dict(),
                    })
            except Exception as exc:
                app_logger.warning(f"Could not surface approval request: {exc}")

            # Stream response tokens to client
            tokens = self._tokenize_response(response_text) or [" "]
            for i, token in enumerate(tokens):
                is_done = i == len(tokens) - 1
                await ws_manager.send_to_conversation(conversation_id, {
                    "type": "message_token",
                    "conversation_id": conversation_id,
                    "message_id": message_id,
                    "token": token,
                    "done": is_done,
                })
                await asyncio.sleep(0.02)  # Simulate natural typing speed

            # Store assistant response in history
            add_to_history(conversation_id, "assistant", response_text)
            return response_text

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
            return None

    async def _call_cognitive_runtime(
        self,
        content: str,
        image_path: Optional[str] = None,
        audio_path: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Route the message through CognitiveRuntime (the authoritative cognitive path).

        Runs the full closed-loop cycle (perceive → reason → plan → execute → verify →
        replan → learn) in a worker thread, then returns the assistant reply for streaming.

        P2 AGI: Now accepts multimodal inputs (image_path, attachments) so chat can be
        vision-grounded, not text-only.
        """
        try:
            # Conversational routing (live-hardware lesson): a thinking-class
            # main model (e.g. Qwen3-14B on CPU, ~7.7 tok/s) takes minutes for
            # simple chat and can exhaust the token budget on internal
            # reasoning. Short conversational turns with no attachments go to
            # the fast model; substantial requests keep the full main path.
            complexity = "main"
            if (
                not image_path
                and not audio_path
                and not attachments
                and len(content) <= 280
                and not any(marker in content for marker in ("```", "plan", "analyze", "design", "debug"))
            ):
                complexity = "fast"
            result = await asyncio.to_thread(
                self.runtime.process_cognitive_cycle,
                user_text=content,
                complexity=complexity,
                image_path=image_path,
                audio_path=audio_path,
                attachments=attachments,
            )

            if not isinstance(result, dict):
                return "I couldn't produce a response from my cognitive engine."

            reply = result.get("assistant_reply") or result.get("reply") or ""
            if reply:
                return reply

            # Cycle succeeded but produced no reply — surface the lifecycle state.
            state = result.get("goal_lifecycle_state", "unknown")
            return f"[cognitive cycle complete — goal state: {state}]"

        except Exception as e:
            app_logger.error(f"Cognitive runtime processing failed: {e}", exc_info=True)
            return (
                "I'm having trouble processing that request through my cognitive engine.\n\n"
                f"Error: {str(e)}"
            )

    def _tokenize_response(self, text: str) -> List[str]:
        """Split response text into tokens for streaming.

        Splits on word boundaries while preserving whitespace and formatting.
        """
        tokens = []
        current = ""

        for char in text:
            current += char
            # Emit token on word boundary or after certain length
            if char in (' ', '\n') and len(current) >= 2:
                tokens.append(current)
                current = ""
            elif len(current) >= 20:
                tokens.append(current)
                current = ""

        if current:
            tokens.append(current)

        # Ensure we have at least one token
        if not tokens:
            tokens = [text]

        return tokens

    def _generate_action_steps(self, content: str) -> list:
        """Generate action steps based on message content analysis."""
        content_lower = content.lower()

        if any(word in content_lower for word in ["code", "program", "function", "fix", "bug", "debug"]):
            return [
                {"id": f"step_{uuid.uuid4().hex[:8]}", "description": "Analyzing code context", "details": "Scanning relevant files"},
                {"id": f"step_{uuid.uuid4().hex[:8]}", "description": "Formulating solution", "details": None},
            ]
        elif any(word in content_lower for word in ["search", "find", "look", "research"]):
            return [
                {"id": f"step_{uuid.uuid4().hex[:8]}", "description": "Searching knowledge base", "details": None},
                {"id": f"step_{uuid.uuid4().hex[:8]}", "description": "Synthesizing results", "details": None},
            ]
        elif any(word in content_lower for word in ["create", "new", "make", "build", "write"]):
            return [
                {"id": f"step_{uuid.uuid4().hex[:8]}", "description": "Planning approach", "details": None},
                {"id": f"step_{uuid.uuid4().hex[:8]}", "description": "Generating content", "details": None},
            ]
        elif any(word in content_lower for word in ["explain", "what", "how", "why", "describe"]):
            return [
                {"id": f"step_{uuid.uuid4().hex[:8]}", "description": "Retrieving knowledge", "details": None},
                {"id": f"step_{uuid.uuid4().hex[:8]}", "description": "Composing explanation", "details": None},
            ]
        else:
            return [
                {"id": f"step_{uuid.uuid4().hex[:8]}", "description": "Processing request", "details": None},
                {"id": f"step_{uuid.uuid4().hex[:8]}", "description": "Generating response", "details": None},
            ]

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
        # Use client-provided ID if available, otherwise generate one
        conversation_id = message.get("conversation_id") or f"conv_{time.time()}"
        title = message.get("title", "New Conversation")

        # Initialize empty history
        _conversation_histories[conversation_id] = []

        await ws_manager.join_conversation(websocket, conversation_id)
        await ws_manager.send_to_connection(websocket, {
            "type": "conversation_created",
            "conversation_id": conversation_id,
            "title": title
        })

    async def _handle_list_conversations(self, websocket, message: Dict[str, Any]):
        """Handle listing conversations (SQLite-persisted, merged with active connections)."""
        # Load persisted conversations from SQLite so history survives restarts.
        try:
            previews = db.get_conversation_previews(limit=50)
        except Exception as e:
            app_logger.warning(f"Could not load persisted conversations: {e}")
            previews = []

        # Merge in any active WebSocket conversations not yet persisted.
        try:
            active_ids = set(ws_manager.get_active_conversations())
            known_ids = {p["id"] for p in previews}
            for cid in active_ids - known_ids:
                previews.append({
                    "id": cid,
                    "title": "New Conversation",
                    "lastMessage": "",
                    "updatedAt": "",
                })
        except Exception as e:
            app_logger.warning(f"Could not merge active conversations: {e}")

        await ws_manager.send_to_connection(websocket, {
            "type": "conversation_list",
            "conversations": previews
        })

    async def _handle_delete_message(self, websocket, message: Dict[str, Any]):
        """Handle message deletion (client-side only, acknowledged)."""
        conversation_id = message.get("conversation_id")
        message_id = message.get("message_id")
        app_logger.info(f"Message delete requested: {message_id} in {conversation_id}")

    async def _handle_get_history(self, websocket, message: Dict[str, Any]):
        """Handle request for conversation history."""
        conversation_id = message.get("conversation_id")
        if not conversation_id:
            return

        history = get_conversation_history(conversation_id)
        await ws_manager.send_to_connection(websocket, {
            "type": "conversation_history",
            "conversation_id": conversation_id,
            "messages": history
        })

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
        app_logger.info("Voice stop requested")
        if self.voice_service:
            await self.voice_service.stop()

    async def _handle_voice_settings(self, websocket, message: Dict[str, Any]):
        """Handle voice settings update from frontend."""
        settings = message.get("settings", {})
        app_logger.info(f"Voice settings update: {list(settings.keys())}")
        if self.voice_service:
            await self.voice_service.update_settings(settings)

    async def _handle_wake_word_detected(self, websocket, message: Dict[str, Any]):
        """Handle a wake word detected on a remote device (Android on-device wake word)."""
        conversation_id = message.get("conversation_id")
        if not conversation_id:
            app_logger.warning("wake_word_detected without conversation_id")
            return

        if self.voice_service:
            await self.voice_service.notify_wake_word(conversation_id)
        else:
            app_logger.warning("Voice service not available; wake word ignored")

    async def _handle_action_approval(self, websocket, message: Dict[str, Any]):
        """Handle an owner's approve/deny of a pending Level-3 action."""
        action_id = message.get("actionId") or message.get("action_id")
        approved = bool(message.get("approved", False))
        note = message.get("reason", "")

        if not action_id:
            app_logger.warning("action_approval without actionId")
            return

        from app.cognition.approval_store import approval_store
        req = approval_store.decide(action_id, approved, note)

        if req is None:
            app_logger.warning(f"action_approval for unknown action_id '{action_id}'")
            if websocket:
                await ws_manager.send_to_connection(websocket, {
                    "type": "approval_result",
                    "action_id": action_id,
                    "status": "not_found",
                })
            return

        app_logger.info(
            f"Owner {'approved' if approved else 'denied'} action '{req.action_type}' ({action_id})"
        )
        if websocket:
            await ws_manager.send_to_connection(websocket, {
                "type": "approval_result",
                "action_id": action_id,
                "status": "approved" if approved else "denied",
                "authorization_id": req.authorization_id,
                "authorization_scope": {
                    "action_type": req.action_type,
                    "payload": req.payload,
                    "single_use": True,
                } if req.authorization_id else None,
            })


# Global message router instance
message_router: Optional[MessageRouter] = None


def initialize_message_router(runtime: CognitiveRuntime):
    """Initialize the message router with the cognitive runtime."""
    global message_router
    message_router = MessageRouter(runtime)
    app_logger.info("Message router initialized with LLM integration")
