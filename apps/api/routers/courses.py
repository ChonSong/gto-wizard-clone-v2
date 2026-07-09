"""
Training courses API router.

Provides endpoints for:
- Listing and retrieving courses with filters
- CRUD operations for courses and lessons
- User progress tracking through courses
- Course enrollment and completion tracking
"""

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from apps.api.services.database import get_session_context
from apps.api.models.course_models import Course, Lesson, UserProgress
from apps.api.services.cache import cached

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/courses", tags=["courses"])


# === REQUEST/RESPONSE MODELS ===


class CourseCreate(BaseModel):
    """Request model for creating a course."""

    title: str = Field(..., description="Course title")
    description: Optional[str] = Field(None, description="Course description")
    short_description: Optional[str] = Field(None, description="Short description for cards")
    thumbnail_url: Optional[str] = None
    game_type: str = Field("nlh", description="Game type: nlh, plo4, plo6, omaha")
    difficulty: str = Field("beginner", description="Difficulty: beginner, intermediate, advanced")
    category: str = Field("general", description="Category: preflop, postflop, mental_game, etc.")
    duration_minutes: int = Field(0, ge=0)
    is_published: bool = Field(False)
    is_featured: bool = Field(False)
    prerequisites: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    author: str = Field("GTO Wizard")


class CourseUpdate(BaseModel):
    """Request model for updating a course."""

    title: Optional[str] = None
    description: Optional[str] = None
    short_description: Optional[str] = None
    thumbnail_url: Optional[str] = None
    game_type: Optional[str] = None
    difficulty: Optional[str] = None
    category: Optional[str] = None
    duration_minutes: Optional[int] = None
    is_published: Optional[bool] = None
    is_featured: Optional[bool] = None
    prerequisites: Optional[List[str]] = None
    tags: Optional[List[str]] = None


class LessonCreate(BaseModel):
    """Request model for creating a lesson."""

    course_id: str = Field(..., description="Course ID")
    title: str = Field(..., description="Lesson title")
    content: Optional[str] = Field(None, description="Lesson content (markdown/html)")
    content_type: str = Field("text", description="Content type: text, video, quiz, interactive")
    video_url: Optional[str] = None
    order_index: int = Field(0, ge=0)
    duration_minutes: int = Field(0, ge=0)
    is_preview: bool = Field(False)
    quiz_data: Optional[Dict[str, Any]] = None


class LessonUpdate(BaseModel):
    """Request model for updating a lesson."""

    title: Optional[str] = None
    content: Optional[str] = None
    content_type: Optional[str] = None
    video_url: Optional[str] = None
    order_index: Optional[int] = None
    duration_minutes: Optional[int] = None
    is_preview: Optional[bool] = None
    quiz_data: Optional[Dict[str, Any]] = None


class UserProgressUpdate(BaseModel):
    """Request model for updating user progress."""

    status: Optional[str] = Field(None, description="Status: not_started, in_progress, completed")
    progress_percent: Optional[float] = Field(None, ge=0.0, le=100.0)
    time_spent_minutes: Optional[int] = Field(None, ge=0)
    quiz_score: Optional[float] = Field(None, ge=0.0, le=100.0)


class CourseResponse(BaseModel):
    """Response model for a course."""

    id: str
    title: str
    description: Optional[str] = None
    short_description: Optional[str] = None
    thumbnail_url: Optional[str] = None
    game_type: str
    difficulty: str
    category: str
    duration_minutes: int
    lesson_count: int
    is_published: bool
    is_featured: bool
    prerequisites: List[str] = []
    tags: List[str] = []
    author: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class CourseDetailResponse(CourseResponse):
    """Response model for a course with lessons."""

    lessons: List[Dict[str, Any]] = []


class LessonResponse(BaseModel):
    """Response model for a lesson."""

    id: str
    course_id: str
    title: str
    content: Optional[str] = None
    content_type: str
    video_url: Optional[str] = None
    order_index: int
    duration_minutes: int
    is_preview: bool
    quiz_data: Optional[Dict[str, Any]] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class UserProgressResponse(BaseModel):
    """Response model for user progress."""

    id: Optional[str] = None
    user_id: str
    course_id: str
    lesson_id: str
    status: str
    progress_percent: float
    time_spent_minutes: int
    quiz_score: Optional[float] = None
    completed_at: Optional[str] = None
    last_accessed_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class CourseListResponse(BaseModel):
    """Response for listing courses."""

    courses: List[CourseResponse]
    total: int
    offset: int
    limit: int


class UserCourseProgressResponse(BaseModel):
    """Response for user's progress in a course."""

    course_id: str
    course_title: str
    overall_progress: float
    lessons_completed: int
    total_lessons: int
    lessons: List[UserProgressResponse]


# === COURSE ENDPOINTS ===


