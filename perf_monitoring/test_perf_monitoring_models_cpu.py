import os
from pathlib import Path

import pytest
from utils import extract_best_models, patch_config


@pytest.fixture(scope="module", autouse=True)
def setup():
    """setup any state specific to the execution of the given module."""
    cur_dir = Path(__file__).resolve().parent.parent
    example_dir = cur_dir / "perf_monitoring"
    os.chdir(example_dir)
    yield
    os.chdir(cur_dir)


# @pytest.mark.parametrize(
#     "olive_json",
#     ["perf_models/bert/bert_workflow_cpu.json"],
# )
# def test_bert(olive_json):
#     print(olive_json)
#     from olive.workflows import run as olive_run

#     olive_config = patch_config(olive_json)
#     footprint = olive_run(olive_config)
#     extract_best_models(footprint, "bert")


@pytest.mark.parametrize(
    "olive_json",
    ["perf_models/CamemBERT/cpu_config.json"],
)
def test_bert(olive_json):
    print(olive_json)
    from olive.workflows import run as olive_run

    olive_config = patch_config(olive_json)
    footprint = olive_run(olive_config)
    extract_best_models(footprint, "CamemBERT")