"""
Quiz WebSocket Router for real-time quiz events.

Provides WebSocket endpoint at /ws/quiz for:
- join_quiz_session: Join a quiz session room
- leave_quiz_session: Leave current session
- quiz_answer: Submit an answer (broadcast to room)
- request_leaderboard: Get current leaderboard

Broadcasts events to all session participants:
- quiz:user_answered
- quiz:progress
- quiz:leaderboard_update
- quiz:complete
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

# Module-level session storage
_sessions: Dict[str, "QuizSession"] = {}


class QuizSession:
    """Holds state for a single quiz session (room)."""
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.participants: Dict[WebSocket, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
    
    async def add_participant(self, ws: WebSocket, user_id: str, user_name: Optional[str] = None):
        """Add a participant to this session."""
        async with self._lock:
            self.participants[ws] = {
                "user_id": user_id,
                "user_name": user_name or user_id,
                "joined_at": datetime.now(timezone.utc).isoformat(),
            }
        logger.info(f"User {user_id} joined session {self.session_id}")
    
    async def remove_participant(self, ws: WebSocket) -> Optional[Dict[str, Any]]:
        """Remove a participant and return their info."""
        async with self._lock:
            return self.participants.pop(ws, None)
    
    async def broadcast(self, message: Dict[str, Any], exclude: Optional[WebSocket] = None):
        """Broadcast a message to all participants."""
        disconnected = []
        async with self._lock:
            participants = list(self.participants.items())
        
        for ws, info in participants:
            if ws is exclude:
                continue
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.append(ws)
        
        # Clean up dead connections
        for ws in disconnected:
            await self.remove_participant(ws)
    
    @property
    def leaderboard(self) -> list[Dict[str, Any]]:
        """Get current leaderboard from participants."""
        return [
            {"user_id": info["user_id"], "user_name": info["user_name"]}
            for ws, info in self.participants.items()
        ]


def get_or_create_session(session_id: str) -> QuizSession:
    """Get or create a quiz session."""
    if session_id not in _sessions:
        _sessions[session_id] = QuizSession(session_id)
    return _sessions[session_id]


async def cleanup_empty_session(session_id: str):
    """Remove session if empty."""
    if session_id in _sessions and not _sessions[session_id].participants:
        del _sessions[session_id]


async def websocket_handler(websocket: WebSocket):
    """
    Main WebSocket handler for quiz events.
    
    Connects to /ws/quiz and processes:
    - join_quiz_session: Join a session room
    - leave_quiz_session: Leave current room  
    - quiz_answer: Submit answer and broadcast
    - request_leaderboard: Send current leaderboard
    """
    await websocket.accept()
    
    current_session: Optional[QuizSession] = None
    user_info: Optional[Dict[str, Any]] = None
    
    try:
        while True:
            # Receive and parse message
            data = await websocket.receive_json()
            msg_type = data.get("type", "")
            
            if msg_type == "join_quiz_session":
                session_id = data.get("session_id")
                user_id = data.get("user_id", "anonymous")
                user_name = data.get("user_name", user_id)
                
                if not session_id:
                    await websocket.send_json({"type": "error", "message": "session_id required"})
                    continue
                
                # Leave old session if any
                if current_session and user_info:
                    await current_session.remove_participant(websocket)
                
                # Join new session
                current_session = get_or_create_session(session_id)
                await current_session.add_participant(websocket, user_id, user_name)
                user_info = {"user_id": user_id, "user_name": user_name}
                
                # Notify others
                await current_session.broadcast({
                    "type": "quiz:user_joined",
                    "user_id": user_id,
                    "user_name": user_name,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }, exclude=websocket)
                
                # Confirm join to sender
                await websocket.send_json({
                    "type": "session_joined",
                    "session_id": session_id,
                    "user_id": user_id,
                    "participant_count": len(current_session.participants),
                })
                
            elif msg_type == "leave_quiz_session":
                if current_session and user_info:
                    await current_session.remove_participant(websocket)
                    await current_session.broadcast({
                        "type": "quiz:user_left",
                        "user_id": user_info["user_id"],
                        "user_name": user_info["user_name"],
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                    await cleanup_empty_session(current_session.session_id)
                    current_session = None
                    user_info = None
                
                await websocket.send_json({"type": "session_left"})
            
            elif msg_type == "quiz_answer":
                if not current_session:
                    await websocket.send_json({"type": "error", "message": "not in a session"})
                    continue
                
                user_id = data.get("user_id", "")
                question_id = data.get("question_id", "")
                selected_action = data.get("selected_action", "")
                
                if not all([user_id, question_id, selected_action]):
                    await websocket.send_json({"type": "error", "message": "missing required fields"})
                    continue
                
                # Broadcast answer to all (including sender)
                answer_msg = {
                    "type": "quiz:user_answered",
                    "user_id": user_id,
                    "question_id": question_id,
                    "selected_action": selected_action,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                await current_session.broadcast(answer_msg)
                
                # Confirm to sender
                await websocket.send_json({
                    "type": "answer_received",
                    "question_id": question_id,
                })
            
            elif msg_type == "request_leaderboard":
                if current_session:
                    await websocket.send_json({
                        "type": "leaderboard",
                        "session_id": current_session.session_id,
                        "participants": current_session.leaderboard,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                else:
                    await websocket.send_json({
                        "type": "leaderboard",
                        "participants": [],
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
            
            else:
                await websocket.send_json({
                    "type": "error", 
                    "message": f"unknown message type: {msg_type}"
                })
    
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        # Cleanup on disconnect
        if current_session and user_info:
            await current_session.remove_participant(websocket)
            await current_session.broadcast({
                "type": "quiz:user_left",
                "user_id": user_info["user_id"],
                "user_name": user_info["user_name"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            await cleanup_empty_session(current_session.session_id)
