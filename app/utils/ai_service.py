"""
ai_service.py — YOLOv8n image analysis (replaces Google Vision API)

No API key, no billing, no external calls.
The model runs locally on the same server.

First run: ultralytics auto-downloads yolov8n.pt (~6MB) to ~/.cache/
Subsequent runs: loads from cache instantly.
"""

from ultralytics import YOLO
from PIL import Image
from io import BytesIO
from typing import Dict, List
import os

# ---------------------------------------------------------------------------
# Difficulty classification keywords
# Same logic as before — just now driven by YOLO labels instead of Vision API
# ---------------------------------------------------------------------------

HARD_KEYWORDS = {
    "construction",
    "debris",
    "metal",
    "concrete",
    "brick",
    "wood",
    "glass",
    "rubble",
    "scrap",
    "industrial",
    "truck",
    "car",
    "vehicle",
    "bus",
    "train",
}

MEDIUM_KEYWORDS = {
    "trash",
    "garbage",
    "waste",
    "litter",
    "bag",
    "box",
    "pile",
    "bin",
    "container",
    "barrel",
    "suitcase",
    "backpack",
}

EASY_KEYWORDS = {
    "paper",
    "plastic",
    "bottle",
    "can",
    "cup",
    "fork",
    "knife",
    "spoon",
    "banana",
    "apple",
    "orange",
    "bowl",
    "book",
    "chair",
}

# YOLO classes that suggest this is NOT an environmental issue
NOT_AN_ISSUE_CLASSES = {
    "person",
    "cat",
    "dog",
    "bird",
    "horse",
    "cow",
    "sheep",
    "elephant",
    "bear",
    "zebra",
    "giraffe",
    "face",
}


