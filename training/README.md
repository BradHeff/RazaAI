# Training seeds

`identity_origin_v4_seed.jsonl` contains reviewed examples of RazaAI's origin: Brad Heffernan began the chatbot in 2019 and resumed development in 2024. The runtime enforces these facts independently of model training.

Private coding traces and corrected datasets stay under the ignored `training/coder_v2_seed/` directory. `scripts/export_coder_seed.py` collects failed plans, accepts reviewed corrections and exports chat-format examples. Verify each corrected plan against its original workspace before training on it.

See the [training guide](../README_TRAINING.md) for environments, evaluation and model deployment. Adding a seed does not trigger training.
