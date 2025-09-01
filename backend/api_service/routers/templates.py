"""
Template management API routes.
Handles CRUD operations for summary templates.
"""
import os
import sys
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status

# Add shared components to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

from shared.logging import ServiceLogger
from shared.utils import timing_decorator

from core.auth import get_current_user
from schemas import SummaryTemplateRequest, SummaryTemplateResponse
from repositories.user_repository import template_repository

logger = ServiceLogger("templates-api")

router = APIRouter(prefix="/templates", tags=["Templates"])


@router.post("/", response_model=SummaryTemplateResponse)
@timing_decorator
async def create_template(
    request: SummaryTemplateRequest,
    current_user = Depends(get_current_user)
):
    """
    Create a new summary template.
    
    Args:
        request: Template creation request
        current_user: Current authenticated user
    
    Returns:
        Created template data
    """
    try:
        template = template_repository.create_template(
            user_id=current_user.id,
            name=request.name,
            description=request.description,
            template_content=request.template_content,
            category=request.category,
            is_default=request.is_default,
            is_active=request.is_active,
            tags=request.tags
        )
        
        logger.success(f"Created template: {template['id']}")
        
        return SummaryTemplateResponse(**template)
        
    except Exception as e:
        logger.error(f"Failed to create template: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create template"
        )


@router.get("/", response_model=List[SummaryTemplateResponse])
@timing_decorator
async def get_user_templates(current_user = Depends(get_current_user)):
    """
    Get all templates for the current user.
    
    Args:
        current_user: Current authenticated user
    
    Returns:
        List of user templates
    """
    try:
        templates = template_repository.get_user_templates(current_user.id)
        
        return [SummaryTemplateResponse(**template) for template in templates]
        
    except Exception as e:
        logger.error(f"Failed to get user templates: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve templates"
        )


@router.get("/{template_id}", response_model=SummaryTemplateResponse)
@timing_decorator
async def get_template(
    template_id: str,
    current_user = Depends(get_current_user)
):
    """
    Get specific template by ID.
    
    Args:
        template_id: Template ID
        current_user: Current authenticated user
    
    Returns:
        Template details
    """
    try:
        template = template_repository.get_template_by_id(template_id, current_user.id)
        
        if not template:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Template not found"
            )
        
        return SummaryTemplateResponse(**template)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get template {template_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve template"
        )


@router.put("/{template_id}", response_model=SummaryTemplateResponse)
@timing_decorator
async def update_template(
    template_id: str,
    request: SummaryTemplateRequest,
    current_user = Depends(get_current_user)
):
    """
    Update template.
    
    Args:
        template_id: Template ID
        request: Template update request
        current_user: Current authenticated user
    
    Returns:
        Updated template data
    """
    try:
        # Verify template ownership
        existing_template = template_repository.get_template_by_id(template_id, current_user.id)
        
        if not existing_template:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Template not found"
            )
        
        # Update template
        client = template_repository.db.get_service_client()
        
        updates = request.dict(exclude_unset=True)
        updates["updated_at"] = datetime.utcnow().isoformat()
        
        result = client.table('summary_templates')\
            .update(updates)\
            .eq('id', template_id)\
            .eq('user_id', current_user.id)\
            .execute()
        
        if not result.data:
            raise Exception("Template update failed")
        
        updated_template = result.data[0]
        
        logger.success(f"Updated template: {template_id}")
        
        return SummaryTemplateResponse(**updated_template)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update template {template_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update template"
        )


@router.delete("/{template_id}")
@timing_decorator
async def delete_template(
    template_id: str,
    current_user = Depends(get_current_user)
):
    """
    Delete template.
    
    Args:
        template_id: Template ID
        current_user: Current authenticated user
    
    Returns:
        Success confirmation
    """
    try:
        # Verify template ownership
        existing_template = template_repository.get_template_by_id(template_id, current_user.id)
        
        if not existing_template:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Template not found"
            )
        
        # Delete template (soft delete by setting is_active=false)
        client = template_repository.db.get_service_client()
        
        result = client.table('summary_templates')\
            .update({"is_active": False, "updated_at": datetime.utcnow().isoformat()})\
            .eq('id', template_id)\
            .eq('user_id', current_user.id)\
            .execute()
        
        if not result.data:
            raise Exception("Template deletion failed")
        
        logger.success(f"Deleted template: {template_id}")
        
        return {"message": "Template deleted successfully", "template_id": template_id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete template {template_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete template"
        )


@router.get("/system", response_model=List[SummaryTemplateResponse])
@timing_decorator
async def get_system_templates(current_user = Depends(get_current_user)):
    """
    Get system templates.
    
    Args:
        current_user: Current authenticated user
    
    Returns:
        List of system templates
    """
    try:
        templates = template_repository.get_system_templates()
        
        return [SummaryTemplateResponse(**template) for template in templates]
        
    except Exception as e:
        logger.error(f"Failed to get system templates: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve system templates"
        )
