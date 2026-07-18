def appearance_settings(appearance_color_field):
    settings = {
        "key": "appearance",
        "title": "Appearance",
        "description": "Choose the visual theme.",
        "sections": [
            {
                "title": "Theme",
                "subsections": [
                    {
                        "title": "Watercolor Presets",
                        "fields": [
                            {
                                "key": "appearance.theme",
                                "label": "Theme",
                                "type": "choice",
                                "choices": [
                                    "Night Watercolor",
                                    "Night Lavender Wash",
                                    "Day Watercolor",
                                    "Day Rose Mist",
                                    "Day Sage Wash",
                                    "Neon Rose Circuit",
                                    "Nuclear Terminal",
                                    "Soft Vintage Studio",
                                    "Precision Machine",
                                    "Retro Computing",
                                ],
                                "default": "Night Watercolor",
                                "description": "Soft pastel themes for night and day modes.",
                                "used": True,
                            },
                        ],
                    },
                    {
                        "title": "Text Sizes",
                        "advanced": True,
                        "fields": [
                            {
                                "key": "appearance.text.base",
                                "label": "Base text size",
                                "type": "int",
                                "default": 9,
                                "description": "General UI text size.",
                                "used": True,
                            },
                            {
                                "key": "appearance.text.small",
                                "label": "Small text size",
                                "type": "int",
                                "default": 8,
                                "description": "Helper labels, timestamps, and compact metadata.",
                                "used": True,
                            },
                            {
                                "key": "appearance.text.title",
                                "label": "Title text size",
                                "type": "int",
                                "default": 10,
                                "description": "Section and panel title size.",
                                "used": True,
                            },
                            {
                                "key": "appearance.text.code",
                                "label": "Code text size",
                                "type": "int",
                                "default": 9,
                                "description": "Code editors, snippets, prompts, and multiline text areas.",
                                "used": True,
                            },
                        ],
                    },
                ],
            },
            {
                "title": "Color Overrides",
                "advanced": True,
                "subsections": [
                    {
                        "title": "Main Palette",
                        "advanced": True,
                        "fields": [
                            appearance_color_field("bg", "Background"),
                            appearance_color_field("panel", "Panel"),
                            appearance_color_field("panel2", "Raised panel"),
                            appearance_color_field("editor", "Editor"),
                            appearance_color_field("text", "Text"),
                            appearance_color_field("muted", "Muted text"),
                            appearance_color_field("line", "Lines"),
                            appearance_color_field("accent", "Accent"),
                            appearance_color_field("select", "Selection"),
                            appearance_color_field("highlight", "Search highlight"),
                            appearance_color_field("highlight_text", "Highlight text"),
                        ],
                    },
                    {
                        "title": "Syntax Colors",
                        "advanced": True,
                        "fields": [
                            appearance_color_field("keyword", "Keyword"),
                            appearance_color_field("string", "String"),
                            appearance_color_field("comment", "Comment"),
                            appearance_color_field("number", "Number"),
                        ],
                    },
                ],
            },
        ],
    }
    return settings
