from fastapi import APIRouter, UploadFile, File, HTTPException, status

router = APIRouter(tags=["test"])

@router.post("/test-upload")
async def test_upload(file: UploadFile = File(...)):
    """
    Simple test endpoint to verify file uploads work
    
    No authentication, no form data, just a file upload.
    This helps us isolate if the problem is with files or our complex endpoint.
    """
    try:
        # Read the file
        contents = await file.read()
        
        # Return basic info about what we received
        return {
            "message": "File uploaded successfully!",
            "filename": file.filename,
            "file_size": len(contents),
            "content_type": file.content_type
        }
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Upload failed: {str(e)}"
        )