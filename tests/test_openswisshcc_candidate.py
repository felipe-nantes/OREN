from pathlib import Path

from dtwin.medgemma_client import load_screening_config


CONFIG = Path("configs/medgemma_local_4b_multiphase_fast_pathology.yaml")


def test_candidate_config_is_single_call_low_latency_pathology_target():
    config = load_screening_config(CONFIG)
    assert config["panel"]["mode"] == "multiphase_fusion"
    assert config["panel"]["strategy"] == "uniform_9"
    assert config["panel"]["fusion"]["channel_map"] == {
        "red": "art", "green": "pv", "blue": "del"
    }
    assert config["medgemma"]["timeout_seconds"] == 120
    assert config["medgemma"]["max_retries"] == 0
    assert config["medgemma"]["response_validation_max_retries"] == 0
    assert config["medgemma"]["response_mode"] == "prefilled_label"
    assert config["medgemma"]["max_output_tokens"] == 64
    assert config["rag"]["enabled"] is False


def test_candidate_prompt_separates_pathology_from_benign_variants():
    prompt = load_screening_config(CONFIG)["prompt"]["template"].lower()
    for text in (
        "vermelho", "verde", "azul", "lesão focal hepática",
        "variante vascular benigna", "estrutura tubular contínua",
        "registro", "inconclusiva", "revisão humana obrigatória",
    ):
        assert text in prompt

