# Changes

## 20.16.0

Both profiles open the terminal by default. `code [directory]` starts a coding workspace. The optional browser is exclusive to the workstation profile.

* Added `razaai` for RTX 4080 and larger GPUs, and `razaai-8g` for the Jetson Orin Nano 8 GB. Profiles select models, context limits, prompt batches, ports and separate state directories.
* Added model setup from public sources, existing Ollama models or local GGUF files. Explicit model overrides now take effect.
* Replaced the architecture-specific installation lock with dependency resolution on the target device. User service installation uses the actual checkout path and account.
* Fixed overlapping requests creating separate agents for the same session. Busy sessions cannot be deleted. Incoming connection counts and malformed request bodies are bounded.
* Applied profile memory limits to model warmup and inference.
* Updated the browser interface, keyboard controls, token storage and stream error handling.
* Removed credentials, private field notes, generated data and obsolete development output from the public source set. Files remain available locally.
* Removed retired training experiments, fixed model templates and duplicate milestone runners. Model setup generates definitions from the current hardware profile.
* Rewrote the README and setup guides, added interface screenshots and an MIT licence, and shortened source comments.

Earlier development notes are retained locally. Hardware validation requirements are in the developer guide.
