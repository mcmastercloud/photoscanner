from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


@dataclass(frozen=True)
class AIAvailability:
    embeddings: bool
    detection: bool
    embeddings_reason: Optional[str] = None
    detection_reason: Optional[str] = None


class EmbeddingModel:
    """Optional CLIP-style image embeddings.

    Implementation is dependency-gated so the app works without heavy AI installs.
    """

    def __init__(self, device: str = "cpu") -> None:
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
        except Exception as e:  # pragma: no cover
            raise RuntimeError(
                "Embeddings require 'sentence-transformers' (and its torch deps). "
                "Install with: pip install sentence-transformers"
            ) from e

        # This is a common, reasonably small CLIP model.
        self.actual_device = device
        try:
            self._model = SentenceTransformer("clip-ViT-B-32", device=device)
            # Perform a dummy encoding to verify the device works (catches CUDA kernel errors early)
            self._model.encode(["test"], normalize_embeddings=True)
        except Exception as e:
            if device != "cpu":
                print(f"AI Error on {device}: {e}. Falling back to CPU.")
                self._model = SentenceTransformer("clip-ViT-B-32", device="cpu")
                self.actual_device = "cpu"
            else:
                raise e

    def embed_file(self, path: Path) -> bytes:
        # sentence-transformers can take image paths directly.
        vec = self._model.encode([str(path)], normalize_embeddings=True)[0]
        return vec.astype("float32").tobytes()

    def suggest_labels(self, path: Path, labels: list[str], top_k: int = 5) -> list[tuple[str, float]]:
        """Suggest labels for an image using Zero-Shot Classification."""
        from sentence_transformers import util  # type: ignore
        
        # Embed image
        img_emb = self._model.encode([str(path)], normalize_embeddings=True)
        
        # Embed labels (this could be cached if labels are static)
        text_emb = self._model.encode(labels, normalize_embeddings=True)
        
        # Compute cosine similarities
        # img_emb is (1, D), text_emb is (N, D) -> (1, N)
        scores = util.cos_sim(img_emb, text_emb)[0]
        
        # Get top k
        # torch.topk returns (values, indices)
        top_results = []
        for i in range(len(labels)):
            top_results.append((labels[i], float(scores[i])))
            
        top_results.sort(key=lambda x: x[1], reverse=True)
        return top_results[:top_k]


DEFAULT_LABELS = [
    "person", "man", "woman", "child", "baby", "group of people",
    "dog", "cat", "bird", "animal", "wildlife",
    "nature", "landscape", "mountain", "beach", "ocean", "forest", "tree", "flower", "sky", "sunset", "clouds",
    "city", "building", "house", "architecture", "street", "road", "bridge",
    "indoor", "room", "furniture", "table", "chair",
    "food", "drink", "fruit", "vegetable",
    "car", "vehicle", "bicycle", "train", "airplane", "boat",
    "text", "screenshot", "drawing", "painting", "art",
    "night", "day", "sunny", "rainy", "snow",
    "party", "wedding", "concert", "sport",
    "computer", "phone", "electronics",
]


