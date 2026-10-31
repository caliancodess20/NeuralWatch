import numpy as np
import pytest

from neural_brain import NeuromorphicBrain


@pytest.fixture
def brain():
    return NeuromorphicBrain()


# ---------- initial state ----------

def test_initial_weights_shape_and_range(brain):
    assert brain.weights.shape == (10, 10)
    assert brain.weights.min() >= 0.3
    assert brain.weights.max() <= 0.7


def test_baseline_is_an_independent_copy(brain):
    assert np.array_equal(brain.weights, brain.baseline)
    brain.weights[0, 0] += 0.5
    assert brain.baseline[0, 0] != brain.weights[0, 0]


def test_initial_drift_is_zero(brain):
    assert brain.get_drift_score() == 0.0


# ---------- learning and poisoning ----------

def test_normal_learning_stays_in_valid_range_and_small(brain):
    before = brain.weights.copy()
    brain.learn_normally()
    assert brain.weights.min() >= 0.0 and brain.weights.max() <= 1.0
    assert np.max(np.abs(brain.weights - before)) <= 0.005 + 1e-12


def test_poison_never_decreases_weights(brain):
    before = brain.weights.copy()
    brain.receive_poison()
    assert np.all(brain.weights >= before)


def test_poison_drifts_much_more_than_normal_learning():
    healthy, poisoned = NeuromorphicBrain(), NeuromorphicBrain()
    np.random.seed(0)
    for _ in range(50):
        healthy.learn_normally()
        poisoned.receive_poison()
    assert poisoned.get_drift_score() > 5 * healthy.get_drift_score()


def test_drift_score_matches_manual_calculation(brain):
    brain.weights[0, 0] += 0.1
    brain.weights[1, 1] -= 0.1
    expected = (0.1 + 0.1) / 100
    assert brain.get_drift_score() == pytest.approx(expected)


# ---------- LIF neuron ----------

def test_zero_drift_never_spikes(brain):
    for t in range(100):
        assert brain.lif_update(0.0, f"T+{t}") is False
    assert brain.membrane_potential == 0.0


def test_membrane_leaks_when_no_input(brain):
    brain.membrane_potential = 0.1
    brain.lif_update(0.0, "T+0")
    assert brain.membrane_potential == pytest.approx(0.1 * brain.leak_rate)


def test_sustained_low_drift_does_not_spike(brain):
    # steady state = drift * leak / (1 - leak) = 19 * 0.005 = 0.095 < 0.15
    for t in range(500):
        assert brain.lif_update(0.005, f"T+{t}") is False


def test_sustained_higher_drift_eventually_spikes(brain):
    # steady state = 19 * 0.01 = 0.19 > 0.15, so a spike must occur
    fired = any(brain.lif_update(0.01, f"T+{t}") for t in range(200))
    assert fired


def test_spike_resets_membrane_and_is_logged(brain):
    brain.membrane_potential = 0.2
    assert brain.lif_update(0.0, "T+042s") is True
    assert brain.membrane_potential == 0.0
    assert brain.spike_log == ["T+042s"]


# ---------- rollback ----------

def test_rollback_restores_weights_and_clears_membrane(brain):
    original = brain.baseline.copy()
    for _ in range(20):
        brain.receive_poison()
    brain.membrane_potential = 0.1
    brain.rollback()
    assert np.array_equal(brain.weights, original)
    assert brain.membrane_potential == 0.0
    assert brain.get_drift_score() == 0.0


def test_rollback_keeps_baseline_independent(brain):
    brain.rollback()
    brain.weights[0, 0] += 0.3
    assert brain.baseline[0, 0] != brain.weights[0, 0]


# ---------- poison fingerprint ----------

def test_fingerprint_clean_brain_has_no_changes(brain):
    fp = brain.get_poison_fingerprint()
    assert fp["up"] == 0 and fp["down"] == 0
    assert all(item["Change"] == 0 for item in fp["top"])


def test_fingerprint_detects_upward_hotspot(brain):
    brain.weights[7:, 7:] += 0.1  # 3x3 block, bottom-right
    fp = brain.get_poison_fingerprint()
    assert fp["up"] == 9
    assert fp["down"] == 0
    assert fp["hotspot"] == "bottom-right"
    assert len(fp["top"]) == 5
    assert fp["top"][0]["Change"] == pytest.approx(0.1)


def test_fingerprint_detects_downward_hotspot(brain):
    brain.weights[:2, :2] -= 0.1  # 2x2 block, top-left
    fp = brain.get_poison_fingerprint()
    assert fp["down"] == 4
    assert fp["up"] == 0
    assert fp["hotspot"] == "top-left"