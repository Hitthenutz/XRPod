
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ml_inference import PhysicalEnvironmentModel


def test_model_predicts_valid_reading():
    model = PhysicalEnvironmentModel()

    result = model.predict({
        "actual_temp_f": 72,
        "actual_humidity_pct": 45
    })

    assert result["prediction"] in {
        "NORMAL", "WARM", "COLD", "UNKNOWN"
    }

    assert 0 <= result["confidence"] <= 1


def test_invalid_reading_is_unknown():
    model = PhysicalEnvironmentModel()

    result = model.predict({
        "actual_temp_f": None,
        "actual_humidity_pct": 45
    })

    assert result["prediction"] == "UNKNOWN"
    assert result["confidence"] == 0.0
