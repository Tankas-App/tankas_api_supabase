from google.cloud import vision
from app.config import config
import os
from typing import Tuple, List, Dict

class AIService:
    """Integrate with Google Vision API for image analysis"""
    
    # Define what types of garbage are "hard" vs "easy" to clean
    HARD_CLEANUP_KEYWORDS = {
        "construction", "debris", "metal", "concrete", "brick", "asphalt",
        "wood", "glass", "rubble", "scrap", "industrial", "heavy"
    }
    
    MEDIUM_CLEANUP_KEYWORDS = {
        "trash", "garbage", "waste", "litter", "refuse", "rubbish",
        "junk", "clutter", "mess", "bag", "box", "pile"
    }
    
    EASY_CLEANUP_KEYWORDS = {
        "paper", "plastic", "bottle", "can", "wrapper", "leaf", "leaves",
        "foliage", "branches", "sticks", "cardboard", "tissue", "fabric"
    }
    
    def __init__(self):
        """Initialize Google Vision client"""
        # Set up credentials from environment
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = config.GOOGLE_VISION_CREDENTIALS_PATH
        self.client = vision.ImageAnnotatorClient()
    
    async def analyze_issue_image(self, image_bytes: bytes) -> Dict:
        """
        Analyze an environmental issue image using Google Vision API
        
        Args:
            image_bytes: Raw image data as bytes
            
        Returns:
            Dictionary with:
            - labels: List of detected labels
            - description: Auto-generated description of the issue
            - difficulty: easy/medium/hard
            - priority: low/medium/high (default: medium)
            - confidence: Average confidence score (0-100)
            - is_valid_issue: Whether this appears to be a cleanup issue
        """
        try:
            # Create image object for Vision API
            image = vision.Image(content=image_bytes)
            
            # Call Google Vision API to detect labels
            response = self.client.label_detection(image=image)
            labels = response.label_annotations
            
            if not labels:
                return {
                    "error": "No labels detected. Please provide a clearer image of the environmental issue.",
                    "is_valid_issue": False
                }
            
            # Extract label names and confidences
            label_data = [
                {
                    "name": label.description.lower(),
                    "confidence": round(label.confidence * 100, 2)  # Convert to 0-100 scale
                }
                for label in labels
            ]
            
            # Check if this is actually a cleanup issue (not a cat, person, food, etc.)
            is_valid = self._is_valid_cleanup_issue(label_data)
            
            if not is_valid:
                return {
                    "error": "This doesn't appear to be an environmental cleanup issue. Please provide an image of litter, garbage, or environmental debris.",
                    "is_valid_issue": False
                }
            
            # Calculate difficulty based on label types
            difficulty = self._calculate_difficulty(label_data)
            
            # Generate description
            description = self._generate_description(label_data)
            
            # Calculate average confidence
            avg_confidence = sum(label["confidence"] for label in label_data) / len(label_data)
            
            return {
                "labels": label_data,
                "description": description,
                "difficulty": difficulty,
                "priority": "medium",  # Default, user can override
                "confidence": round(avg_confidence, 2),
                "is_valid_issue": True
            }
        
        except Exception as e:
            return {
                "error": f"Image analysis failed: {str(e)}",
                "is_valid_issue": False
            }
    
    def _is_valid_cleanup_issue(self, labels: List[Dict]) -> bool:
        """
        Check if the image appears to be a legitimate cleanup issue
        
        Args:
            labels: List of detected labels with names and confidences
            
        Returns:
            True if this looks like a cleanup issue, False otherwise
        """
        # Extract just the label names
        label_names = [label["name"] for label in labels]
        
        # Combine all keywords to check against
        all_cleanup_keywords = (
            self.HARD_CLEANUP_KEYWORDS | 
            self.MEDIUM_CLEANUP_KEYWORDS | 
            self.EASY_CLEANUP_KEYWORDS
        )
        
        # Check if ANY label matches cleanup keywords
        for label in label_names:
            if any(keyword in label for keyword in all_cleanup_keywords):
                return True
        
        # Additional check: if top label has high confidence and contains cleanup-related words
        if labels and labels[0]["confidence"] > 70:
            top_label = labels[0]["name"]
            if any(word in top_label for word in ["waste", "garbage", "trash", "litter", "debris", "dirt", "dirt", "pollution", "contamination"]):
                return True
        
        return False
    
    def _calculate_difficulty(self, labels: List[Dict]) -> str:
        """
        Determine cleanup difficulty based on label types
        
        Logic:
        - If ANY hard label is detected → hard
        - Else if ANY medium label is detected → medium
        - Else if ANY easy label is detected → easy
        - Else → medium (default)
        
        Args:
            labels: List of detected labels
            
        Returns:
            "easy", "medium", or "hard"
        """
        label_names = [label["name"].lower() for label in labels]
        
        # Check for hard cleanup indicators
        for label in label_names:
            if any(keyword in label for keyword in self.HARD_CLEANUP_KEYWORDS):
                return "hard"
        
        # Check for medium cleanup indicators
        for label in label_names:
            if any(keyword in label for keyword in self.MEDIUM_CLEANUP_KEYWORDS):
                return "medium"
        
        # Check for easy cleanup indicators
        for label in label_names:
            if any(keyword in label for keyword in self.EASY_CLEANUP_KEYWORDS):
                return "easy"
        
        # Default to medium if unclear
        return "medium"
    
    def _generate_description(self, labels: List[Dict]) -> str:
        """
        Generate a human-readable description of the issue from labels
        
        Args:
            labels: List of detected labels
            
        Returns:
            A descriptive sentence about the issue
        """
        if not labels:
            return "Environmental cleanup issue"
        
        # Get top 3 labels by confidence
        top_labels = sorted(labels, key=lambda x: x["confidence"], reverse=True)[:3]
        label_names = [label["name"] for label in top_labels]
        
        # Build description
        if len(label_names) == 1:
            description = f"Environmental issue with {label_names[0]}"
        elif len(label_names) == 2:
            description = f"Environmental issue with {label_names[0]} and {label_names[1]}"
        else:
            description = f"Environmental issue with {', '.join(label_names[:-1])}, and {label_names[-1]}"
        
        return description
    
    async def verify_resolution(self, before_image_bytes: bytes, after_image_bytes: bytes) -> Dict:
        """
        Verify that cleanup work was actually done by comparing before/after images
        
        Args:
            before_image_bytes: Original issue photo
            after_image_bytes: Photo after cleanup
            
        Returns:
            Dictionary with:
            - verified: True if cleanup appears complete
            - confidence: Confidence score (0-100)
            - before_labels: Labels from original image
            - after_labels: Labels from cleanup image
        """
        try:
            # Analyze both images
            before_response = await self.analyze_issue_image(before_image_bytes)
            after_response = await self.analyze_issue_image(after_image_bytes)
            
            if not before_response.get("is_valid_issue") or not after_response.get("is_valid_issue"):
                return {
                    "verified": False,
                    "confidence": 0,
                    "error": "Could not verify images"
                }
            
            # Get labels from both images
            before_labels = set(label["name"] for label in before_response["labels"])
            after_labels = set(label["name"] for label in after_response["labels"])
            
            # Calculate how many cleanup-related labels were removed
            removed_labels = len(before_labels - after_labels)
            total_labels = len(before_labels)
            
            # If at least 50% of labels were removed, consider it verified
            if total_labels > 0:
                removal_percentage = (removed_labels / total_labels) * 100
            else:
                removal_percentage = 0
            
            # High confidence if most labels were removed
            verified = removal_percentage >= 50
            confidence = min(removal_percentage, 100)
            
            return {
                "verified": verified,
                "confidence": round(confidence, 2),
                "before_labels": list(before_labels),
                "after_labels": list(after_labels),
                "removed_labels": list(before_labels - after_labels),
                "removal_percentage": round(removal_percentage, 2)
            }
        
        except Exception as e:
            return {
                "verified": False,
                "confidence": 0,
                "error": str(e)
            }