@router.post("", response_model=CourseResponse, status_code=201)
async def create_course(request: CourseCreate) -> Dict[str, Any]:
    """Create a new course."""
    async with get_session_context() as session:
        course = Course(
            title=request.title,
            description=request.description,
            short_description=request.short_description,
            thumbnail_url=request.thumbnail_url,
            game_type=request.game_type,
            difficulty=request.difficulty,
            category=request.category,
            duration_minutes=request.duration_minutes,
            is_published=request.is_published,
            is_featured=request.is_featured,
            prerequisites=request.prerequisites,
            tags=request.tags,
            author=request.author,
        )
        session.add(course)
        await session.flush()
        await session.refresh(course)
        return course.to_dict()


@router.get("", response_model=CourseListResponse)
@cached(ttl=300)
async def list_courses(
    game_type: Optional[str] = Query(None, description="Filter by game type"),
    difficulty: Optional[str] = Query(None, description="Filter by difficulty"),
    category: Optional[str] = Query(None, description="Filter by category"),
    is_published: Optional[bool] = Query(None, description="Filter by published status"),
    is_featured: Optional[bool] = Query(None, description="Filter by featured"),
    tags: Optional[str] = Query(None, description="Comma-separated tags to filter by"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> Dict[str, Any]:
    """List all courses with optional filters."""
    async with get_session_context() as session:
        # Build query
        query = select(Course)
        count_query = select(func.count(Course.id))

        if game_type:
            query = query.where(Course.game_type == game_type)
            count_query = count_query.where(Course.game_type == game_type)
        if difficulty:
            query = query.where(Course.difficulty == difficulty)
            count_query = count_query.where(Course.difficulty == difficulty)
        if category:
            query = query.where(Course.category == category)
            count_query = count_query.where(Course.category == category)
        if is_published is not None:
            query = query.where(Course.is_published == is_published)
            count_query = count_query.where(Course.is_published == is_published)
        if is_featured is not None:
            query = query.where(Course.is_featured == is_featured)
            count_query = count_query.where(Course.is_featured == is_featured)

        # Get total count
        total_result = await session.execute(count_query)
        total = total_result.scalar() or 0

        # Apply pagination
        query = query.order_by(Course.created_at.desc()).offset(offset).limit(limit)
        result = await session.execute(query)
        courses = result.scalars().all()

        return {
            "courses": [c.to_dict() for c in courses],
            "total": total,
            "offset": offset,
            "limit": limit,
        }


@router.get("/featured", response_model=CourseListResponse)
@cached(ttl=300)
async def list_featured_courses(
    limit: int = Query(10, ge=1, le=50),
) -> Dict[str, Any]:
    """List featured courses."""
    async with get_session_context() as session:
        query = (
            select(Course)
            .where(Course.is_featured == True, Course.is_published == True)
            .order_by(Course.created_at.desc())
            .limit(limit)
        )

        result = await session.execute(query)
        courses = result.scalars().all()

        return {
            "courses": [c.to_dict() for c in courses],
            "total": len(courses),
            "offset": 0,
            "limit": limit,
        }


@router.get("/categories", response_model=Dict[str, List[str]])
@cached(ttl=600)
async def get_categories() -> Dict[str, List[str]]:
    """Get all available course metadata."""
    async with get_session_context() as session:
        # Get unique categories
        cat_result = await session.execute(
            select(Course.category).distinct().where(Course.is_published == True)
        )
        categories = [r[0] for r in cat_result.fetchall()]

        # Get unique difficulties
        diff_result = await session.execute(
            select(Course.difficulty).distinct().where(Course.is_published == True)
        )
        difficulties = [r[0] for r in diff_result.fetchall()]

        # Get unique game types
        game_result = await session.execute(
            select(Course.game_type).distinct().where(Course.is_published == True)
        )
        game_types = [r[0] for r in game_result.fetchall()]

        return {
            "categories": sorted(categories),
            "difficulties": sorted(difficulties),
            "game_types": sorted(game_types),
        }


@router.get("/{course_id}", response_model=CourseDetailResponse)
async def get_course(course_id: str) -> Dict[str, Any]:
    """Get a single course by ID with its lessons."""
    async with get_session_context() as session:
        query = select(Course).options(selectinload(Course.lessons)).where(Course.id == course_id)
        result = await session.execute(query)
        course = result.scalar_one_or_none()

        if not course:
            raise HTTPException(status_code=404, detail=f"Course not found: {course_id}")

        course_dict = course.to_dict()
        course_dict["lessons"] = sorted(
            [l.to_dict() for l in course.lessons], key=lambda x: x["order_index"]
        )
        return course_dict


@router.put("/{course_id}", response_model=CourseResponse)
async def update_course(course_id: str, request: CourseUpdate) -> Dict[str, Any]:
    """Update an existing course."""
    async with get_session_context() as session:
        query = select(Course).where(Course.id == course_id)
        result = await session.execute(query)
        course = result.scalar_one_or_none()

        if not course:
            raise HTTPException(status_code=404, detail=f"Course not found: {course_id}")

        # Update fields
        update_fields = [
            "title",
            "description",
            "short_description",
            "thumbnail_url",
            "game_type",
            "difficulty",
            "category",
            "duration_minutes",
            "is_published",
            "is_featured",
            "prerequisites",
            "tags",
        ]
        for field in update_fields:
            value = getattr(request, field, None)
            if value is not None:
                setattr(course, field, value)

        await session.flush()
        await session.refresh(course)
        return course.to_dict()


@router.delete("/{course_id}")
async def delete_course(course_id: str) -> Dict[str, str]:
    """Delete a course and all its lessons."""
    async with get_session_context() as session:
        query = select(Course).where(Course.id == course_id)
        result = await session.execute(query)
        course = result.scalar_one_or_none()

        if not course:
            raise HTTPException(status_code=404, detail=f"Course not found: {course_id}")

        await session.delete(course)
        return {"status": "deleted", "id": course_id}


# === LESSON ENDPOINTS ===


@router.post("/lessons", response_model=LessonResponse, status_code=201)
async def create_lesson(request: LessonCreate) -> Dict[str, Any]:
    """Create a new lesson within a course."""
    async with get_session_context() as session:
        # Verify course exists
        course_query = select(Course).where(Course.id == request.course_id)
        course_result = await session.execute(course_query)
        course = course_result.scalar_one_or_none()

        if not course:
            raise HTTPException(status_code=404, detail=f"Course not found: {request.course_id}")

        lesson = Lesson(
            course_id=request.course_id,
            title=request.title,
            content=request.content,
            content_type=request.content_type,
            video_url=request.video_url,
            order_index=request.order_index,
            duration_minutes=request.duration_minutes,
            is_preview=request.is_preview,
            quiz_data=request.quiz_data,
        )
        session.add(lesson)

        # Update course lesson count
        course.lesson_count = (course.lesson_count or 0) + 1

        await session.flush()
        await session.refresh(lesson)
        return lesson.to_dict()


@router.get("/lessons/{lesson_id}", response_model=LessonResponse)
async def get_lesson(lesson_id: str) -> Dict[str, Any]:
    """Get a single lesson by ID."""
    async with get_session_context() as session:
        query = select(Lesson).where(Lesson.id == lesson_id)
        result = await session.execute(query)
        lesson = result.scalar_one_or_none()

        if not lesson:
            raise HTTPException(status_code=404, detail=f"Lesson not found: {lesson_id}")

        return lesson.to_dict()


@router.put("/lessons/{lesson_id}", response_model=LessonResponse)
async def update_lesson(lesson_id: str, request: LessonUpdate) -> Dict[str, Any]:
    """Update an existing lesson."""
    async with get_session_context() as session:
        query = select(Lesson).where(Lesson.id == lesson_id)
        result = await session.execute(query)
        lesson = result.scalar_one_or_none()

        if not lesson:
            raise HTTPException(status_code=404, detail=f"Lesson not found: {lesson_id}")

        # Update fields
        update_fields = [
            "title",
            "content",
            "content_type",
            "video_url",
            "order_index",
            "duration_minutes",
            "is_preview",
            "quiz_data",
        ]
        for field in update_fields:
            value = getattr(request, field, None)
            if value is not None:
                setattr(lesson, field, value)

        await session.flush()
        await session.refresh(lesson)
        return lesson.to_dict()


@router.delete("/lessons/{lesson_id}")
async def delete_lesson(lesson_id: str) -> Dict[str, str]:
    """Delete a lesson."""
    async with get_session_context() as session:
        query = select(Lesson).where(Lesson.id == lesson_id)
        result = await session.execute(query)
        lesson = result.scalar_one_or_none()

        if not lesson:
            raise HTTPException(status_code=404, detail=f"Lesson not found: {lesson_id}")

        course_id = lesson.course_id
        await session.delete(lesson)

        # Update course lesson count
        course_query = select(Course).where(Course.id == course_id)
        course_result = await session.execute(course_query)
        course = course_result.scalar_one_or_none()
        if course and course.lesson_count > 0:
            course.lesson_count -= 1

        return {"status": "deleted", "id": lesson_id}


# === USER PROGRESS ENDPOINTS ===


@router.get("/user/{user_id}/progress", response_model=List[UserCourseProgressResponse])
async def get_user_course_progress(user_id: str) -> List[Dict[str, Any]]:
    """Get all course progress for a user."""
    async with get_session_context() as session:
        # Get all user progress records
        query = select(UserProgress).where(UserProgress.user_id == user_id)
        result = await session.execute(query)
        progress_records = result.scalars().all()

        # Group by course
        course_progress: Dict[str, Dict[str, Any]] = {}
        for progress in progress_records:
            cid = str(progress.course_id)
            if cid not in course_progress:
                course_progress[cid] = {
                    "course_id": cid,
                    "course_title": "",
                    "overall_progress": 0.0,
                    "lessons_completed": 0,
                    "total_lessons": 0,
                    "lessons": [],
                }
            course_progress[cid]["lessons"].append(progress.to_dict())

        # Get course details and calculate progress
        for course_id in course_progress:
            course_query = (
                select(Course).options(selectinload(Course.lessons)).where(Course.id == course_id)
            )
            course_result = await session.execute(course_query)
            course = course_result.scalar_one_or_none()

            if course:
                course_progress[course_id]["course_title"] = course.title or ""
                course_progress[course_id]["total_lessons"] = len(course.lessons)

                completed = sum(
                    1 for lp in course_progress[course_id]["lessons"] if lp["status"] == "completed"
                )
                course_progress[course_id]["lessons_completed"] = completed

                if len(course.lessons) > 0:
                    course_progress[course_id]["overall_progress"] = (
                        completed / len(course.lessons)
                    ) * 100

        return list(course_progress.values())


@router.post("/user/{user_id}/course/{course_id}/lesson/{lesson_id}/progress")
async def update_user_progress(
    user_id: str,
    course_id: str,
    lesson_id: str,
    request: UserProgressUpdate,
) -> Dict[str, Any]:
    """Update user progress for a specific lesson."""
    async with get_session_context() as session:
        # Verify lesson exists
        lesson_query = select(Lesson).where(Lesson.id == lesson_id)
        lesson_result = await session.execute(lesson_query)
        lesson = lesson_result.scalar_one_or_none()

        if not lesson:
            raise HTTPException(status_code=404, detail=f"Lesson not found: {lesson_id}")

        # Find existing progress or create new
        query = select(UserProgress).where(
            UserProgress.user_id == user_id,
            UserProgress.lesson_id == lesson_id,
        )
        result = await session.execute(query)
        progress = result.scalar_one_or_none()

        if not progress:
            progress = UserProgress(
                user_id=user_id,
                course_id=course_id,
                lesson_id=lesson_id,
            )
            session.add(progress)

        # Update fields
        if request.status is not None:
            progress.status = request.status
            if request.status == "completed":
                progress.completed_at = datetime.utcnow()

        if request.progress_percent is not None:
            progress.progress_percent = request.progress_percent

        if request.time_spent_minutes is not None:
            progress.time_spent_minutes = request.time_spent_minutes

        if request.quiz_score is not None:
            progress.quiz_score = request.quiz_score

        await session.flush()
        await session.refresh(progress)
        return progress.to_dict()


@router.get(
    "/user/{user_id}/course/{course_id}/progress", response_model=UserCourseProgressResponse
)
async def get_user_course_progress_detail(
    user_id: str,
    course_id: str,
) -> Dict[str, Any]:
    """Get detailed progress for a user in a specific course."""
    async with get_session_context() as session:
        # Get course with lessons
        course_query = (
            select(Course).options(selectinload(Course.lessons)).where(Course.id == course_id)
        )
        course_result = await session.execute(course_query)
        course = course_result.scalar_one_or_none()

        if not course:
            raise HTTPException(status_code=404, detail=f"Course not found: {course_id}")

        # Get user progress for this course
        progress_query = select(UserProgress).where(
            UserProgress.user_id == user_id,
            UserProgress.course_id == course_id,
        )
        progress_result = await session.execute(progress_query)
        progress_records = progress_result.scalars().all()

        progress_map = {str(p.lesson_id): p for p in progress_records}

        total_lessons = len(course.lessons)
        completed = 0
        lessons_response = []

        for lesson in sorted(course.lessons, key=lambda x: x.order_index):
            if str(lesson.id) in progress_map:
                p = progress_map[str(lesson.id)]
                lessons_response.append(p.to_dict())
                if p.status == "completed":
                    completed += 1
            else:
                lessons_response.append(
                    {
                        "id": None,
                        "user_id": user_id,
                        "course_id": course_id,
                        "lesson_id": str(lesson.id),
                        "status": "not_started",
                        "progress_percent": 0.0,
                        "time_spent_minutes": 0,
                        "quiz_score": None,
                        "completed_at": None,
                        "last_accessed_at": None,
                        "created_at": None,
                        "updated_at": None,
                    }
                )

        overall_progress = (completed / total_lessons * 100) if total_lessons > 0 else 0.0

        return {
            "course_id": course_id,
            "course_title": course.title,
            "overall_progress": overall_progress,
            "lessons_completed": completed,
            "total_lessons": total_lessons,
            "lessons": lessons_response,
        }