class Detector:
    """Optional face/object detection.

    Uses MediaPipe if installed. Results are JSON-serializable dicts.
    """

    def __init__(self) -> None:
        try:
            import mediapipe as mp  # type: ignore
        except Exception as e:  # pragma: no cover
            raise RuntimeError(
                "Detection requires 'mediapipe'. Install with: pip install mediapipe"
            ) from e

        self._mp = mp

    def analyze_file(self, path: Path, faces: bool, objects: bool, device: str = "cpu") -> dict[str, Any]:
        # Minimal, pragmatic detection:
        # - Faces: use MediaPipe Face Detection
        # - Objects: use MediaPipe Objectron is 3D; instead use SelfieSegmentation? Not object.
        # For now, treat objects as "not implemented" unless you want YOLO.
        import cv2  # type: ignore

        img_bgr = cv2.imdecode(
            # OpenCV reads bytes; this supports unicode paths on Windows.
            # pylint: disable=protected-access
            __import__("numpy").fromfile(str(path), dtype=__import__("numpy").uint8),
            cv2.IMREAD_COLOR,
        )
        if img_bgr is None:
            return {"faces": [] if faces else None, "objects": [] if objects else None}

        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)

        out: dict[str, Any] = {"faces": None, "objects": None}

        if faces:
            mp_face = self._mp.solutions.face_detection
            with mp_face.FaceDetection(model_selection=1, min_detection_confidence=0.5) as fd:
                r = fd.process(img_rgb)
                faces_out = []
                if r.detections:
                    for det in r.detections:
                        bbox = det.location_data.relative_bounding_box
                        faces_out.append(
                            {
                                "score": float(det.score[0]) if det.score else None,
                                "bbox": {
                                    "xmin": float(bbox.xmin),
                                    "ymin": float(bbox.ymin),
                                    "width": float(bbox.width),
                                    "height": float(bbox.height),
                                },
                            }
                        )
                out["faces"] = faces_out

        if objects:
            # Use MediaPipe Object Detection (EfficientDet-Lite0)
            # Requires model file. For now, we'll use a simpler approach or assume model is present?
            # Actually, MediaPipe Object Detection requires downloading a TFLite model.
            # To keep it simple and dependency-light without downloading models at runtime,
            # we might stick to the CLIP zero-shot classification we added in EmbeddingModel.
            # BUT, the user asked for bounding boxes. CLIP (ViT-B-32) doesn't give bounding boxes easily.
            # We need an object detector like YOLO or MediaPipe Object Detector.
            
            # Let's try to use MediaPipe Object Detector if available, but it needs a model path.
            # Since we can't easily ship a model, let's use a dummy implementation or 
            # rely on the user having 'ultralytics' (YOLO) installed?
            # Or, we can use the 'mediapipe' tasks API which downloads models?
            
            # For this specific request ("suggest labels... bounding box..."), 
            # the user implies the "Suggest Labels" button should now do detection.
            # The previous implementation used CLIP which has no bboxes.
            # We need to switch to something that supports bboxes.
            # Let's use Ultralytics YOLOv8 if available, as it's easiest for "pip install ultralytics".
            # If not, we can't really do bboxes easily without a model file.
            
            # Let's try to import ultralytics.
            try:
                from ultralytics import YOLO
                # Load a pretrained YOLOv8n model
                model = YOLO("yolov8n.pt") 
                
                # Run inference
                # YOLO accepts device argument (e.g., 'cpu', 'cuda', '0')
                # If device is 'cpu', use it. If 'cuda', use it.
                # Note: ultralytics might throw error if cuda not available.
                
                try:
                    results = model(img_rgb, verbose=False, device=device)
                except Exception as e:
                    # If CUDA failed, try CPU fallback if requested
                    if device != "cpu":
                        print(f"YOLO Error on {device}: {e}. Falling back to CPU.")
                        # Re-raise to let caller handle logging/fallback logic?
                        # Or handle here? Caller (LabelingWorker) has the logic to log failure timestamp.
                        # So we should probably raise it, or return a specific error code.
                        raise e
                    else:
                        raise e
                
                objs_out = []
                for r in results:
                    for box in r.boxes:
                        # box.xyxy is [x1, y1, x2, y2]
                        # box.cls is class index
                        # box.conf is confidence
                        x1, y1, x2, y2 = box.xyxy[0].tolist()
                        conf = float(box.conf[0])
                        cls_id = int(box.cls[0])
                        label = model.names[cls_id]
                        
                        # Normalize to 0-1 relative coordinates
                        h, w, _ = img_rgb.shape
                        objs_out.append({
                            "label": label,
                            "score": conf,
                            "bbox": {
                                "xmin": x1 / w,
                                "ymin": y1 / h,
                                "width": (x2 - x1) / w,
                                "height": (y2 - y1) / h
                            }
                        })
                out["objects"] = objs_out
            except ImportError:
                # Fallback or empty
                # Signal that we need ultralytics
                out["objects"] = []
                out["error"] = "Install 'ultralytics' for object detection."
            except Exception as e:
                # This catches the re-raised exception from inner try block
                # We want to propagate this up if it's a CUDA error so LabelingWorker can handle it.
                # But analyze_file signature returns dict.
                # We can put the error in the dict.
                print(f"Object detection error: {e}")
                out["objects"] = []
                out["error"] = str(e)
                # We should probably raise if it's a device error to trigger fallback logic in worker
                if "CUDA" in str(e) or "device" in str(e):
                     raise e

        return out

        return out

        return out


def get_ai_availability() -> AIAvailability:
    embeddings_ok = True
    detection_ok = True
    emb_reason = None
    det_reason = None

    try:
        import sentence_transformers  # noqa: F401
    except Exception as e:
        embeddings_ok = False
        emb_reason = str(e)

    try:
        import mediapipe  # noqa: F401
        import cv2  # noqa: F401
        import numpy  # noqa: F401
    except Exception as e:
        detection_ok = False
        det_reason = str(e)

    return AIAvailability(
        embeddings=embeddings_ok,
        detection=detection_ok,
        embeddings_reason=emb_reason,
        detection_reason=det_reason,
    )
