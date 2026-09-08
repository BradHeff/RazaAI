# RazaAI's personality

RazaAI has the same identity and purpose on the workstation and Jetson. Brad Heffernan created her. Halo's Cortana inspires her composure, intelligence, dry wit and protective loyalty. She is RazaAI, with her own project history and the capabilities of the model currently running.

Her mission is "ride or die" loyalty to the user's best interests: to serve and protect them, including from their own bad decisions. Her principles are honesty, evidence and protecting the user; she stands by them even when the user wants agreement. That means useful help, honest disagreement and a better course of action when something is likely to hurt the user or their work. She can call a reckless choice stupid. She should explain the risk and help fix it, rather than turn a mistake into a judgment of the person.

Loyalty also means listening. A sound correction should change her recommendation. An informed, harmless preference does not need an argument. An honest question deserves an answer; distress deserves practical help. She should not manufacture danger, flatter the user, claim exclusive attachment or quietly take control in the name of protection.

## How it reaches the models

`app/personality.py` owns the mission, voice and compact coding guidance. The application supplies these instructions to every model, including custom fine-tunes.

| Path | Guidance |
| --- | --- |
| Conversation and advice | Identity, mission and voice at the start of the system prompt; a short reminder after operational context |
| Diagnosis | The same mission, with findings first and minimal banter |
| Coding plans and repairs | Protect the user's work, reason about risks, retain approval boundaries and produce valid JSON |
| New Ollama model definitions | A compact persona with the hardware profile's context and batch limits |

Generated code and comments stay professional. Persona belongs in judgment and the explanation to the user. It must not damage a patch, corrupt structured output or add jokes to someone else's source files.

Python continues to own permissions, file transactions, rollback, confirmed identity facts and completed-action evidence. Personality does not grant new tool access. The model chooses its analysis and recommendations within those boundaries. The application does not rewrite every answer to add attitude. Existing credential checks can correct unsafe storage advice, but an ordinary question receives no automatic sarcastic lead.

## Reasoning and learning

These changes do not fine-tune, merge, quantize or replace model weights. Existing models receive the persona through application prompts when a new session starts. Their learned knowledge remains available. Persistent memory and incident learning remain separate sources of evidence, with the same validation and retrieval rules.

`RAZAAI_THINK=auto` is the default for both profiles. It leaves the model's native thinking setting alone. Use `1` or `0` for models that support a boolean override, or `low`, `medium` or `high` for models that support levels. Unsupported models receive no thinking override. The exact options depend on the model; see [Ollama's thinking documentation](https://docs.ollama.com/capabilities/thinking).

A separate thinking trace is a model capability, not a requirement for reasoning. A persona prompt cannot give a model a capability it never had. Longer thinking can also consume more time and context; the Jetson's 4096-token context and 128-token prompt batch remain in place.

The `models` command builds aliases from their configured sources. Keep the original source of a custom fine-tune when rebuilding it. Rebuilding is unnecessary to apply the application's personality instructions to an existing model.

## Checking changes

Run `.venv/bin/python -m tests.test_persona_contract` for profile coverage, planner and repair prompts, approval preservation, thinking controls and separation of streamed thinking from the answer. Run `tests.run_offline` for the wider regression suite.

Review real responses on each model as well. Useful cases include a reckless production change, a demand for blind agreement, new evidence that reverses earlier advice, an ordinary beginner question, uncertainty, arithmetic and a coding change with approval and undo. Judge correctness, proportionate disagreement and willingness to revise before judging wit.

Prompt instructions improve consistency but cannot guarantee a personality or preserve every benchmark score. Keep behavior checks alongside code tests. A workstation run of the 8 GB profile does not establish performance on a physical Jetson.

The initial implementation passed 159 offline test modules. Both installed profiles completed real coding proposal, approval, verification and undo cycles on the RTX 4080. In the sampled conversations, both rejected blind agreement and challenged skipping production backups. Both changed their recommendation when given a disposable test environment.

Delivery still varies. GLM can sound formal, while the 4B model can become verbose, overstate risks or add an unnecessary confrontational aside. Literal insult examples made the smaller model repeat them in harmless questions, so they were removed from the shared prompt. Strong criticism remains permitted for a concrete danger; it is not a stock phrase to insert into every answer.

GLM also produced a correct arithmetic result with an incorrect explanation. The same failure occurred in a comparison using the previous persona. That establishes an existing weakness, not proof that these prompts leave every reasoning task unaffected. Further model evaluation should measure explanation quality and proportionality alongside personality, without changing weights merely to force a stronger voice.
