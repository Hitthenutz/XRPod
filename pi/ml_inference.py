
from pathlib import Path
import math

import joblib
import pandas as pd


class PhysicalEnvironmentModel:
    """
    Loads the trained XRPOD Random Forest model
    and predicts physical environmental conditions.
    """

    def __init__(self):
        # Locate the saved ML model
        model_path = (
            Path(__file__).resolve().parent
            / "models"
            / "environment_model.joblib"
        )

        if not model_path.exists():
            raise FileNotFoundError(
                f"AI model not found: {model_path}"
            )

        # Only load model files from trusted sources
        self.model = joblib.load(model_path)

    def predict(self, reading):
        """
        Accept sensor readings from the Pi backend.

        Input:
            actual_temp_f
            actual_humidity_pct

        Output:
            prediction
            confidence
        """

        temp_f = reading.get("actual_temp_f")
        humidity = reading.get("actual_humidity_pct")

        # Validate the sensor readings
        if (
            isinstance(temp_f, bool)
            or isinstance(humidity, bool)
            or not isinstance(temp_f, (int, float))
            or not isinstance(humidity, (int, float))
            or not math.isfinite(temp_f)
            or not math.isfinite(humidity)
        ):
            return {
                "prediction": "UNKNOWN",
                "confidence": 0.0
            }

        # Convert Fahrenheit to Celsius
        temp_c = (temp_f - 32) * 5 / 9

        if not (-20 <= temp_c <= 80):
            return {
                "prediction": "UNKNOWN",
                "confidence": 0.0
            }

        if not (0 <= humidity <= 100):
            return {
                "prediction": "UNKNOWN",
                "confidence": 0.0
            }

        # Match the original training features
        features = pd.DataFrame([{
            "temperature": temp_c,
            "humidity": humidity
        }])

        # Generate class probabilities
        probabilities = self.model.predict_proba(features)[0]

        best_index = probabilities.argmax()

        prediction = str(
            self.model.classes_[best_index]
        )

        confidence = float(
            probabilities[best_index]
        )

        return {
            "prediction": prediction,
            "confidence": confidence
        }
