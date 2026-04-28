# backend/utils/model_loader.py
"""
Model loader supporting multiple formats: joblib, pickle, ONNX, Keras, PyTorch.
Returns the loaded model and a flag indicating if it's a deep learning model.
"""

import os
import joblib
import pickle
import numpy as np
from sklearn.base import BaseEstimator, ClassifierMixin


def load_model(file_obj, filename):
    """
    Load a model from various formats.
    
    Args:
        file_obj: File object from Flask request
        filename: Original filename (to detect extension)
    
    Returns:
        tuple: (model, is_dl_model)
            - model: Loaded model object or wrapper
            - is_dl_model: Boolean indicating if model is a deep learning model
    
    Raises:
        ValueError: If model format is unsupported or loading fails
    """
    
    ext = os.path.splitext(filename.lower())[1]
    
    # Try sklearn formats first (joblib, pickle)
    if ext == '.joblib':
        try:
            model = joblib.load(file_obj)
            # Handle legacy saved dicts from older mitigation downloads
            if isinstance(model, dict):
                try:
                    from utils.mitigation import MitigatedBaselineWrapper, MitigatedUserModelWrapper
                except Exception:
                    from .mitigation import MitigatedBaselineWrapper, MitigatedUserModelWrapper

                if "mitigator" in model:
                    return MitigatedBaselineWrapper.from_saved_dict(model), False
                if "group_thresholds" in model and "final_model" in model and "transformer" in model:
                    return MitigatedUserModelWrapper.from_saved_dict(model), False
                raise ValueError("Uploaded .joblib is a metadata dict, not a model. Downloaded mitigated files from older versions are not directly uploadable.")
            return model, False
        except Exception as e:
            raise ValueError(f"Failed to load .joblib file: {str(e)}")
    
    elif ext == '.pkl':
        import tempfile
        # Write to a temp file first — both joblib and pickle work more
        # reliably from a path than from a raw BytesIO / Werkzeug FileStorage.
        try:
            file_obj.seek(0)
            raw = file_obj.read()
        except Exception as e:
            raise ValueError(f"Failed to read .pkl file: {e}")

        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as tmp:
                tmp.write(raw)
                tmp_path = tmp.name

            # 1. Try joblib first — handles numpy-heavy sklearn objects better
            try:
                model = joblib.load(tmp_path)
                return model, False
            except Exception:
                pass

            # 2. Fall back to plain pickle
            try:
                with open(tmp_path, "rb") as fh:
                    model = pickle.load(fh)
                return model, False
            except Exception as e2:
                raise ValueError(
                    f"Failed to load .pkl file: {e2}. "
                    "Ensure the file was saved with joblib.dump() or pickle.dump() "
                    "using a compatible sklearn/numpy version."
                )
        finally:
            if tmp_path:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
    
    # ONNX format
    elif ext == '.onnx':
        try:
            import onnxruntime as ort
        except ImportError:
            raise ValueError("ONNX support requires 'onnxruntime'. Install with: pip install onnxruntime")
        
        try:
            file_obj.seek(0)
            model = ONNXWrapper(file_obj.read())
            return model, True
        except Exception as e:
            raise ValueError(f"Failed to load .onnx file: {str(e)}")
    
    # Keras format
    elif ext in ['.keras', '.h5']:
        try:
            import tensorflow as tf
        except ImportError:
            raise ValueError("Keras support requires 'tensorflow'. Install with: pip install tensorflow")
        
        try:
            file_obj.seek(0)
            # Save to temp file for keras loading (can't load from BytesIO directly in all versions)
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                tmp.write(file_obj.read())
                tmp_path = tmp.name
            
            try:
                keras_model = tf.keras.models.load_model(tmp_path)
                model = KerasWrapper(keras_model)
                return model, True
            finally:
                os.remove(tmp_path)
        except Exception as e:
            raise ValueError(f"Failed to load Keras model ({ext}): {str(e)}")
    
    # PyTorch format
    elif ext in ['.pt', '.pth']:
        try:
            import torch
        except ImportError:
            raise ValueError("PyTorch support requires 'torch'. Install with: pip install torch")
        
        try:
            file_obj.seek(0)
            # Load PyTorch model
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                tmp.write(file_obj.read())
                tmp_path = tmp.name
            
            try:
                pytorch_model = torch.load(tmp_path, map_location='cpu')
                # If it's a state dict, we can't wrap it directly; raise error
                if isinstance(pytorch_model, dict):
                    raise ValueError("Uploaded .pth/.pt appears to be a state_dict, not a full model. Please save the entire model: torch.save(model, 'model.pth')")
                model = PyTorchWrapper(pytorch_model)
                return model, True
            finally:
                os.remove(tmp_path)
        except Exception as e:
            raise ValueError(f"Failed to load PyTorch model ({ext}): {str(e)}")
    
    else:
        raise ValueError(f"Unsupported model format: {ext}. Supported formats: .joblib, .pkl, .onnx, .keras, .h5, .pt, .pth")


