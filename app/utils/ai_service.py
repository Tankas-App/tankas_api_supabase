"""
ai_service.py — Swappable AI image analysis

Switch providers via .env:
    AI_PROVIDER=yolo           → YOLOv8s (free, local, default)
    AI_PROVIDER=google_vision  → Google Vision API (paid, more accurate)

Nothing else in the codebase needs to change when you switch.
"""

import os
from typing import Dict, List
from PIL import Image
from io import BytesIO

# ---------------------------------------------------------------------------
# Shared keyword sets — used by both providers for difficulty classification
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
    "handbag",
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
}
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
}

AI_MIN_CONFIDENCE = 40.0  # below this → flag for admin review


# ---------------------------------------------------------------------------
# Base class — both providers implement this interface
# ---------------------------------------------------------------------------


class BaseAIProvider:

    async def analyze_issue_image(self, image_bytes: bytes) -> Dict:
        raise NotImplementedError

    async def verify_resolution(
        self, before_image_bytes: bytes, after_image_bytes: bytes
    ) -> Dict:
        raise NotImplementedError

    # Shared helpers — available to all providers
    def _calculate_difficulty(self, labels: List[Dict]) -> str:
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
        return "medium"

    def _generate_description(self, labels: List[Dict]) -> str:
        if not labels:
            return "Environmental cleanup issue"
        top = [l["name"] for l in labels[:3]]
        if len(top) == 1:
            return f"Environmental issue involving {top[0]}"
        elif len(top) == 2:
            return f"Environmental issue with {top[0]} and {top[1]}"
        else:
            return f"Environmental issue with {top[0]}, {top[1]}, and {top[2]}"

    def _is_only_people_animals(self, labels: List[Dict]) -> bool:
        names = {l["name"] for l in labels}
        non_person = names - NOT_AN_ISSUE_CLASSES
        return len(names) > 0 and len(non_person) == 0

    def _needs_review_response(self, reason: str, labels: List[Dict] = None) -> Dict:
        """Standard pending_review response."""
        return {
            "labels": labels or [],
            "description": "Environmental issue reported — awaiting admin classification",
            "difficulty": "medium",
            "priority": "medium",
            "confidence": 0.0,
            "is_valid_issue": True,
            "needs_review": True,
            "review_reason": reason,
        }

    def _rejection_response(self, reason: str) -> Dict:
        """Standard rejection response."""
        return {
            "error": reason,
            "is_valid_issue": False,
            "needs_review": False,
        }


# ---------------------------------------------------------------------------
# Provider 1: YOLOv8s (free, local)
# ---------------------------------------------------------------------------


class YOLOProvider(BaseAIProvider):

    _model = None
    CONFIDENCE_THRESHOLD = 0.15

    def __init__(self):
        if YOLOProvider._model is None:
            from ultralytics import YOLO

            print("[AI] Loading YOLOv8s model...")
            YOLOProvider._model = YOLO("yolov8s.pt")
            print("[AI] YOLOv8s loaded ✅")

    async def analyze_issue_image(self, image_bytes: bytes) -> Dict:
        try:
            image = Image.open(BytesIO(image_bytes)).convert("RGB")
            results = YOLOProvider._model(
                image, verbose=False, conf=self.CONFIDENCE_THRESHOLD
            )
            labels = self._extract_labels(results) if results else []

            # Nothing detected → admin review
            if not labels:
                return self._needs_review_response(
                    "AI could not detect objects in this image"
                )

            # Only people/animals → reject
            if self._is_only_people_animals(labels):
                return self._rejection_response(
                    "This looks like a photo of people or animals. "
                    "Please upload a photo of an environmental issue."
                )

            avg_confidence = sum(l["confidence"] for l in labels) / len(labels)
            difficulty = self._calculate_difficulty(labels)
            description = self._generate_description(labels)

            # Low confidence → admin review
            if avg_confidence < AI_MIN_CONFIDENCE:
                return self._needs_review_response(
                    f"AI confidence too low ({avg_confidence:.1f}%) — admin verification needed",
                    labels=labels,
                )

            return {
                "labels": labels,
                "description": description,
                "difficulty": difficulty,
                "priority": "medium",
                "confidence": round(avg_confidence, 2),
                "is_valid_issue": True,
                "needs_review": False,
            }

        except Exception as e:
            return self._needs_review_response(f"AI analysis error: {str(e)}")

    async def verify_resolution(
        self, before_image_bytes: bytes, after_image_bytes: bytes
    ) -> Dict:
        try:
            before = await self.analyze_issue_image(before_image_bytes)
            after = await self.analyze_issue_image(after_image_bytes)

            before_labels = {l["name"] for l in before.get("labels", [])}
            after_labels = {l["name"] for l in after.get("labels", [])}
            removed = before_labels - after_labels
            removal_pct = (
                (len(removed) / len(before_labels) * 100) if before_labels else 0
            )

            return {
                "verified": removal_pct >= 40,
                "confidence": round(removal_pct, 2),
                "before_labels": list(before_labels),
                "after_labels": list(after_labels),
                "removed_labels": list(removed),
                "removal_percentage": round(removal_pct, 2),
            }
        except Exception as e:
            return {"verified": False, "confidence": 0, "error": str(e)}

    def _extract_labels(self, results) -> List[Dict]:
        labels = []
        seen = set()
        for result in results:
            if result.boxes is None:
                continue
            for box in result.boxes:
                cls_id = int(box.cls[0])
                confidence = round(float(box.conf[0]) * 100, 2)
                name = YOLOProvider._model.names[cls_id].lower()
                if name not in seen:
                    labels.append({"name": name, "confidence": confidence})
                    seen.add(name)
        labels.sort(key=lambda x: x["confidence"], reverse=True)
        return labels


