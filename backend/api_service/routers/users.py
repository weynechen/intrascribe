"""
User management API routes.
Handles user profile, preferences, and account operations.
"""
import os
import sys
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status

# Add shared components to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

from shared.logging import ServiceLogger
from shared.utils import timing_decorator

from core.auth import get_current_user
from schemas import UserProfileResponse, UserPreferencesRequest
from repositories.user_repository import user_repository

logger = ServiceLogger("users-api")

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/profile", response_model=UserProfileResponse)
@timing_decorator
async def get_user_profile(current_user = Depends(get_current_user)):
    """
    Get user business profile.
    
    Args:
        current_user: Current authenticated user
    
    Returns:
        User profile with subscription, quotas, and preferences
    """
    try:
        profile = user_repository.get_user_profile(current_user.id)
        
        return UserProfileResponse(
            subscription=profile["subscription"],
            quotas=profile["quotas"],
            preferences=profile["preferences"]
        )
        
    except Exception as e:
        logger.error(f"Failed to get user profile: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve user profile"
        )


@router.put("/preferences", response_model=UserProfileResponse)
@timing_decorator
async def update_user_preferences(
    request: UserPreferencesRequest,
    current_user = Depends(get_current_user)
):
    """
    Update user preferences.
    
    Args:
        request: Preferences update request
        current_user: Current authenticated user
    
    Returns:
        Updated user profile
    """
    try:
        # Convert request to dict, excluding unset values
        preferences = request.dict(exclude_unset=True)
        
        profile = user_repository.update_user_preferences(current_user.id, preferences)
        
        logger.success(f"Updated preferences for user {current_user.id}")
        
        return UserProfileResponse(
            subscription=profile["subscription"],
            quotas=profile["quotas"],
            preferences=profile["preferences"]
        )
        
    except Exception as e:
        logger.error(f"Failed to update user preferences: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update user preferences"
        )
