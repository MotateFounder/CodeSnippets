def chat_settings():
    return {
        "key": "chat",
        "title": "Chat",
        "description": "Control how answers are generated during normal chat.",
        "sections": [
            {
                "title": "Response Behavior",
                "subsections": [
                    {
                        "title": "Everyday chat settings",
                        "fields": [
                            {
                                "key": "context.wrapper_prompt",
                                "label": "Context instruction",
                                "type": "multiline",
                                "default": (
                                    "Use the following selected context and reasoning artifacts. "
                                    "If context is insufficient, say what is missing instead of inventing APIs."
                                ),
                                "description": "Instruction placed before attached context in chat requests.",
                                "used": True,
                                "height": 4,
                            },
                            {
                                "key": "reasoning.enabled_by_default",
                                "label": "Enable reasoning",
                                "type": "bool",
                                "default": False,
                                "description": "Use the reasoning workflow for Set Context by default.",
                                "used": True,
                            },
                        ],
                    },
                    {
                        "title": "Generation tuning",
                        "advanced": True,
                        "fields": [
                            {
                                "key": "generation.temperature",
                                "label": "Creativity",
                                "type": "float",
                                "default": 0.2,
                                "description": "Lower values make answers more deterministic. Higher values make wording more varied.",
                                "used": True,
                            },
                            {
                                "key": "generation.max_tokens",
                                "label": "Maximum answer tokens",
                                "type": "int",
                                "default": 0,
                                "description": "Optional response length limit. 0 lets the provider decide.",
                                "used": True,
                            },
                            {
                                "key": "generation.reasoning_temperature",
                                "label": "Reasoning creativity",
                                "type": "float",
                                "default": 0.1,
                                "description": "Temperature for internal reasoning-stage calls.",
                                "used": True,
                            },
                        ],
                    },
                ],
            },
        ],
    }
