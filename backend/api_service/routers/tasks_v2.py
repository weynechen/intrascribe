"""
Tasks V2 API routes for async task management.
Handles task status queries and async operation tracking.
"""
import os
import sys
import time
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, status
from datetime import datetime

# Add shared components to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

from shared.logging import ServiceLogger
from shared.utils import timing_decorator

logger = ServiceLogger("tasks-v2-api")

router = APIRouter(prefix="/v2/tasks", tags=["Tasks V2"])

# Simple in-memory task store (in production, use Redis or database)
task_store: Dict[str, Dict[str, Any]] = {}


def update_task_status(task_id: str, status: str, progress: Optional[Dict] = None, result: Optional[Dict] = None, error: Optional[str] = None):
    """Update task status in store"""
    task_store[task_id] = {
        "task_id": task_id,
        "status": status,
        "progress": progress,
        "result": result,
        "error": error,
        "updated_at": datetime.utcnow().isoformat()
    }


@router.get("/{task_id}")
@timing_decorator
async def get_task(task_id: str):
    """
    Get task information by task ID.
    
    Args:
        task_id: Task ID to query
    
    Returns:
        Task information
    """
    return await get_task_status_impl(task_id)


async def get_task_status_impl(task_id: str):
    """
    Internal implementation for getting task status.
    
    Args:
        task_id: Task ID to query
    
    Returns:
        Task status information
    """
    try:
        # Handle special case for "undefined" task_id
        if task_id == "undefined":
            return {
                "success": False,
                "message": "Invalid task ID",
                "timestamp": datetime.utcnow().isoformat(),
                "task_id": task_id,
                "status": "error",
                "error": "Task ID is undefined - check client implementation"
            }
        
        # For now, simulate task completion after a short delay
        # In production, this would query actual task status from Redis/database
        
        if task_id not in task_store:
            # Simulate task progression
            current_time = time.time()
            task_age = current_time % 10  # Simulate 10-second cycle
            
            if task_age < 2:
                status_value = "pending"
                progress = {"step": "initializing", "percentage": 10}
            elif task_age < 5:
                status_value = "started" 
                progress = {"step": "processing", "percentage": 50}
            else:
                status_value = "success"
                progress = {"step": "completed", "percentage": 100}
                # Mock result for session finalization
                result = {
                    "message": "Session finalized successfully",
                    "session_id": task_id.split('-')[0],  # Mock session ID
                    "transcription_saved": True,
                    "segments_processed": 15,
                    "total_duration_seconds": 120
                }
            
            return {
                "success": True,
                "message": "Task status retrieved",
                "timestamp": datetime.utcnow().isoformat(),
                "task_id": task_id,
                "status": status_value,
                "progress": progress,
                "result": result if status_value == "success" else None,
                "error": None
            }
        
        # Return stored task status
        task_data = task_store[task_id]
        return {
            "success": True,
            "message": "Task status retrieved", 
            "timestamp": datetime.utcnow().isoformat(),
            **task_data
        }
        
    except Exception as e:
        logger.error(f"Failed to get task status for {task_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get task status"
        )


@router.get("/{task_id}/status")
@timing_decorator
async def get_task_status(task_id: str):
    """
    Get task status by task ID.
    
    Args:
        task_id: Task ID to query
    
    Returns:
        Task status information
    """
    return await get_task_status_impl(task_id)


@router.delete("/{task_id}")
@timing_decorator
async def cancel_task(task_id: str):
    """
    Cancel a running task.
    
    Args:
        task_id: Task ID to cancel
    
    Returns:
        Cancellation confirmation
    """
    try:
        # Update task status to cancelled
        update_task_status(task_id, "cancelled", error="Task cancelled by user")
        
        return {
            "success": True,
            "message": "Task cancelled successfully",
            "timestamp": datetime.utcnow().isoformat(),
            "task_id": task_id
        }
        
    except Exception as e:
        logger.error(f"Failed to cancel task {task_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cancel task"
        )
