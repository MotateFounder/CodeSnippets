def prompts_reasoning_settings():
    return {
        "key": "prompts_reasoning",
        "title": "Prompts & Reasoning",
        "advanced_only": True,
        "description": "Manage prompt presets and the optional reasoning workflow. Internal stage prompts and limits are advanced controls.",
        "sections": [
            {
                "title": "Reasoning Workflow",
                "subsections": [
                    {
                        "title": "Everyday reasoning settings",
                        "fields": [
                            {
                                "key": "reasoning.visible_trace_lines",
                                "label": "Visible reasoning lines",
                                "type": "int",
                                "default": 4,
                                "description": "How many progress lines each reasoning card shows before scrolling.",
                                "used": True,
                            },
                            {
                                "key": "prompt_presets.csv_path",
                                "label": "Prompt preset CSV",
                                "type": "string",
                                "default": "Prompts.csv",
                                "description": "CSV file used to load reusable prompt presets.",
                                "used": True,
                            },
                        ],
                    },
                    {
                        "title": "Advanced reasoning limits",
                        "advanced": True,
                        "fields": [
                            {
                                "key": "reasoning.max_stage_context_chars",
                                "label": "Max stage context chars",
                                "type": "int",
                                "default": 12000,
                                "description": "Maximum context characters passed to each internal reasoning stage.",
                                "used": True,
                            },
                            {
                                "key": "reasoning.max_final_artifact_chars",
                                "label": "Max final artifact chars",
                                "type": "int",
                                "default": 16000,
                                "description": "Maximum generated reasoning artifact text retained for the final answer.",
                                "used": True,
                            },
                            {
                                "key": "reasoning.max_retrieval_targets",
                                "label": "Max retrieval targets",
                                "type": "int",
                                "default": 10,
                                "description": "Maximum targets produced by the retrieval planning stage.",
                                "used": True,
                            },
                            {
                                "key": "reasoning.max_followup_targets",
                                "label": "Max follow-up targets",
                                "type": "int",
                                "default": 6,
                                "description": "Maximum follow-up retrieval targets produced after missing-context analysis.",
                                "used": True,
                            },
                            {
                                "key": "reasoning.max_identifier_report_items",
                                "label": "Max identifier report items",
                                "type": "int",
                                "default": 24,
                                "description": "Maximum identifiers shown in internal context reports.",
                                "used": True,
                            },
                        ],
                    },
                ],
            },
        ],
    }
