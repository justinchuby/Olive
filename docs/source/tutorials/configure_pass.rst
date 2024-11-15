.. _how_to_configure_pass:

How To Configure Pass
=====================

This document describes how to configure a Pass.

When configuring a Pass, the user can chose to set the values of parameters to their default value (no search), pre-defined search space
(search for the best value from the possible options) or a combination of the two (fix some parameters to a certain value, default or
user provided, and/or search for other parameters).

To fully configure a Pass, we need :code:`type` and :code:`config`.

* :code:`type`: This is the type of the Pass. Check out :ref:`passes` for the full list of supported Passes.
* :code:`config`: This is a dictionary of the config parameters and values. It must contain all required parameters.
  For optional parameters the default value or default searchable values can be overridden by providing user defined
  values. You can also assign the value for a specific parameter as :code:`"DEFAULT_VALUE"` to use the default value
  or :code:`"SEARCHABLE_VALUES"` to use the default searchable values (if available).

Let's take the example of the :ref:`onnx_quantization` Pass:

.. tabs::
    .. tab:: Config JSON

        .. code-block:: json

            {
                "type": "OnnxQuantization",
                "data_config": "calib_data_config",
                // set per_channel to "DEFAULT_VALUE"
                "per_channel": "DEFAULT_VALUE",
                // set reduce_range to "SEARCHABLE_VALUES" value
                "reduce_range": "SEARCHABLE_VALUES",
                // user defined value for weight_type
                "weight_type": "QUInt8"
            }

        .. note::
            :code:`type` is case insensitive.



    .. tab:: Python Class

        .. code-block:: python

            from olive.passes import OnnxQuantization
            from olive.passes.olive_pass import create_pass_from_dict

            onnx_quantization = create_pass_from_dict(OnnxQuantization,
                config={
                    "data_config": "calib_data_config",
                    # set per_channel to "DEFAULT_VALUE" value
                    "per_channel": "DEFAULT_VALUE",
                    # set reduce_range to "SEARCHABLE_VALUES"
                    "reduce_range": "SEARCHABLE_VALUES"
                    # user defined value for weight_type
                    "weight_type": "QUInt8"
                },
            )
