# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------

import argparse
import json
import os
import shutil
import urllib.request
import warnings
from pathlib import Path

import config
from run_llama_v2_io_binding import run_llama_v2_io_binding

from olive.model import ONNXModel
from olive.workflows import run as olive_run


def optimize(optimized_model_dir: Path):
    script_dir = Path(__file__).resolve().parent
    model_info = dict()
    submodel_names = ["argmax_sampling", "update_embeddings", "llama_v2"]

    for submodel_name in submodel_names:
        print(f"\nOptimizing {submodel_name}")

        olive_config = None
        with open(script_dir / f"config_{submodel_name}.json", "r") as fin:
            olive_config = json.load(fin)

        olive_run(olive_config)

        footprints_file_path = (
            Path(__file__).resolve().parent / "footprints" / f"{submodel_name}_gpu-dml_footprints.json"
        )
        with footprints_file_path.open("r") as footprint_file:
            footprints = json.load(footprint_file)

            conversion_footprint = None
            optimizer_footprint = None
            merging_footprint = None
            for _, footprint in footprints.items():
                if footprint["from_pass"] == "OnnxConversion":
                    conversion_footprint = footprint
                elif footprint["from_pass"] == "OrtTransformersOptimization":
                    optimizer_footprint = footprint
                elif footprint["from_pass"] == "OptimumMerging":
                    merging_footprint = footprint

            assert conversion_footprint is not None

            if submodel_name == "llama_v2":
                assert optimizer_footprint is not None
                assert merging_footprint is not None
                optimized_olive_model = ONNXModel(**merging_footprint["model_config"]["config"])
            else:
                optimized_olive_model = ONNXModel(**conversion_footprint["model_config"]["config"])

            model_info[submodel_name] = {
                "optimized": {
                    "path": Path(optimized_olive_model.model_path),
                },
            }

            print(f"Optimized Model   : {model_info[submodel_name]['optimized']['path']}")
    optimized_model_dir.stem
    print("Copying optimized models...")
    for submodel_name in submodel_names:
        src_path = model_info[submodel_name]["optimized"]["path"]
        dst_path = optimized_model_dir / submodel_name / src_path.name
        os.makedirs(os.path.dirname(dst_path), exist_ok=True)
        shutil.copyfile(src_path, dst_path)

        src_weights_path = src_path.with_suffix(".onnx.data")
        if src_weights_path.is_file():
            dst_weights_path = dst_path.with_suffix(".onnx.data")
            shutil.copyfile(src_weights_path, dst_weights_path)

    raw_data_folder = Path(__file__).resolve().parent / "raw_model_data" / "7B-chat"
    raw_data_folder.mkdir(exist_ok=True, parents=True)
    src_tokenizer_path = raw_data_folder / "tokenizer.model"
    dst_tokenizer_path = optimized_model_dir / "tokenizer.model"
    shutil.copyfile(src_tokenizer_path, dst_tokenizer_path)

    print(f"The optimized pipeline is located here: {optimized_model_dir}")


def download_checkpoint():
    model_size = "7B-chat"
    model_name = "llama-2-7b-chat"

    raw_data_folder = Path(__file__).resolve().parent / "raw_model_data" / model_size
    raw_data_folder.mkdir(exist_ok=True, parents=True)

    license_path = raw_data_folder / "LICENSE"
    use_policy_path = raw_data_folder / "USE_POLICY.md"
    tokenizer_path = raw_data_folder / "tokenizer.model"
    weights_path = raw_data_folder / f"{model_name}.pth"

    opener = urllib.request.build_opener()
    opener.addheaders = [("User-agent", "wget")]
    urllib.request.install_opener(opener)

    if not (
        license_path.is_file() and use_policy_path.is_file() and tokenizer_path.is_file() and weights_path.is_file()
    ):
        email_url = input(
            "URL from the e-mail that was received after requesting access from "
            "https://ai.meta.com/resources/models-and-libraries/llama-downloads/ (only valid for 24h): "
        )

    if not license_path.is_file():
        print("Downloading LICENSE")
        urllib.request.urlretrieve(email_url.replace("*", "LICENSE"), license_path)

    if not use_policy_path.is_file():
        print("Downloading Acceptable Usage Policy")
        urllib.request.urlretrieve(email_url.replace("*", "USE_POLICY.md"), use_policy_path)

    if not tokenizer_path.is_file():
        print("Downloading tokenizer")
        urllib.request.urlretrieve(email_url.replace("*", "tokenizer.model"), tokenizer_path)

    if not weights_path.is_file():
        print(f"Downloading {model_name}")
        urllib.request.urlretrieve(email_url.replace("*", f"{model_name}/consolidated.00.pth"), weights_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--embeddings_file",
        type=str,
        help="The embeddings.pth file downloaded from the 7B_FT_float16 submodule located at "
        "https://github.com/microsoft/Llama-2-Onnx",
    )
    parser.add_argument("--optimize", action="store_true", help="Runs the optimization step")
    parser.add_argument("--prompt", default="What is the lightest element?", type=str)
    parser.add_argument("--max_seq_len", default=2048, type=int, help="The size of the cache")
    parser.add_argument(
        "--max_gen_len", default=256, type=int, help="The maximum number of tokens that can be included in an answer"
    )
    args = parser.parse_args()

    config.embeddings_file = args.embeddings_file

    script_dir = Path(__file__).resolve().parent
    optimized_model_dir = script_dir / "models" / "optimized" / "llama_v2"

    if args.optimize or not optimized_model_dir.exists():
        if not args.embeddings_file:
            print("--embeddings_file needs to be provided when the model hasn't been optimized yet")
            exit(1)

        download_checkpoint()
        optimize(optimized_model_dir)

    if not args.optimize:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            run_llama_v2_io_binding(args.prompt, args.max_seq_len, args.max_gen_len)
