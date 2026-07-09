"""
Event handlers for quiz WebSocket actions.

Handles:
- useranswered: When a user answers a quiz question
- quiz_progress: Progress updates during quiz sessions
- leaderboard_update: Real-time leaderboard updates
"""

import logging
from typing import Dict, Any, Optional, Set
from datetime import datetime

from apps.api.websocket.manager import get_websocket_manager, WebSocketManager

logger = logging.getLogger(__name__)


class QuizEventHandler:
    """
    Handler for quiz-related WebSocket events.
    
    Provides methods to process and broadcast quiz events to
    connected clients in real-time.
    """
    
    def __init__(self, manager: Optional[WebSocketManager] = None):
        """
        Initialize quiz event handler.
        
        Args:
            manager: WebSocket manager instance (defaults to singleton)
        """
        self.manager = manager or get_websocket_manager()
    
    async def on_user_answered(
        self,
        quiz_session_id: str,
        user_id: str,
        question_id: str,
        selected_action: str,
        is_correct: bool,
        ev_loss: float,
        time_taken: float,
        current_leaderboard: Optional[list[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Handle a user answering a quiz question.
        
        Broadcasts the answer to all users in the session and triggers
        a leaderboard update.
        
        Args:
            quiz_session_id: Quiz session ID
            user_id: User who answered
            question_id: Question that was answered
            selected_action: Action selected by user
            is_correct: Whether the answer was correct
            ev_loss: Expected value loss from the decision
            time_taken: Time taken to answer in seconds
            current_leaderboard: Optional current leaderboard state
        
        Returns:
            Event data that was broadcast
        """
        logger.info(f"User {user_id} answered question {question_id} in session {quiz_session_id}")
        
        # Broadcast answer event to all session participants
        await self.manager.handle_quiz_user_answered(
            quiz_session_id=quiz_session_id,
            user_id=user_id,
            question_id=question_id,
            selected_action=selected_action,
            is_correct=is_correct,
            ev_loss=ev_loss,
            time_taken=time_taken
        )
        
        # If leaderboard provided, broadcast update immediately
        if current_leaderboard is not None:
            await self.manager.handle_leaderboard_update(
                quiz_session_id=quiz_session_id,
                leaderboard=current_leaderboard
            )
        
        return {
            "type": "quiz:user_answered",
            "quiz_session_id": quiz_session_id,
            "user_id": user_id,
            "question_id": question_id,
            "is_correct": is_correct,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    async def on_quiz_progress(
        self,
        quiz_session_id: str,
        question_index: int,
        total_questions: int,
        time_remaining: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Handle quiz progress update.
        
        Notifies all participants about the current question progress.
        
        Args:
            quiz_session_id: Quiz session ID
            question_index: Current question index (0-based)
            total_questions: Total number of questions in quiz
            time_remaining: Optional countdown timer for question
        
        Returns:
            Event data that was broadcast
        """
        logger.info(
            f"Quiz {quiz_session_id} progress: question {question_index + 1}/{total_questions}"
        )
        
        await self.manager.handle_quiz_progress(
            quiz_session_id=quiz_session_id,
            question_index=question_index,
            total_questions=total_questions,
            time_remaining=time_remaining
        )
        
        return {
            "type": "quiz:progress",
            "quiz_session_id": quiz_session_id,
            "question_index": question_index,
            "total_questions": total_questions,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    async def on_leaderboard_update(
        self,
        quiz_session_id: str,
        leaderboard: list[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Handle leaderboard update event.
        
        Broadcasts updated rankings to all participants.
        
        Args:
            quiz_session_id: Quiz session ID
            leaderboard: List of user rankings with user_id, score, accuracy, etc.
        
        Returns:
            Event data that was broadcast
        """
        logger.info(f"Leaderboard update for session {quiz_session_id}: {len(leaderboard)} participants")
        
        await self.manager.handle_leaderboard_update(
            quiz_session_id=quiz_session_id,
            leaderboard=leaderboard
        )
        
        return {
            "type": "quiz:leaderboard_update",
            "quiz_session_id": quiz_session_id,
            "leaderboard": leaderboard,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    async def on_quiz_complete(
        self,
        quiz_session_id: str,
        final_leaderboard: list[Dict[str, Any]],
        session_stats: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Handle quiz completion event.
        
        Broadcasts final results and session statistics to all participants.
        
        Args:
            quiz_session_id: Quiz session ID
            final_leaderboard: Final rankings after quiz ended
            session_stats: Session statistics (total questions, avg accuracy, etc.)
        
        Returns:
            Event data that was broadcast
        """
        logger.info(f"Quiz {quiz_session_id} completed with {len(final_leaderboard)} participants")
        
        await self.manager.handle_quiz_complete(
            quiz_session_id=quiz_session_id,
            final_leaderboard=final_leaderboard,
            session_stats=session_stats
        )
        
        return {
            "type": "quiz:complete",
            "quiz_session_id": quiz_session_id,
            "final_leaderboard": final_leaderboard,
            "session_stats": session_stats,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    async def on_user_joined(
        self,
        quiz_session_id: str,
        user_id: str,
        user_name: str,
        current_leaderboard: Optional[list[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Handle a user joining a quiz session.
        
        Notifies all participants about the new user and sends current state.
        
        Args:
            quiz_session_id: Quiz session ID
            user_id: User ID of joining user
            user_name: Display name of joining user
            current_leaderboard: Optional current leaderboard for quick sync
        
        Returns:
            Event data that was broadcast
        """
        message = {
            "type": "quiz:user_joined",
            "quiz_session_id": quiz_session_id,
            "user_id": user_id,
            "user_name": user_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        
        await self.manager.broadcast_to_quiz_session(quiz_session_id, message)
        
        # Send current leaderboard to the new user
        if current_leaderboard is not None:
            await self.manager.send_to_connection(
                self.manager._connections[quiz_session_id],  # Need to track this differently
                {
                    "type": "quiz:sync_state",
                    "quiz_session_id": quiz_session_id,
                    "leaderboard": current_leaderboard,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            )
        
        return message
    
    async def on_question_start(
        self,
        quiz_session_id: str,
        question_id: str,
        question_data: Dict[str, Any],
        time_limit: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Handle a new question starting.
        
        Broadcasts question details to all participants.
        
        Args:
            quiz_session_id: Quiz session ID
            question_id: New question ID
            question_data: Question details (hand, board, pot, etc.)
            time_limit: Optional time limit for answering
        
        Returns:
            Event data that was broadcast
        """
        message = {
            "type": "quiz:question_start",
            "quiz_session_id": quiz_session_id,
            "question_id": question_id,
            "question": question_data,
            "time_limit": time_limit,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        
        await self.manager.broadcast_to_quiz_session(quiz_session_id, message)
        
        return message


# Global handler instance
_quiz_handler: Optional[QuizEventHandler] = None


def get_quiz_handler() -> QuizEventHandler:
    """Get singleton QuizEventHandler instance."""
    global _quiz_handler
    if _quiz_handler is None:
        _quiz_handler = QuizEventHandler()
    return _quiz_handler


def broadcast_quiz_answer(
    quiz_session_id: str,
    user_id: str,
    question_id: str,
    selected_action: str,
    is_correct: bool,
    ev_loss: float,
    time_taken: float,
    current_leaderboard: Optional[list[Dict[str, Any]]] = None
):
    """
    Convenience function to broadcast a quiz answer event.
    
    This should be called when a quiz submission API receives an answer.
    """
    handler = get_quiz_handler()
    return handler.on_user_answered(
        quiz_session_id=quiz_session_id,
        user_id=user_id,
        question_id=question_id,
        selected_action=selected_action,
        is_correct=is_correct,
        ev_loss=ev_loss,
        time_taken=time_taken,
        current_leaderboard=current_leaderboard
    )


def broadcast_quiz_progress(
    quiz_session_id: str,
    question_index: int,
    total_questions: int,
    time_remaining: Optional[float] = None
):
    """
    Convenience function to broadcast quiz progress.
    """
    handler = get_quiz_handler()
    return handler.on_quiz_progress(
        quiz_session_id=quiz_session_id,
        question_index=question_index,
        total_questions=total_questions,
        time_remaining=time_remaining
    )


def broadcast_leaderboard_update(
    quiz_session_id: str,
    leaderboard: list[Dict[str, Any]]
):
    """
    Convenience function to broadcast leaderboard update.
    """
    handler = get_quiz_handler()
    return handler.on_leaderboard_update(
        quiz_session_id=quiz_session_id,
        leaderboard=leaderboard
    )


def broadcast_quiz_complete(
    quiz_session_id: str,
    final_leaderboard: list[Dict[str, Any]],
    session_stats: Dict[str, Any]
):
    """
    Convenience function to broadcast quiz completion.
    """
    handler = get_quiz_handler()
    return handler.on_quiz_complete(
        quiz_session_id=quiz_session_id,
        final_leaderboard=final_leaderboard,
        session_stats=session_stats
    )