# ---------------------------------------------------------------------------
# Provider 2: Google Vision API (paid, more accurate)
# ---------------------------------------------------------------------------


class GoogleVisionProvider(BaseAIProvider):

    # Cleanup-related keywords from Google Vision's label taxonomy
    CLEANUP_KEYWORDS = {
        "waste",
        "garbage",
        "trash",
        "litter",
        "debris",
        "pollution",
        "contamination",
        "rubbish",
        "refuse",
        "junk",
        "clutter",
        "dump",
        "landfill",
        "plastic",
        "bottle",
        "can",
        "bag",
        "container",
        "construction",
        "rubble",
        "scrap",
        "metal",
    }

    def __init__(self):
        from google.cloud import vision
        from app.config import config
        import os

        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = (
            config.GOOGLE_VISION_CREDENTIALS_PATH
        )
        self.client = vision.ImageAnnotatorClient()
        print("[AI] Google Vision API initialised ✅")

    async def analyze_issue_image(self, image_bytes: bytes) -> Dict:
        try:
            from google.cloud import vision

            image = vision.Image(content=image_bytes)
            response = self.client.label_detection(image=image)
            raw = response.label_annotations

            if not raw:
                return self._needs_review_response("Google Vision detected no labels")

            labels = [
                {
                    "name": label.description.lower(),
                    "confidence": round(label.score * 100, 2),
                }
                for label in raw
            ]

            # Only people/animals → reject
            if self._is_only_people_animals(labels):
                return self._rejection_response(
                    "This doesn't appear to be an environmental issue. "
                    "Please upload a photo of litter, garbage, or debris."
                )

            # Check if any label matches cleanup keywords
            label_names = {l["name"] for l in labels}
            has_cleanup = any(
                any(kw in name for kw in self.CLEANUP_KEYWORDS) for name in label_names
            )
            non_person = label_names - NOT_AN_ISSUE_CLASSES

            if not has_cleanup and not non_person:
                return self._rejection_response(
                    "This doesn't appear to be an environmental issue."
                )

            avg_confidence = sum(l["confidence"] for l in labels) / len(labels)
            difficulty = self._calculate_difficulty(labels)
            description = self._generate_description(labels)

            # Low confidence → admin review
            if avg_confidence < AI_MIN_CONFIDENCE:
                return self._needs_review_response(
                    f"AI confidence too low ({avg_confidence:.1f}%) — admin verification needed",
                    labels=labels,
                )

            return {
                "labels": labels,
                "description": description,
                "difficulty": difficulty,
                "priority": "medium",
                "confidence": round(avg_confidence, 2),
                "is_valid_issue": True,
                "needs_review": False,
            }

        except Exception as e:
            return self._needs_review_response(f"Google Vision error: {str(e)}")

    async def verify_resolution(
        self, before_image_bytes: bytes, after_image_bytes: bytes
    ) -> Dict:
        try:
            before = await self.analyze_issue_image(before_image_bytes)
            after = await self.analyze_issue_image(after_image_bytes)

            before_labels = {l["name"] for l in before.get("labels", [])}
            after_labels = {l["name"] for l in after.get("labels", [])}
            removed = before_labels - after_labels
            removal_pct = (
                (len(removed) / len(before_labels) * 100) if before_labels else 0
            )

            return {
                "verified": removal_pct >= 50,
                "confidence": round(removal_pct, 2),
                "before_labels": list(before_labels),
                "after_labels": list(after_labels),
                "removed_labels": list(removed),
                "removal_percentage": round(removal_pct, 2),
            }
        except Exception as e:
            return {"verified": False, "confidence": 0, "error": str(e)}


# ---------------------------------------------------------------------------
# AIService — the single class the rest of the codebase imports
# Reads AI_PROVIDER from .env and returns the right provider
# ---------------------------------------------------------------------------


class AIService:
    """
    Facade — import this everywhere.
    Switch providers by changing AI_PROVIDER in .env:

        AI_PROVIDER=yolo            # free, local (default)
        AI_PROVIDER=google_vision   # paid, more accurate
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            provider = os.getenv("AI_PROVIDER", "yolo").lower()

            if provider == "google_vision":
                cls._instance = GoogleVisionProvider()
                print("[AI] Using Google Vision API")
            else:
                cls._instance = YOLOProvider()
                print("[AI] Using YOLOv8s (local)")

        return cls._instance

    # Delegate to the provider — these methods are called by issue_service.py
    async def analyze_issue_image(self, image_bytes: bytes) -> Dict:
        return await self._instance.analyze_issue_image(image_bytes)

    async def verify_resolution(
        self, before_image_bytes: bytes, after_image_bytes: bytes
    ) -> Dict:
        return await self._instance.verify_resolution(
            before_image_bytes, after_image_bytes
        )
