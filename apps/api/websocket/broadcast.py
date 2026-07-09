"""
Quiz broadcast utility for sending quiz events to connected WebSocket clients.

This module provides functions to broadcast real-time quiz events
to all clients connected to a specific quiz session. It integrates
with the WebSocket manager and Redis pub/sub for scalability.

Usage:
    from apps.api.websocket.broadcast import broadcast_answer, broadcast_leaderboard
    
    # When a user submits an answer
    await broadcast_answer(
        quiz_session_id="session-123",
        user_id="user-456",
        question_id="q-001",
        selected_action="raise",
        is_correct=True,
        ev_loss=0.0,
        time_taken=2.5
    )
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

from apps.api.websocket.manager import get_websocket_manager, WebSocketManager
from apps.api.websocket.handlers import (
    get_quiz_handler,
    QuizEventHandler,
)

logger = logging.getLogger(__name__)


class QuizBroadcaster:
    """
    Central broadcaster for quiz-related WebSocket events.
    
    This class provides a high-level interface for broadcasting
    quiz events to connected clients. It handles:
    - User answer events
    - Progress updates
    - Leaderboard updates
    - Quiz completion events
    
    All events are broadcast to all users in the specified quiz session.
    """
    
    def __init__(self, manager: Optional[WebSocketManager] = None):
        """
        Initialize QuizBroadcaster.
        
        Args:
            manager: Optional WebSocket manager instance
        """
        self._manager = manager
        self._handler: Optional[QuizEventHandler] = None
    
    @property
    def manager(self) -> WebSocketManager:
        """Get the WebSocket manager instance."""
        if self._manager is None:
            self._manager = get_websocket_manager()
        return self._manager
    
    @property
    def handler(self) -> QuizEventHandler:
        """Get the quiz event handler instance."""
        if self._handler is None:
            self._handler = get_quiz_handler()
        return self._handler
    
    async def broadcast_answer(
        self,
        quiz_session_id: str,
        user_id: str,
        question_id: str,
        selected_action: str,
        is_correct: bool,
        ev_loss: float,
        time_taken: float,
        leaderboard: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Broadcast a user answer event to all participants.
        
        Args:
            quiz_session_id: Quiz session ID
            user_id: User who submitted the answer
            question_id: Question that was answered
            selected_action: Action selected (raise/call/fold)
            is_correct: Whether the answer was correct
            ev_loss: Expected value loss from the decision
            time_taken: Time taken to answer in seconds
            leaderboard: Optional leaderboard to broadcast with answer
        
        Returns:
            The broadcast event data
        """
        logger.info(
            f"Broadcasting answer: user={user_id}, question={question_id}, "
            f"correct={is_correct}, session={quiz_session_id}"
        )
        
        return await self.handler.on_user_answered(
            quiz_session_id=quiz_session_id,
            user_id=user_id,
            question_id=question_id,
            selected_action=selected_action,
            is_correct=is_correct,
            ev_loss=ev_loss,
            time_taken=time_taken,
            current_leaderboard=leaderboard
        )
    
    async def broadcast_progress(
        self,
        quiz_session_id: str,
        question_index: int,
        total_questions: int,
        time_remaining: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Broadcast quiz progress update.
        
        Args:
            quiz_session_id: Quiz session ID
            question_index: Current question index (0-based)
            total_questions: Total number of questions
            time_remaining: Optional time remaining
        
        Returns:
            The broadcast event data
        """
        logger.info(
            f"Broadcasting progress: question {question_index + 1}/{total_questions}, "
            f"session={quiz_session_id}"
        )
        
        return await self.handler.on_quiz_progress(
            quiz_session_id=quiz_session_id,
            question_index=question_index,
            total_questions=total_questions,
            time_remaining=time_remaining
        )
    
    async def broadcast_leaderboard(
        self,
        quiz_session_id: str,
        leaderboard: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Broadcast leaderboard update.
        
        Args:
            quiz_session_id: Quiz session ID
            leaderboard: List of user rankings
        
        Returns:
            The broadcast event data
        """
        logger.info(
            f"Broadcasting leaderboard: {len(leaderboard)} participants, "
            f"session={quiz_session_id}"
        )
        
        return await self.handler.on_leaderboard_update(
            quiz_session_id=quiz_session_id,
            leaderboard=leaderboard
        )
    
    async def broadcast_complete(
        self,
        quiz_session_id: str,
        final_leaderboard: List[Dict[str, Any]],
        session_stats: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Broadcast quiz completion event.
        
        Args:
            quiz_session_id: Quiz session ID
            final_leaderboard: Final rankings
            session_stats: Optional session statistics
        
        Returns:
            The broadcast event data
        """
        stats = session_stats or {
            "total_participants": len(final_leaderboard),
            "quiz_session_id": quiz_session_id,
            "completed_at": datetime.now(timezone.utc).isoformat()
        }
        
        logger.info(f"Broadcasting quiz complete: session={quiz_session_id}")
        
        return await self.handler.on_quiz_complete(
            quiz_session_id=quiz_session_id,
            final_leaderboard=final_leaderboard,
            session_stats=stats
        )
    
    async def broadcast_question_start(
        self,
        quiz_session_id: str,
        question_id: str,
        question_data: Dict[str, Any],
        time_limit: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Broadcast new question event.
        
        Args:
            quiz_session_id: Quiz session ID
            question_id: Question ID
            question_data: Question details (hand, board, pot, etc.)
            time_limit: Optional time limit for answering
        
        Returns:
            The broadcast event data
        """
        logger.info(f"Broadcasting question start: {question_id}, session={quiz_session_id}")
        
        return await self.handler.on_question_start(
            quiz_session_id=quiz_session_id,
            question_id=question_id,
            question_data=question_data,
            time_limit=time_limit
        )
    
    async def broadcast_user_joined(
        self,
        quiz_session_id: str,
        user_id: str,
        user_name: str
    ) -> Dict[str, Any]:
        """
        Broadcast user joined event.
        
        Args:
            quiz_session_id: Quiz session ID
            user_id: User ID
            user_name: User display name
        
        Returns:
            The broadcast event data
        """
        logger.info(f"Broadcasting user joined: {user_id} ({user_name}), session={quiz_session_id}")
        
        return await self.handler.on_user_joined(
            quiz_session_id=quiz_session_id,
            user_id=user_id,
            user_name=user_name
        )


# Singleton instance
_quiz_broadcaster: Optional[QuizBroadcaster] = None


def get_quiz_broadcaster() -> QuizBroadcaster:
    """Get singleton QuizBroadcaster instance."""
    global _quiz_broadcaster
    if _quiz_broadcaster is None:
        _quiz_broadcaster = QuizBroadcaster()
    return _quiz_broadcaster


# Convenience functions for synchronous call patterns
# These create tasks that should be awaited or used with asyncio.create_task

async def broadcast_answer(
    quiz_session_id: str,
    user_id: str,
    question_id: str,
    selected_action: str,
    is_correct: bool,
    ev_loss: float,
    time_taken: float,
    leaderboard: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Broadcast a user answer event.
    
    Convenience function that uses the global QuizBroadcaster.
    """
    broadcaster = get_quiz_broadcaster()
    return await broadcaster.broadcast_answer(
        quiz_session_id=quiz_session_id,
        user_id=user_id,
        question_id=question_id,
        selected_action=selected_action,
        is_correct=is_correct,
        ev_loss=ev_loss,
        time_taken=time_taken,
        leaderboard=leaderboard
    )


async def broadcast_progress(
    quiz_session_id: str,
    question_index: int,
    total_questions: int,
    time_remaining: Optional[float] = None
) -> Dict[str, Any]:
    """
    Broadcast quiz progress update.
    """
    broadcaster = get_quiz_broadcaster()
    return await broadcaster.broadcast_progress(
        quiz_session_id=quiz_session_id,
        question_index=question_index,
        total_questions=total_questions,
        time_remaining=time_remaining
    )


async def broadcast_leaderboard(
    quiz_session_id: str,
    leaderboard: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Broadcast leaderboard update.
    """
    broadcaster = get_quiz_broadcaster()
    return await broadcaster.broadcast_leaderboard(
        quiz_session_id=quiz_session_id,
        leaderboard=leaderboard
    )


async def broadcast_complete(
    quiz_session_id: str,
    final_leaderboard: List[Dict[str, Any]],
    session_stats: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Broadcast quiz completion.
    """
    broadcaster = get_quiz_broadcaster()
    return await broadcaster.broadcast_complete(
        quiz_session_id=quiz_session_id,
        final_leaderboard=final_leaderboard,
        session_stats=session_stats
    )


async def broadcast_question_start(
    quiz_session_id: str,
    question_id: str,
    question_data: Dict[str, Any],
    time_limit: Optional[float] = None
) -> Dict[str, Any]:
    """
    Broadcast new question event.
    """
    broadcaster = get_quiz_broadcaster()
    return await broadcaster.broadcast_question_start(
        quiz_session_id=quiz_session_id,
        question_id=question_id,
        question_data=question_data,
        time_limit=time_limit
    )


async def broadcast_user_joined(
    quiz_session_id: str,
    user_id: str,
    user_name: str
) -> Dict[str, Any]:
    """
    Broadcast user joined event.
    """
    broadcaster = get_quiz_broadcaster()
    return await broadcaster.broadcast_user_joined(
        quiz_session_id=quiz_session_id,
        user_id=user_id,
        user_name=user_name
    )