class AIService:
    """
    Local AI image analysis using YOLOv8n.
    Drop-in replacement for the Google Vision API version.
    """

    _model = None  # class-level singleton — load once, reuse forever

    def __init__(self):
        if AIService._model is None:
            print("[AI] Loading YOLOv8n model...")
            AIService._model = YOLO("yolov8n.pt")  # auto-downloads on first run
            print("[AI] Model loaded ✅")

    # ------------------------------------------------------------------
    # Public interface — same signature as the old Google Vision version
    # ------------------------------------------------------------------

    async def analyze_issue_image(self, image_bytes: bytes) -> Dict:
        """
        Analyse an environmental issue image.

        Returns the same dict shape as the old Google Vision version so
        nothing else in the codebase needs to change:
        {
            "labels":        [{"name": str, "confidence": float}, ...],
            "description":   str,
            "difficulty":    "easy" | "medium" | "hard",
            "priority":      "medium",
            "confidence":    float,
            "is_valid_issue": bool,
            "error":         str   (only present on failure)
        }
        """
        try:
            # Convert bytes → PIL Image
            image = Image.open(BytesIO(image_bytes)).convert("RGB")

            # Run YOLO inference
            results = AIService._model(image, verbose=False)

            if not results or len(results) == 0:
                return {
                    "error": "No objects detected. Please provide a clearer image.",
                    "is_valid_issue": False,
                }

            # Extract detections
            labels = self._extract_labels(results)

            if not labels:
                return {
                    "error": "No recognisable objects found in the image.",
                    "is_valid_issue": False,
                }

            # Check if it's a valid cleanup issue
            is_valid = self._is_valid_cleanup_issue(labels)
            if not is_valid:
                return {
                    "error": (
                        "This doesn't appear to be an environmental issue. "
                        "Please upload a photo of litter, garbage, or debris."
                    ),
                    "is_valid_issue": False,
                }

            difficulty = self._calculate_difficulty(labels)
            description = self._generate_description(labels)
            avg_confidence = sum(l["confidence"] for l in labels) / len(labels)

            return {
                "labels": labels,
                "description": description,
                "difficulty": difficulty,
                "priority": "medium",
                "confidence": round(avg_confidence, 2),
                "is_valid_issue": True,
            }

        except Exception as e:
            return {
                "error": f"Image analysis failed: {str(e)}",
                "is_valid_issue": False,
            }

    async def verify_resolution(
        self,
        before_image_bytes: bytes,
        after_image_bytes: bytes,
    ) -> Dict:
        """
        Compare before/after images to verify cleanup was done.
        Same interface as the old Google Vision version.
        """
        try:
            before = await self.analyze_issue_image(before_image_bytes)
            after = await self.analyze_issue_image(after_image_bytes)

            if not before.get("is_valid_issue"):
                return {
                    "verified": False,
                    "confidence": 0,
                    "error": "Could not analyse before image",
                }

            before_labels = {l["name"] for l in before.get("labels", [])}
            after_labels = {l["name"] for l in after.get("labels", [])}

            removed = before_labels - after_labels
            removal_pct = (
                (len(removed) / len(before_labels) * 100) if before_labels else 0
            )
            verified = removal_pct >= 50

            return {
                "verified": verified,
                "confidence": round(removal_pct, 2),
                "before_labels": list(before_labels),
                "after_labels": list(after_labels),
                "removed_labels": list(removed),
                "removal_percentage": round(removal_pct, 2),
            }

        except Exception as e:
            return {"verified": False, "confidence": 0, "error": str(e)}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_labels(self, results) -> List[Dict]:
        """Pull class names + confidence scores out of YOLO results."""
        labels = []
        seen = set()

        for result in results:
            if result.boxes is None:
                continue
            for box in result.boxes:
                cls_id = int(box.cls[0])
                confidence = round(float(box.conf[0]) * 100, 2)
                name = AIService._model.names[cls_id].lower()

                # Deduplicate — keep highest confidence per class
                if name not in seen:
                    labels.append({"name": name, "confidence": confidence})
                    seen.add(name)

        # Sort by confidence descending
        labels.sort(key=lambda x: x["confidence"], reverse=True)
        return labels

    def _is_valid_cleanup_issue(self, labels: List[Dict]) -> bool:
        """
        Return True if the image looks like an environmental issue.
        Rejects photos that are clearly just people, animals, etc.
        """
        names = {l["name"] for l in labels}

        # If ONLY non-issue classes detected → reject
        if names and names.issubset(NOT_AN_ISSUE_CLASSES):
            return False

        # Accept anything that isn't purely non-issue
        # (YOLO detects objects generically — most outdoor scenes with
        #  objects qualify; the user description provides more context)
        all_keywords = HARD_KEYWORDS | MEDIUM_KEYWORDS | EASY_KEYWORDS
        for name in names:
            if any(kw in name for kw in all_keywords):
                return True

        # If unrecognised objects detected, still accept — better to
        # let a borderline image through than block a real issue report
        non_person = names - NOT_AN_ISSUE_CLASSES
        return len(non_person) > 0

    def _calculate_difficulty(self, labels: List[Dict]) -> str:
        """Classify cleanup difficulty from detected object names."""
        names = [l["name"].lower() for l in labels]

        for name in names:
            if any(kw in name for kw in HARD_KEYWORDS):
                return "hard"

        for name in names:
            if any(kw in name for kw in MEDIUM_KEYWORDS):
                return "medium"

        for name in names:
            if any(kw in name for kw in EASY_KEYWORDS):
                return "easy"

        return "medium"  # safe default

    def _generate_description(self, labels: List[Dict]) -> str:
        """Generate a human-readable description from the top detections."""
        if not labels:
            return "Environmental cleanup issue"

        top = [l["name"] for l in labels[:3]]

        if len(top) == 1:
            return f"Environmental issue involving {top[0]}"
        elif len(top) == 2:
            return f"Environmental issue with {top[0]} and {top[1]}"
        else:
            return f"Environmental issue with {top[0]}, {top[1]}, and {top[2]}"
