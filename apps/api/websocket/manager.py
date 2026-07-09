"""
WebSocket connection manager for real-time solver and quiz progress streaming.

Manages WebSocket connections with:
- Connection/disconnection handling
- Job-based room subscriptions
- Progress broadcasting
- Quiz event broadcasting
"""

import asyncio
import json
import logging
from typing import Dict, Set, Optional, Any, Callable
from datetime import datetime, timezone

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class ConnectionState:
    """Holds state for a single WebSocket connection."""
    
    def __init__(self, websocket: WebSocket, job_id: Optional[str] = None, user_id: Optional[str] = None):
        self.websocket = websocket
        self.job_id = job_id
        self.user_id = user_id
        self.connected_at = datetime.now(timezone.utc)
        self.quiz_session_id: Optional[str] = None


class WebSocketManager:
    """
    WebSocket connection manager for solver progress and quiz streaming.
    
    Features:
    - Multiple simultaneous connections
    - Job-based subscription rooms
    - Quiz session rooms for real-time leaderboards
    - Automatic reconnection handling
    - Progress event broadcasting
    """
    
    def __init__(self):
        """Initialize the WebSocket manager."""
        # Map of job_id -> set of connections subscribed to that job
        self._rooms: Dict[str, Set[ConnectionState]] = {}
        # Map of quiz_session_id -> set of connections in quiz room
        self._quiz_rooms: Dict[str, Set[ConnectionState]] = {}
        # All active connections
        self._connections: Dict[WebSocket, ConnectionState] = {}
        # Lock for thread-safe operations
        self._lock = asyncio.Lock()
    
    async def connect(self, websocket: WebSocket, job_id: Optional[str] = None, user_id: Optional[str] = None) -> bool:
        """
        Accept a new WebSocket connection and optionally subscribe to a job.
        
        Args:
            websocket: FastAPI WebSocket instance
            job_id: Optional job ID to subscribe to
            user_id: Optional user ID for quiz sessions
        
        Returns:
            True if connection successful
        """
        try:
            await websocket.accept()
            
            state = ConnectionState(websocket, job_id, user_id)
            
            async with self._lock:
                self._connections[websocket] = state
                
                if job_id:
                    if job_id not in self._rooms:
                        self._rooms[job_id] = set()
                    self._rooms[job_id].add(state)
            
            logger.info(f"WebSocket connected (job_id={job_id}, user_id={user_id})")
            
            # Send welcome message
            await websocket.send_json({
                "type": "connected",
                "job_id": job_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to accept WebSocket connection: {e}")
            return False

    async def disconnect(self, websocket: WebSocket):
        """
        Handle WebSocket disconnection.
        
        Args:
            websocket: The WebSocket that disconnected
        """
        async with self._lock:
            state = self._connections.pop(websocket, None)
            
            if state and state.job_id:
                room = self._rooms.get(state.job_id)
                if room:
                    room.discard(state)
                    if not room:
                        del self._rooms[state.job_id]
            
            # Remove from quiz room if applicable
            if state and state.quiz_session_id:
                quiz_room = self._quiz_rooms.get(state.quiz_session_id)
                if quiz_room:
                    quiz_room.discard(state)
                    if not quiz_room:
                        del self._quiz_rooms[state.quiz_session_id]
        
        logger.info(f"WebSocket disconnected (job_id={state.job_id if state else None})")
    
    async def subscribe(self, websocket: WebSocket, job_id: str):
        """
        Subscribe a connection to a job's progress updates.
        
        Args:
            websocket: WebSocket connection to subscribe
            job_id: Job ID to subscribe to
        """
        async with self._lock:
            state = self._connections.get(websocket)
            if state:
                # Remove from old room
                if state.job_id:
                    old_room = self._rooms.get(state.job_id)
                    if old_room:
                        old_room.discard(state)
                
                # Add to new room
                state.job_id = job_id
                if job_id not in self._rooms:
                    self._rooms[job_id] = set()
                self._rooms[job_id].add(state)
                
                logger.info(f"WebSocket subscribed to job {job_id}")
    
    async def join_quiz_session(self, websocket: WebSocket, quiz_session_id: str, user_id: Optional[str] = None):
        """
        Join a quiz quiz_session_id room for leaderboard and progress updates.
        
        Args:
            websocket: WebSocket connection
            quiz_session_id: Quiz session ID to join
            user_id: Optional user ID
        """
        async with self._lock:
            state = self._connections.get(websocket)
            if state:
                # Remove from old quiz room
                if state.quiz_session_id:
                    old_room = self._quiz_rooms.get(state.quiz_session_id)
                    if old_room:
                        old_room.discard(state)
                
                # Update user info
                if user_id:
                    state.user_id = user_id
                state.quiz_session_id = quiz_session_id
                
                # Add to new room
                if quiz_session_id not in self._quiz_rooms:
                    self._quiz_rooms[quiz_session_id] = set()
                self._quiz_rooms[quiz_session_id].add(state)
                
                logger.info(f"WebSocket joined quiz session {quiz_session_id}")
    
    async def leave_quiz_session(self, websocket: WebSocket):
        """
        Leave the current quiz session room.
        
        Args:
            websocket: WebSocket connection
        """
        async with self._lock:
            state = self._connections.get(websocket)
            if state and state.quiz_session_id:
                room = self._quiz_rooms.get(state.quiz_session_id)
                if room:
                    room.discard(state)
                    if not room:
                        del self._quiz_rooms[state.quiz_session_id]
                state.quiz_session_id = None
                
                logger.info("WebSocket left quiz session")
    
    async def unsubscribe(self, websocket: WebSocket):
        """
        Unsubscribe a connection from its current job.
        
        Args:
            websocket: WebSocket connection to unsubscribe
        """
        async with self._lock:
            state = self._connections.get(websocket)
            if state and state.job_id:
                room = self._rooms.get(state.job_id)
                if room:
                    room.discard(state)
                    if not room:
                        del self._rooms[state.job_id]
                state.job_id = None
                
                logger.info("WebSocket unsubscribed from job")
    
    async def broadcast_to_job(self, job_id: str, message: Dict[str, Any]):
        """
        Broadcast a message to all connections subscribed to a job.
        
        Args:
            job_id: Job ID to broadcast to
            message: Message data to send
        """
        room = self._rooms.get(job_id, set())
        disconnected = []
        
        for state in room:
            try:
                await state.websocket.send_json(message)
            except Exception as e:
                logger.warning(f"Failed to send to WebSocket: {e}")
                disconnected.append(state)
        
        # Clean up disconnected clients
        for state in disconnected:
            await self.disconnect(state.websocket)
    
    async def send_to_connection(self, websocket: WebSocket, message: Dict[str, Any]):
        """
        Send a message to a specific WebSocket connection.
        
        Args:
            websocket: Target WebSocket
            message: Message data to send
        """
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.warning(f"Failed to send to WebSocket: {e}")
            await self.disconnect(websocket)
    
    async def broadcast_all(self, message: Dict[str, Any]):
        """
        Broadcast a message to all connected clients.
        
        Args:
            message: Message data to send
        """
        disconnected = []
        
        async with self._lock:
            for websocket in self._connections:
                try:
                    await websocket.send_json(message)
                except Exception:
                    disconnected.append(websocket)
        
        # Clean up disconnected
        for websocket in disconnected:
            await self.disconnect(websocket)
    
    async def broadcast_to_quiz_session(self, quiz_session_id: str, message: Dict[str, Any]):
        """
        Broadcast a message to all connections in a quiz session.
        
        Args:
            quiz_session_id: Quiz session ID
            message: Message data to send
        """
        room = self._quiz_rooms.get(quiz_session_id, set())
        disconnected = []
        
        for state in room:
            try:
                await state.websocket.send_json(message)
            except Exception as e:
                logger.warning(f"Failed to send to WebSocket: {e}")
                disconnected.append(state)
        
        # Clean up disconnected clients
        for state in disconnected:
            await self.disconnect(state.websocket)
    
    @property
    def connection_count(self) -> int:
        """Get total number of active connections."""
        return len(self._connections)
    
    def get_room_size(self, job_id: str) -> int:
        """Get number of connections subscribed to a job."""
        return len(self._rooms.get(job_id, set()))
    
    def get_quiz_room_size(self, quiz_session_id: str) -> int:
        """Get number of connections in a quiz session."""
        return len(self._quiz_rooms.get(quiz_session_id, set()))
    
    async def handle_solver_progress(self, job_id: str, progress_data: Dict[str, Any]):
        """
        Handle incoming solver progress update.
        
        Called by the Redis pub/sub subscriber to broadcast progress.
        
        Args:
            job_id: Job ID
            progress_data: Progress update data
        """
        message = {
            "type": "solve:progress",
            "job_id": job_id,
            **progress_data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        
        await self.broadcast_to_job(job_id, message)
    
    async def handle_solver_complete(self, job_id: str, result_data: Dict[str, Any]):
        """
        Handle solver completion.
        
        Args:
            job_id: Job ID
            result_data: Final result data
        """
        message = {
            "type": "solve:complete",
            "job_id": job_id,
            **result_data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        
        await self.broadcast_to_job(job_id, message)
    
    # Quiz event handlers
    
    async def handle_quiz_user_answered(
        self, 
        quiz_session_id: str, 
        user_id: str, 
        question_id: str,
        selected_action: str,
        is_correct: bool,
        ev_loss: float,
        time_taken: float
    ):
        """
        Handle a user's answer to a quiz question.
        
        Broadcasts the answer to all users in the quiz session for real-time leaderboard updates.
        
        Args:
            quiz_session_id: Quiz session ID
            user_id: User who answered
            question_id: Question ID
            selected_action: The action the user selected
            is_correct: Whether the answer was correct
            ev_loss: EV loss from the decision
            time_taken: Time taken to answer in seconds
        """
        message = {
            "type": "quiz:user_answered",
            "quiz_session_id": quiz_session_id,
            "user_id": user_id,
            "question_id": question_id,
            "selected_action": selected_action,
            "is_correct": is_correct,
            "ev_loss": ev_loss,
            "time_taken": time_taken,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        
        await self.broadcast_to_quiz_session(quiz_session_id, message)
    
    async def handle_quiz_progress(
        self,
        quiz_session_id: str,
        question_index: int,
        total_questions: int,
        time_remaining: Optional[float] = None
    ):
        """
        Handle quiz progress update.
        
        Broadcasts current question progress to all users in the session.
        
        Args:
            quiz_session_id: Quiz session ID
            question_index: Current question index (0-based)
            total_questions: Total number of questions
            time_remaining: Optional time remaining for current question
        """
        message = {
            "type": "quiz:progress",
            "quiz_session_id": quiz_session_id,
            "question_index": question_index,
            "total_questions": total_questions,
            "time_remaining": time_remaining,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        
        await self.broadcast_to_quiz_session(quiz_session_id, message)
    
    async def handle_leaderboard_update(
        self,
        quiz_session_id: str,
        leaderboard: list[Dict[str, Any]]
    ):
        """
        Handle leaderboard update.
        
        Broadcasts updated leaderboard to all users in the session.
        
        Args:
            quiz_session_id: Quiz session ID
            leaderboard: List of user rankings with scores
        """
        message = {
            "type": "quiz:leaderboard_update",
            "quiz_session_id": quiz_session_id,
            "leaderboard": leaderboard,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        
        await self.broadcast_to_quiz_session(quiz_session_id, message)
    
    async def handle_quiz_complete(
        self,
        quiz_session_id: str,
        final_leaderboard: list[Dict[str, Any]],
        session_stats: Dict[str, Any]
    ):
        """
        Handle quiz completion.
        
        Broadcasts final results to all users in the session.
        
        Args:
            quiz_session_id: Quiz session ID
            final_leaderboard: Final rankings
            session_stats: Session statistics
        """
        message = {
            "type": "quiz:complete",
            "quiz_session_id": quiz_session_id,
            "final_leaderboard": final_leaderboard,
            "session_stats": session_stats,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        
        await self.broadcast_to_quiz_session(quiz_session_id, message)


# Global WebSocket manager instance
_ws_manager: Optional[WebSocketManager] = None


def get_websocket_manager() -> WebSocketManager:
    """Get singleton WebSocketManager instance."""
    global _ws_manager
    if _ws_manager is None:
        _ws_manager = WebSocketManager()
    return _ws_manager
