import os
import shlex
import subprocess
import sys
import webbrowser
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[2]
LLAMA_CPP_DIR = APP_ROOT / "src" / "assets" / "LlamaCPP"
LLAMA_MODELS_DIR = APP_ROOT / "src" / "assets" / "llmmodels"
LLAMA_UI_DIR = LLAMA_CPP_DIR / "ui"
DEFAULT_LLAMA_CONTEXT_SIZE = 8192


def llama_server_executable():
    name = "llama-server.exe" if os.name == "nt" else "llama-server"
    return LLAMA_CPP_DIR / name


def list_gguf_models():
    LLAMA_MODELS_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(path for path in LLAMA_MODELS_DIR.glob("*.gguf") if path.is_file())


def default_model_path():
    models = list_gguf_models()
    return min(models, key=lambda path: path.stat().st_size) if models else Path()


def normalized_llamacpp_path(value, fallback, filename_match=False):
    path = Path(value) if value else Path()
    if path.exists():
        return path
    fallback = Path(fallback)
    if filename_match and path.name:
        candidate = fallback.parent / path.name
        if candidate.exists():
            return candidate
    return fallback


def llama_base_url(host="0.0.0.0", port=8080):
    display_host = "localhost" if str(host or "").strip() in {"", "0.0.0.0", "::"} else str(host).strip()
    return "http://{0}:{1}".format(display_host, int(port or 8080))


def build_llama_server_command(settings=None, model_path=None, context_size=None):
    settings = settings or {}
    executable = normalized_llamacpp_path(settings.get("executable_path"), llama_server_executable())
    host = str(settings.get("host", "0.0.0.0") or "0.0.0.0")
    port = int(settings.get("port", 8080) or 8080)
    ui_path = normalized_llamacpp_path(settings.get("ui_path"), LLAMA_UI_DIR)
    selected_model = normalized_llamacpp_path(
        model_path or settings.get("model_path"),
        default_model_path(),
        filename_match=True,
    )
    ctx_size = int(context_size or settings.get("ctx_size", DEFAULT_LLAMA_CONTEXT_SIZE) or DEFAULT_LLAMA_CONTEXT_SIZE)
    gpu_layers = str(settings.get("n_gpu_layers", "0") or "0")
    parallel = int(settings.get("parallel", 1) or 1)
    flash_attn = str(settings.get("flash_attn", "off") or "off")
    fit = str(settings.get("fit", "off") or "off")

    command = [
        os.fspath(executable),
        "--host",
        host,
        "--port",
        str(port),
        "--path",
        os.fspath(ui_path),
        "-m",
        os.fspath(selected_model),
        "--ctx-size",
        str(ctx_size),
        "--n-gpu-layers",
        gpu_layers,
        "--parallel",
        str(parallel),
        "--flash-attn",
        flash_attn,
        "--fit",
        fit,
    ]
    append_optional_int(command, settings, "n_cpu_moe", ["-ncmoe"])
    append_optional_value(command, settings, "reasoning", ["--reasoning"])
    append_optional_value(command, settings, "cache_type_k", ["--cache-type-k"])
    append_optional_value(command, settings, "cache_type_v", ["--cache-type-v"])
    append_optional_value(command, settings, "cache_type_k_draft", ["--cache-type-k-draft"])
    append_optional_value(command, settings, "cache_type_v_draft", ["--cache-type-v-draft"])
    append_optional_value(command, settings, "spec_type", ["--spec-type"])
    append_optional_int(command, settings, "spec_draft_n_max", ["--spec-draft-n-max"])
    append_optional_value(command, settings, "temperature", ["--temp"])
    append_optional_value(command, settings, "top_p", ["--top-p"])
    append_optional_int(command, settings, "top_k", ["--top-k"])
    append_optional_value(command, settings, "min_p", ["--min-p"])
    append_optional_value(command, settings, "presence_penalty", ["--presence-penalty"])
    append_optional_value(command, settings, "repeat_penalty", ["--repeat-penalty"])
    append_optional_int(command, settings, "verbosity", ["-lv"])
    append_optional_flag(command, settings, "cache_idle_slots", "--cache-idle-slots")
    append_optional_flag(command, settings, "kv_unified", "--kv-unified")
    append_optional_value(command, settings, "alias", ["-a"])
    extra_args = str(settings.get("extra_args", "") or "").strip()
    if extra_args:
        command.extend(shlex.split(extra_args, posix=(os.name != "nt")))
    return command


def append_optional_value(command, settings, key, flag):
    value = settings.get(key, "")
    if value is None:
        return
    value = str(value).strip()
    if not value:
        return
    command.extend(flag + [value])


def append_optional_int(command, settings, key, flag):
    value = settings.get(key, 0)
    try:
        number = int(value or 0)
    except (TypeError, ValueError):
        return
    if number <= 0:
        return
    command.extend(flag + [str(number)])


def append_optional_flag(command, settings, key, flag):
    if bool(settings.get(key, False)):
        command.append(flag)


def launch_llama_server(settings=None, model_path=None, context_size=None):
    command = build_llama_server_command(settings=settings, model_path=model_path, context_size=context_size)
    executable = Path(command[0])
    if not executable.exists():
        raise FileNotFoundError("Llama.cpp server executable not found: {0}".format(executable))
    if "-m" in command:
        model = Path(command[command.index("-m") + 1])
        if not model.exists():
            raise FileNotFoundError("GGUF model not found: {0}".format(model))

    if os.name == "nt":
        return subprocess.Popen(command, cwd=os.fspath(executable.parent), creationflags=subprocess.CREATE_NEW_CONSOLE)
    if sys.platform == "darwin":
        script = "cd {0} && {1}".format(
            shlex.quote(os.fspath(executable.parent)),
            " ".join(shlex.quote(part) for part in command),
        )
        return subprocess.Popen(["osascript", "-e", 'tell app "Terminal" to do script "{0}"'.format(script.replace('"', '\\"'))])
    return subprocess.Popen(command, cwd=os.fspath(executable.parent))


def open_llama_browser(host="0.0.0.0", port=8080):
    webbrowser.open(llama_base_url(host=host, port=port))
