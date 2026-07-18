import re


VARIABLE_PATTERN = re.compile(r"{{\s*([^{}\[\]\r\n]+?)\s*}}|\[([^\[\]\r\n]+?)\]")


def detect_variables(template):
    names = []
    seen = set()
    for match in VARIABLE_PATTERN.finditer(template or ""):
        name = variable_name(match)
        if name not in seen:
            seen.add(name)
            names.append(name)
    return names


def replace_variables(template, values):
    values = values or {}

    def replacement(match):
        name = variable_name(match)
        return str(values.get(name, ""))

    return VARIABLE_PATTERN.sub(replacement, template or "")


def replace_variables_partial(template, values):
    values = values or {}

    def replacement(match):
        name = variable_name(match)
        value = str(values.get(name, ""))
        return value if value.strip() else match.group(0)

    return VARIABLE_PATTERN.sub(replacement, template or "")


def variable_name(match):
    return str(match.group(1) or match.group(2) or "").strip()
