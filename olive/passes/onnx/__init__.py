# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------
from olive.passes.onnx.append_pre_post_processing_ops import AppendPrePostProcessingOps
from olive.passes.onnx.conversion import DeviceSpecificOnnxConversion, OnnxConversion
from olive.passes.onnx.float16_conversion import OnnxFloatToFloat16
from olive.passes.onnx.inc_quantization import IncDynamicQuantization, IncQuantization, IncStaticQuantization
from olive.passes.onnx.insert_beam_search import InsertBeamSearch
from olive.passes.onnx.mixed_precision import OrtMixedPrecision
from olive.passes.onnx.model_optimizer import OnnxModelOptimizer
from olive.passes.onnx.moe_experts_distributor import MoEExpertsDistributor
from olive.passes.onnx.optimum_conversion import OptimumConversion
from olive.passes.onnx.optimum_merging import OptimumMerging
from olive.passes.onnx.perf_tuning import OrtPerfTuning
from olive.passes.onnx.quantization import OnnxDynamicQuantization, OnnxQuantization, OnnxStaticQuantization
from olive.passes.onnx.sharding import Sharding
from olive.passes.onnx.transformer_optimization import OrtTransformersOptimization
from olive.passes.onnx.vitis_ai_quantization import VitisAIQuantization

__all__ = [
    "AppendPrePostProcessingOps",
    "DeviceSpecificOnnxConversion",
    "IncDynamicQuantization",
    "IncQuantization",
    "IncStaticQuantization",
    "InsertBeamSearch",
    "MoEExpertsDistributor",
    "OnnxConversion",
    "OnnxDynamicQuantization",
    "OnnxFloatToFloat16",
    "OnnxModelOptimizer",
    "OnnxQuantization",
    "OnnxStaticQuantization",
    "OptimumConversion",
    "OptimumMerging",
    "OrtMixedPrecision",
    "OrtPerfTuning",
    "OrtTransformersOptimization",
    "Sharding",
    "VitisAIQuantization",
]