class ONNXWrapper(BaseEstimator, ClassifierMixin):
    """Wraps ONNX models to expose sklearn-like predict interface."""
    
    def __init__(self, onnx_bytes):
        """
        Args:
            onnx_bytes: Raw bytes of ONNX model file
        """
        import onnxruntime as ort
        import tempfile
        
        # Save bytes to temp file and load
        with tempfile.NamedTemporaryFile(suffix='.onnx', delete=False) as tmp:
            tmp.write(onnx_bytes)
            tmp_path = tmp.name
        
        try:
            self.session = ort.InferenceSession(tmp_path, providers=['CPUExecutionProvider'])
            self.input_name = self.session.get_inputs()[0].name
            self.output_name = self.session.get_outputs()[0].name
        finally:
            os.remove(tmp_path)
    
    def predict(self, X):
        """
        Run inference on ONNX model.
        
        Args:
            X: Input array or DataFrame (n_samples, n_features)
        
        Returns:
            Predictions (binary labels or probabilities)
        """
        X_array = np.asarray(X, dtype=np.float32)
        if X_array.ndim == 1:
            X_array = X_array.reshape(1, -1)
        
        # Run inference
        outputs = self.session.run([self.output_name], {self.input_name: X_array})
        predictions = outputs[0]
        
        # If output is 2D and has 2 columns (probabilities), take argmax; else return as-is
        if predictions.ndim == 2 and predictions.shape[1] == 2:
            return np.argmax(predictions, axis=1).astype(int)
        elif predictions.ndim == 2 and predictions.shape[1] == 1:
            # Single output column; threshold at 0.5 for binary classification
            return (predictions.flatten() > 0.5).astype(int)
        else:
            return predictions.flatten().astype(int)


class KerasWrapper(BaseEstimator, ClassifierMixin):
    """Wraps Keras/TensorFlow models to expose sklearn-like predict interface."""
    
    def __init__(self, keras_model):
        self.model = keras_model
    
    def predict(self, X):
        """
        Run inference on Keras model.
        
        Args:
            X: Input array or DataFrame
        
        Returns:
            Binary predictions
        """
        import numpy as np
        
        X_array = np.asarray(X, dtype=np.float32)
        predictions = self.model.predict(X_array, verbose=0)
        
        # Handle various output shapes
        if predictions.ndim == 2 and predictions.shape[1] == 2:
            # Multi-class output; take argmax
            return np.argmax(predictions, axis=1).astype(int)
        elif predictions.ndim == 2 and predictions.shape[1] == 1:
            # Single output; threshold at 0.5
            return (predictions.flatten() > 0.5).astype(int)
        elif predictions.ndim == 1:
            # Already 1D; threshold at 0.5
            return (predictions > 0.5).astype(int)
        else:
            return predictions.astype(int)


class PyTorchWrapper(BaseEstimator, ClassifierMixin):
    """Wraps PyTorch models to expose sklearn-like predict interface."""
    
    def __init__(self, pytorch_model):
        self.model = pytorch_model
        self.model.eval()  # Set to evaluation mode
    
    def predict(self, X):
        """
        Run inference on PyTorch model.
        
        Args:
            X: Input array or DataFrame
        
        Returns:
            Binary predictions
        """
        import torch
        import numpy as np
        
        X_array = np.asarray(X, dtype=np.float32)
        
        with torch.no_grad():
            X_tensor = torch.from_numpy(X_array)
            outputs = self.model(X_tensor)
        
        # Handle various output shapes
        predictions = outputs.numpy() if isinstance(outputs, torch.Tensor) else outputs
        
        if predictions.ndim == 2 and predictions.shape[1] == 2:
            # Multi-class; take argmax
            return np.argmax(predictions, axis=1).astype(int)
        elif predictions.ndim == 2 and predictions.shape[1] == 1:
            # Single output; threshold at 0.5
            return (predictions.flatten() > 0.5).astype(int)
        elif predictions.ndim == 1:
            # Already 1D; threshold at 0.5
            return (predictions > 0.5).astype(int)
        else:
            return predictions.astype(int)