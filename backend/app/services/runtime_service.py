from __future__ import annotations

import ast
import asyncio
import base64
import importlib
import inspect
import json
import os
import re
import shutil
import threading
import tracemalloc
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

from ..schemas.model_runtime import (
    ExecutionError,
    NodeCapability,
    NodeExecutionRequest,
    NodeExecutionResponse,
    PROTOCOL_VERSION,
    RuntimeHealth,
    RuntimeMetrics,
    RuntimeTraceEntry,
    SUPPORTED_PROTOCOL_MAJOR
)


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    raw = os.environ.get(name)
    try:
        value = int(raw) if raw is not None else default
    except (TypeError, ValueError):
        value = default
    return max(minimum, value)


def _resolve_models_dir() -> Path:
    configured = os.environ.get('TOKENFLOW_MODELS_DIR', 'models')
    path = Path(configured).expanduser()
    if path.is_absolute():
        return path
    backend_dir = Path(__file__).parent.parent.parent
    return backend_dir / path


def _resolve_runtime_temp_dir() -> Path:
    configured = os.environ.get('TOKENFLOW_RUNTIME_TEMP_DIR', '').strip()
    if configured:
        path = Path(configured).expanduser()
        if path.is_absolute():
            return path
        backend_dir = Path(__file__).parent.parent.parent
        return backend_dir / path
    storage_dir = os.environ.get('TOKENFLOW_STORAGE_DIR', './storage').strip() or './storage'
    storage_path = Path(storage_dir).expanduser()
    backend_dir = Path(__file__).parent.parent.parent
    if not storage_path.is_absolute():
        storage_path = backend_dir / storage_path
    return storage_path / 'runtime_tmp'


def _resolve_runtime_audit_log_path() -> Path:
    configured = os.environ.get('TOKENFLOW_RUNTIME_AUDIT_LOG_PATH', '').strip()
    if configured:
        path = Path(configured).expanduser()
        if path.is_absolute():
            return path
        backend_dir = Path(__file__).parent.parent.parent
        return backend_dir / path
    storage_dir = os.environ.get('TOKENFLOW_STORAGE_DIR', './storage').strip() or './storage'
    storage_path = Path(storage_dir).expanduser()
    backend_dir = Path(__file__).parent.parent.parent
    if not storage_path.is_absolute():
        storage_path = backend_dir / storage_path
    return storage_path / 'runtime_audit.log'


def _allowed_imports() -> set[str]:
    configured = os.environ.get(
        'TOKENFLOW_RUNTIME_ALLOWED_IMPORTS',
        'math,json,re,statistics,itertools,functools,collections,datetime,decimal,random,numpy'
    )
    values = [item.strip() for item in configured.split(',')]
    return {item for item in values if item}


def _allowed_models() -> set[str]:
    configured = os.environ.get('TOKENFLOW_RUNTIME_ALLOWED_MODELS', '').strip()
    values = [item.strip() for item in configured.split(',')] if configured else []
    if values:
        return {item for item in values if item}
    if TOKENFLOW_MODELS_DIR.exists() and TOKENFLOW_MODELS_DIR.is_dir():
        return {
            item.name
            for item in TOKENFLOW_MODELS_DIR.iterdir()
            if item.is_file() and item.suffix.lower() == '.gguf'
        }
    return set()


TOKENFLOW_MODELS_DIR = _resolve_models_dir()
TOKENFLOW_RUNTIME_TEMP_DIR = _resolve_runtime_temp_dir()
TOKENFLOW_RUNTIME_AUDIT_LOG_PATH = _resolve_runtime_audit_log_path()
TOKENFLOW_RUNTIME_ALLOWED_IMPORTS = _allowed_imports()
TOKENFLOW_RUNTIME_ALLOWED_MODELS = _allowed_models()
TOKENFLOW_RUNTIME_DEFAULT_MODEL = os.environ.get('TOKENFLOW_RUNTIME_DEFAULT_MODEL', '').strip()
TOKENFLOW_RUNTIME_MODEL_BACKEND = os.environ.get('TOKENFLOW_RUNTIME_MODEL_BACKEND', 'llama-cpp-python').strip() or 'llama-cpp-python'
TOKENFLOW_RUNTIME_TIMEOUT_SECONDS = _env_int('TOKENFLOW_RUNTIME_TIMEOUT_SECONDS', 20, minimum=1)
TOKENFLOW_RUNTIME_MAX_CONCURRENCY = _env_int('TOKENFLOW_RUNTIME_MAX_CONCURRENCY', 2, minimum=1)
TOKENFLOW_RUNTIME_MAX_QUEUE_LENGTH = _env_int('TOKENFLOW_RUNTIME_MAX_QUEUE_LENGTH', 16, minimum=1)
TOKENFLOW_RUNTIME_MAX_MEMORY_MB = _env_int('TOKENFLOW_RUNTIME_MAX_MEMORY_MB', 512, minimum=32)
TOKENFLOW_RUNTIME_CANCEL_GRACE_MS = _env_int('TOKENFLOW_RUNTIME_CANCEL_GRACE_MS', 250, minimum=0)
TOKENFLOW_RUNTIME_MAX_SOURCE_CHARS = _env_int('TOKENFLOW_RUNTIME_MAX_SOURCE_CHARS', 20000, minimum=1024)
TOKENFLOW_RUNTIME_MAX_RESOURCE_BYTES = _env_int('TOKENFLOW_RUNTIME_MAX_RESOURCE_BYTES', 5 * 1024 * 1024, minimum=1024)
TOKENFLOW_RUNTIME_MAX_OUTPUT_CHARS = _env_int('TOKENFLOW_RUNTIME_MAX_OUTPUT_CHARS', 200000, minimum=256)
TOKENFLOW_RUNTIME_MODEL_CTX = _env_int('TOKENFLOW_RUNTIME_MODEL_CTX', 4096, minimum=256)
TOKENFLOW_RUNTIME_MODEL_THREADS = _env_int('TOKENFLOW_RUNTIME_MODEL_THREADS', 4, minimum=1)

_RUNTIME_EXECUTOR = ThreadPoolExecutor(
    max_workers=TOKENFLOW_RUNTIME_MAX_CONCURRENCY,
    thread_name_prefix='tokenflow-runtime'
)
_RUNTIME_SEMAPHORE = asyncio.Semaphore(TOKENFLOW_RUNTIME_MAX_CONCURRENCY)
_RUNTIME_QUEUE_LOCK = threading.Lock()
_RUNTIME_PENDING = 0
_MODEL_CACHE: dict[str, Any] = {}
_MODEL_CACHE_LOCK = threading.Lock()

_FORBIDDEN_CALLS = {'eval', 'exec', 'compile', 'open', 'input', '__import__'}
_FORBIDDEN_ATTRIBUTES = {'__subclasses__', '__globals__', '__code__', '__mro__', '__getattribute__'}
_SECRET_PATTERN = re.compile(r'(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*([^\s,;]+)')
_USER_DATA_PATTERN = re.compile(r'(?i)(user(_id|name)?|email)\s*[:=]\s*([^\s,;]+)')
_EMAIL_PATTERN = re.compile(r'(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b')
_PATH_PATTERN_WINDOWS = re.compile(r'(?i)\b[A-Z]:\\[^\s"\'<>|]+')
_PATH_PATTERN_UNIX = re.compile(r'/(?:home|Users|var|tmp|etc|opt|srv|mnt)/[^\s"\'<>|]+')


class RuntimeExecutionError(Exception):
    def __init__(self, code: str, message: str, detail: Any = None, traceback_text: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail
        self.traceback_text = traceback_text


class RuntimeCancellation:
    def __init__(self):
        self._event = threading.Event()
        self.reason: str | None = None

    def cancel(self, reason: str):
        self.reason = reason
        self._event.set()

    def is_cancelled(self) -> bool:
        return self._event.is_set()


def _reserve_queue_slot():
    global _RUNTIME_PENDING
    with _RUNTIME_QUEUE_LOCK:
        if _RUNTIME_PENDING >= TOKENFLOW_RUNTIME_MAX_QUEUE_LENGTH:
            raise RuntimeExecutionError(
                'RESOURCE_LIMIT_EXCEEDED',
                'Runtime queue is full',
                detail={'max_queue_length': TOKENFLOW_RUNTIME_MAX_QUEUE_LENGTH}
            )
        _RUNTIME_PENDING += 1


def _release_queue_slot():
    global _RUNTIME_PENDING
    with _RUNTIME_QUEUE_LOCK:
        _RUNTIME_PENDING = max(0, _RUNTIME_PENDING - 1)


class _RuntimeAstValidator(ast.NodeVisitor):
    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            root = alias.name.split('.')[0]
            if root not in TOKENFLOW_RUNTIME_ALLOWED_IMPORTS:
                raise RuntimeExecutionError('UNSAFE_CODE', f'Import "{root}" is not allowed')
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        module_name = (node.module or '').split('.')[0]
        if module_name and module_name not in TOKENFLOW_RUNTIME_ALLOWED_IMPORTS:
            raise RuntimeExecutionError('UNSAFE_CODE', f'Import "{module_name}" is not allowed')
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id in _FORBIDDEN_CALLS:
            raise RuntimeExecutionError('UNSAFE_CODE', f'Call "{node.func.id}" is forbidden')
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute):
        if node.attr in _FORBIDDEN_ATTRIBUTES or node.attr.startswith('__'):
            raise RuntimeExecutionError('UNSAFE_CODE', f'Attribute "{node.attr}" is forbidden')
        self.generic_visit(node)


def _redact_text(value: Any) -> str:
    text = str(value)
    text = _SECRET_PATTERN.sub(r'\1=[REDACTED]', text)
    text = _USER_DATA_PATTERN.sub(r'\1=[REDACTED]', text)
    text = _EMAIL_PATTERN.sub('[EMAIL_REDACTED]', text)
    text = _PATH_PATTERN_WINDOWS.sub('[PATH_REDACTED]', text)
    text = _PATH_PATTERN_UNIX.sub('[PATH_REDACTED]', text)
    return text


def _trim_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return f'{text[:max_chars]}...[truncated]'


def _normalize_logs(logs: list[str], max_chars: int) -> list[str]:
    normalized: list[str] = []
    used = 0
    for line in logs:
        current = _trim_text(_redact_text(line), max_chars=max_chars)
        if used + len(current) > max_chars:
            remaining = max(0, max_chars - used)
            if remaining:
                normalized.append(current[:remaining])
            normalized.append('[logs truncated]')
            break
        normalized.append(current)
        used += len(current)
    return normalized


def _safe_output(value: Any, max_chars: int) -> Any:
    sanitized = _sanitize_output(value=value, max_chars=max_chars)
    if isinstance(sanitized, str):
        return _trim_text(sanitized, max_chars=max_chars)
    try:
        rendered = json.dumps(sanitized, ensure_ascii=False, default=str)
    except Exception:
        rendered = _redact_text(sanitized)
    if len(rendered) <= max_chars:
        return sanitized
    return _trim_text(rendered, max_chars=max_chars)


def _sanitize_output(value: Any, max_chars: int) -> Any:
    if isinstance(value, str):
        return _trim_text(_redact_text(value), max_chars=max_chars)
    if isinstance(value, dict):
        return {str(k): _sanitize_output(v, max_chars=max_chars) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_output(item, max_chars=max_chars) for item in value]
    if isinstance(value, tuple):
        return tuple(_sanitize_output(item, max_chars=max_chars) for item in value)
    if isinstance(value, set):
        return [_sanitize_output(item, max_chars=max_chars) for item in sorted(value, key=str)]
    return value


def _validate_protocol_version(version: str):
    parts = version.split('.')
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise RuntimeExecutionError('INVALID_REQUEST', f'Invalid protocol_version: {version}')
    major = int(parts[0])
    if major != SUPPORTED_PROTOCOL_MAJOR:
        raise RuntimeExecutionError(
            'UNSUPPORTED_PROTOCOL_VERSION',
            f'Unsupported protocol_version: {version}',
            detail={'supported_major': SUPPORTED_PROTOCOL_MAJOR}
        )


def _validate_source(source: str):
    if len(source) > TOKENFLOW_RUNTIME_MAX_SOURCE_CHARS:
        raise RuntimeExecutionError(
            'INVALID_REQUEST',
            f'module.source exceeds max length ({TOKENFLOW_RUNTIME_MAX_SOURCE_CHARS})'
        )
    try:
        parsed = ast.parse(source)
    except SyntaxError as exc:
        raise RuntimeExecutionError(
            'INVALID_REQUEST',
            f'Syntax error in module.source: {exc.msg}',
            detail={'lineno': exc.lineno, 'offset': exc.offset}
        ) from exc
    _RuntimeAstValidator().visit(parsed)


def _normalize_resources(payload: NodeExecutionRequest) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    consumed_bytes = 0
    for resource in payload.resources:
        if resource.kind == 'text':
            body = resource.text or ''
            size = len(body.encode('utf-8'))
        else:
            encoded = resource.base64_data or ''
            try:
                decoded = base64.b64decode(encoded, validate=True)
            except Exception as exc:
                raise RuntimeExecutionError(
                    'INVALID_REQUEST',
                    f'Invalid base64_data for resource "{resource.name}"'
                ) from exc
            size = len(decoded)
        consumed_bytes += size
        if consumed_bytes > TOKENFLOW_RUNTIME_MAX_RESOURCE_BYTES:
            raise RuntimeExecutionError(
                'INVALID_REQUEST',
                f'Resource payload exceeds {TOKENFLOW_RUNTIME_MAX_RESOURCE_BYTES} bytes',
                detail={'consumed_bytes': consumed_bytes}
            )
        normalized.append(resource.model_dump())
    return normalized


def _resolve_timeout_seconds(payload: NodeExecutionRequest) -> float:
    timeout_ms = payload.runtime.timeout_ms if payload.runtime else None
    if timeout_ms:
        return max(0.001, timeout_ms / 1000.0)
    return float(TOKENFLOW_RUNTIME_TIMEOUT_SECONDS)


def _resolve_output_limit(payload: NodeExecutionRequest) -> int:
    runtime_limit = payload.runtime.max_output_bytes if payload.runtime else None
    if not runtime_limit:
        return TOKENFLOW_RUNTIME_MAX_OUTPUT_CHARS
    return max(256, min(runtime_limit, TOKENFLOW_RUNTIME_MAX_OUTPUT_CHARS))


def _restricted_import(name: str, _globals=None, _locals=None, _fromlist=(), _level=0):
    root = name.split('.')[0]
    if root not in TOKENFLOW_RUNTIME_ALLOWED_IMPORTS:
        raise ImportError(f'Import "{root}" is not allowed')
    return importlib.import_module(name)


def _validate_model_name(model_name: str):
    if not model_name:
        raise RuntimeExecutionError('MODEL_NOT_ALLOWED', 'Model name is required')
    if len(model_name) > 120:
        raise RuntimeExecutionError('MODEL_NOT_ALLOWED', 'Model name is too long')
    if '/' in model_name or '\\' in model_name or '..' in model_name:
        raise RuntimeExecutionError('MODEL_NOT_ALLOWED', 'Invalid model name path')
    if not re.fullmatch(r'[A-Za-z0-9._-]+', model_name):
        raise RuntimeExecutionError('MODEL_NOT_ALLOWED', 'Model name format is invalid')
    if not model_name.lower().endswith('.gguf'):
        raise RuntimeExecutionError('MODEL_NOT_ALLOWED', 'Only .gguf model files are allowed')


def _resolve_model_path(model_name: str) -> Path:
    models_dir = TOKENFLOW_MODELS_DIR.resolve(strict=False)
    model_path = models_dir / model_name
    if not model_path.exists() or not model_path.is_file():
        raise RuntimeExecutionError('MODEL_NOT_ALLOWED', f'Model "{model_name}" not found in models directory')
    if model_path.is_symlink():
        raise RuntimeExecutionError('MODEL_NOT_ALLOWED', f'Model "{model_name}" symlink is not allowed')
    resolved = model_path.resolve(strict=True)
    try:
        resolved.relative_to(models_dir.resolve(strict=False))
    except ValueError as exc:
        raise RuntimeExecutionError('MODEL_NOT_ALLOWED', f'Model "{model_name}" escaped models directory') from exc
    return resolved


def _load_llama_model(model_name: str):
    _validate_model_name(model_name)
    if model_name not in TOKENFLOW_RUNTIME_ALLOWED_MODELS:
        raise RuntimeExecutionError('MODEL_NOT_ALLOWED', f'Model "{model_name}" is not in runtime whitelist')
    model_path = _resolve_model_path(model_name)
    with _MODEL_CACHE_LOCK:
        cached = _MODEL_CACHE.get(model_name)
        if cached is not None:
            return cached
        try:
            import llama_cpp
        except Exception as exc:
            raise RuntimeExecutionError(
                'RUNTIME_EXCEPTION',
                'llama-cpp-python is not installed',
                detail={'dependency': 'llama-cpp-python'}
            ) from exc
        model = llama_cpp.Llama(
            model_path=str(model_path),
            n_ctx=TOKENFLOW_RUNTIME_MODEL_CTX,
            n_threads=TOKENFLOW_RUNTIME_MODEL_THREADS,
            verbose=False
        )
        _MODEL_CACHE[model_name] = model
        return model


def _run_local_model(prompt: str, model_name: str | None = None, max_tokens: int = 256, temperature: float = 0.2):
    selected = model_name or TOKENFLOW_RUNTIME_DEFAULT_MODEL
    if not selected:
        raise RuntimeExecutionError('INVALID_REQUEST', 'model is required when run_local_model is used')
    llm = _load_llama_model(selected)
    try:
        response = llm.create_chat_completion(
            messages=[{'role': 'user', 'content': str(prompt)}],
            max_tokens=max_tokens,
            temperature=temperature
        )
    except Exception as exc:
        raise RuntimeExecutionError('RUNTIME_EXCEPTION', 'Local model inference failed') from exc
    try:
        return response['choices'][0]['message']['content']
    except Exception:
        return response


def _extract_model_name(payload: NodeExecutionRequest) -> str | None:
    model_value = payload.module.kwargs.get('model')
    if isinstance(model_value, str) and model_value.strip():
        return model_value.strip()
    model_name_value = payload.module.kwargs.get('model_name')
    if isinstance(model_name_value, str) and model_name_value.strip():
        return model_name_value.strip()
    return TOKENFLOW_RUNTIME_DEFAULT_MODEL or None


def _write_audit_log(entry: dict[str, Any]):
    try:
        TOKENFLOW_RUNTIME_AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(entry, ensure_ascii=False)
        with TOKENFLOW_RUNTIME_AUDIT_LOG_PATH.open('a', encoding='utf-8') as handle:
            handle.write(line + '\n')
    except Exception:
        # Audit logging should not break runtime execution flow.
        return


def _build_exec_scope(
    payload: NodeExecutionRequest,
    logs: list[str],
    resources: list[dict[str, Any]],
    context: dict[str, Any],
    output_limit: int,
    cancellation: RuntimeCancellation
) -> dict[str, Any]:
    def runtime_cancelled() -> bool:
        return cancellation.is_cancelled()

    def runtime_checkpoint():
        if cancellation.is_cancelled():
            raise RuntimeExecutionError(
                'TIMEOUT',
                'Execution was cancelled',
                detail={'reason': cancellation.reason or 'cancelled'}
            )

    def runtime_print(*args, **kwargs):
        runtime_checkpoint()
        sep = kwargs.get('sep', ' ')
        end = kwargs.get('end', '')
        line = sep.join(str(arg) for arg in args) + end
        logs.append(_trim_text(_redact_text(line), max_chars=output_limit))

    def runtime_model(prompt: str, model: str | None = None, **kwargs):
        runtime_checkpoint()
        return _run_local_model(prompt=prompt, model_name=model, **kwargs)

    safe_builtins: dict[str, Any] = {
        'abs': abs,
        'all': all,
        'any': any,
        'bool': bool,
        'dict': dict,
        'enumerate': enumerate,
        'float': float,
        'int': int,
        'len': len,
        'list': list,
        'max': max,
        'min': min,
        'pow': pow,
        'range': range,
        'round': round,
        'set': set,
        'sorted': sorted,
        'str': str,
        'sum': sum,
        'tuple': tuple,
        'zip': zip,
        'map': map,
        'filter': filter,
        'Exception': Exception,
        'ValueError': ValueError,
        'TypeError': TypeError,
        'RuntimeError': RuntimeError,
        'print': runtime_print,
        '__import__': _restricted_import
    }
    return {
        '__builtins__': safe_builtins,
        '__name__': '__tokenflow_runtime__',
        'node_id': payload.node_id,
        'node_inputs': payload.inputs,
        'node_attributes': {},
        'node_env': payload.env,
        'node_resources': resources,
        'run_local_model': runtime_model,
        'runtime_context': context,
        'runtime_cancelled': runtime_cancelled,
        'runtime_checkpoint': runtime_checkpoint
    }


def _invoke_target(
    target_fn: Any,
    payload: NodeExecutionRequest,
    context: dict[str, Any],
    resources: list[dict[str, Any]],
    cancellation: RuntimeCancellation
):
    if cancellation.is_cancelled():
        raise RuntimeExecutionError('TIMEOUT', 'Execution was cancelled')
    signature = inspect.signature(target_fn)
    args = list(payload.module.args)
    kwargs = dict(payload.module.kwargs)
    value = payload.inputs[0] if payload.inputs else None
    alias_values: dict[str, Any] = {
        'value': value,
        'input': value,
        'inputs': payload.inputs,
        'context': context,
        'resources': resources,
        'env': payload.env,
        'node_id': payload.node_id,
        'node_type': payload.node_type
    }
    provided = set(kwargs)
    positional_params = [
        parameter
        for parameter in signature.parameters.values()
        if parameter.kind in {inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD}
    ]
    for parameter in positional_params[:len(args)]:
        provided.add(parameter.name)
    for parameter in signature.parameters.values():
        if parameter.kind in {inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD}:
            continue
        if parameter.name in provided or parameter.default is not inspect._empty:
            continue
        if parameter.name not in alias_values:
            continue
        if parameter.kind == inspect.Parameter.POSITIONAL_ONLY:
            args.append(alias_values[parameter.name])
        else:
            kwargs[parameter.name] = alias_values[parameter.name]
        provided.add(parameter.name)
    if not payload.module.args and not payload.module.kwargs and not kwargs:
        params = [p for p in signature.parameters.values() if p.kind in {inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD}]
        if len(params) >= 3:
            args = [value, context, resources]
        elif len(params) == 2:
            args = [value, context]
        elif len(params) == 1:
            args = [value]
    try:
        signature.bind(*args, **kwargs)
    except TypeError as exc:
        raise RuntimeExecutionError('INVALID_REQUEST', f'module arguments mismatch: {exc}') from exc
    if cancellation.is_cancelled():
        raise RuntimeExecutionError('TIMEOUT', 'Execution was cancelled')
    result = target_fn(*args, **kwargs)
    if inspect.isawaitable(result):
        raise RuntimeExecutionError('INVALID_REQUEST', 'Async function is not supported in runtime module execution')
    return result


def _execute_python_module(payload: NodeExecutionRequest, cancellation: RuntimeCancellation) -> tuple[Any, list[str], float]:
    _validate_source(payload.module.source)
    resources = _normalize_resources(payload)
    output_limit = _resolve_output_limit(payload)
    logs: list[str] = []
    context = {
        'node_id': payload.node_id,
        'node_type': payload.node_type,
        'execution_mode': payload.execution_mode,
        'env': dict(payload.env)
    }
    TOKENFLOW_RUNTIME_TEMP_DIR.mkdir(parents=True, exist_ok=True)
    run_dir = TOKENFLOW_RUNTIME_TEMP_DIR / f'tokenflow-runtime-{uuid.uuid4().hex}'
    run_dir.mkdir(parents=True, exist_ok=False)
    try:
        module_path = run_dir / 'runtime_module.py'
        module_path.write_text(payload.module.source, encoding='utf-8')
        try:
            code = compile(payload.module.source, str(module_path), 'exec')
        except SyntaxError as exc:
            raise RuntimeExecutionError(
                'INVALID_REQUEST',
                f'Syntax error in module.source: {exc.msg}',
                detail={'lineno': exc.lineno, 'offset': exc.offset}
            ) from exc
        tracemalloc.start()
        scope = _build_exec_scope(
            payload=payload,
            logs=logs,
            resources=resources,
            context=context,
            output_limit=output_limit,
            cancellation=cancellation
        )
        exec(code, scope, scope)
        function_name = payload.module.function_name
        if not function_name:
            raise RuntimeExecutionError('INVALID_REQUEST', 'module.function_name is required')
        target_fn = scope.get(function_name)
        if target_fn is None:
            raise RuntimeExecutionError('INVALID_REQUEST', f'Function "{function_name}" not found in module.source')
        if not callable(target_fn):
            raise RuntimeExecutionError('INVALID_REQUEST', f'"{function_name}" is not callable')
        if inspect.iscoroutinefunction(target_fn):
            raise RuntimeExecutionError('INVALID_REQUEST', 'Async function is not supported in runtime module execution')
        result = _invoke_target(
            target_fn=target_fn,
            payload=payload,
            context=context,
            resources=resources,
            cancellation=cancellation
        )
        _current, peak_bytes = tracemalloc.get_traced_memory()
        peak_memory_mb = peak_bytes / (1024 * 1024)
        if peak_memory_mb > TOKENFLOW_RUNTIME_MAX_MEMORY_MB:
            raise RuntimeExecutionError(
                'RESOURCE_LIMIT_EXCEEDED',
                f'Execution memory limit exceeded ({peak_memory_mb:.2f}MB > {TOKENFLOW_RUNTIME_MAX_MEMORY_MB}MB)'
            )
        return _safe_output(result, max_chars=output_limit), _normalize_logs(logs, max_chars=output_limit), peak_memory_mb
    finally:
        if tracemalloc.is_tracing():
            tracemalloc.stop()
        shutil.rmtree(run_dir, ignore_errors=True)


def _build_failed_response(
    payload: NodeExecutionRequest,
    code: str,
    message: str,
    duration_ms: float,
    trace: list[RuntimeTraceEntry],
    detail: Any = None,
    traceback_text: str | None = None,
    logs: list[str] | None = None,
    timeout_seconds: float | None = None,
    memory_peak_mb: float | None = None
) -> NodeExecutionResponse:
    return NodeExecutionResponse(
        protocol_version=PROTOCOL_VERSION,
        request_id=payload.request_id,
        status='failed',
        output=None,
        logs=_normalize_logs(logs or [], max_chars=TOKENFLOW_RUNTIME_MAX_OUTPUT_CHARS),
        error=ExecutionError(
            code=code,
            message=_redact_text(message),
            detail=detail,
            traceback=_redact_text(traceback_text) if traceback_text else None
        ),
        metrics=RuntimeMetrics(duration_ms=duration_ms, timeout_seconds=timeout_seconds, memory_peak_mb=memory_peak_mb),
        trace=trace
    )


async def execute_node(payload: NodeExecutionRequest, requestor: str | None = None) -> NodeExecutionResponse:
    started = perf_counter()
    timeout_seconds = _resolve_timeout_seconds(payload)
    trace: list[RuntimeTraceEntry] = []
    response: NodeExecutionResponse | None = None
    cancellation = RuntimeCancellation()
    queue_reserved = False
    peak_memory_mb: float | None = None
    model_name = _extract_model_name(payload)
    try:
        _validate_protocol_version(payload.protocol_version)
        if payload.execution_mode not in {'python-module', 'builtin', 'auto'}:
            raise RuntimeExecutionError('INVALID_REQUEST', f'Unsupported execution_mode: {payload.execution_mode}')
        _reserve_queue_slot()
        queue_reserved = True
        trace.append(RuntimeTraceEntry(node_id=payload.node_id, phase='queue', status='ok'))
        trace.append(RuntimeTraceEntry(node_id=payload.node_id, phase='prepare', status='ok'))
        if payload.execution_mode != 'python-module':
            raise RuntimeExecutionError(
                'INVALID_REQUEST',
                f'Only "python-module" mode is currently supported (received: {payload.execution_mode})'
            )
        async with _RUNTIME_SEMAPHORE:
            loop = asyncio.get_running_loop()
            future = loop.run_in_executor(_RUNTIME_EXECUTOR, _execute_python_module, payload, cancellation)
            output, logs, peak_memory_mb = await asyncio.wait_for(future, timeout=timeout_seconds)
        trace.append(RuntimeTraceEntry(node_id=payload.node_id, phase='run', status='ok'))
        trace.append(RuntimeTraceEntry(node_id=payload.node_id, phase='postprocess', status='ok'))
        response = NodeExecutionResponse(
            protocol_version=PROTOCOL_VERSION,
            request_id=payload.request_id,
            status='ok',
            output=output,
            logs=logs,
            error=None,
            metrics=RuntimeMetrics(
                duration_ms=(perf_counter() - started) * 1000,
                timeout_seconds=timeout_seconds,
                memory_peak_mb=peak_memory_mb
            ),
            trace=trace
        )
        return response
    except asyncio.TimeoutError:
        cancellation.cancel('hard-timeout')
        if TOKENFLOW_RUNTIME_CANCEL_GRACE_MS > 0:
            await asyncio.sleep(TOKENFLOW_RUNTIME_CANCEL_GRACE_MS / 1000.0)
        trace.append(RuntimeTraceEntry(node_id=payload.node_id, phase='run', status='error', detail='timeout'))
        response = _build_failed_response(
            payload=payload,
            code='TIMEOUT',
            message=f'Execution timed out after {timeout_seconds:.3f}s',
            detail={'timeout_seconds': timeout_seconds},
            traceback_text=None,
            logs=[],
            duration_ms=(perf_counter() - started) * 1000,
            timeout_seconds=timeout_seconds,
            memory_peak_mb=peak_memory_mb,
            trace=trace
        )
        return response
    except RuntimeExecutionError as exc:
        trace.append(RuntimeTraceEntry(node_id=payload.node_id, phase='run', status='error', detail=exc.code))
        response = _build_failed_response(
            payload=payload,
            code=exc.code,
            message=exc.message,
            detail=exc.detail,
            traceback_text=exc.traceback_text,
            logs=[],
            duration_ms=(perf_counter() - started) * 1000,
            timeout_seconds=timeout_seconds,
            memory_peak_mb=peak_memory_mb,
            trace=trace
        )
        return response
    except Exception as exc:
        trace_text = traceback.format_exc()
        trace.append(RuntimeTraceEntry(node_id=payload.node_id, phase='run', status='error', detail=type(exc).__name__))
        response = _build_failed_response(
            payload=payload,
            code='RUNTIME_EXCEPTION',
            message=str(exc),
            detail=None,
            traceback_text=trace_text,
            logs=[],
            duration_ms=(perf_counter() - started) * 1000,
            timeout_seconds=timeout_seconds,
            memory_peak_mb=peak_memory_mb,
            trace=trace
        )
        return response
    finally:
        if queue_reserved:
            _release_queue_slot()
        _write_audit_log(
            {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'request_id': payload.request_id,
                'node_id': payload.node_id,
                'execution_mode': payload.execution_mode,
                'requestor': requestor or payload.env.get('USER_ID') or payload.env.get('USER_EMAIL') or 'anonymous',
                'model': model_name or '',
                'status': response.status if response else 'failed',
                'error_code': response.error.code if response and response.error else '',
                'duration_ms': response.metrics.duration_ms if response else (perf_counter() - started) * 1000
            }
        )


def _list_models() -> list[str]:
    if not TOKENFLOW_MODELS_DIR.exists() or not TOKENFLOW_MODELS_DIR.is_dir():
        return []
    models = [item.name for item in TOKENFLOW_MODELS_DIR.iterdir() if item.is_file() and item.suffix.lower() == '.gguf']
    return sorted(models)


def _check_llama_cpp_available() -> bool:
    if TOKENFLOW_RUNTIME_MODEL_BACKEND != 'llama-cpp-python':
        return False
    try:
        import llama_cpp  # noqa: F401
        return True
    except Exception:
        return False


def get_runtime_capabilities() -> list[NodeCapability]:
    return [
        NodeCapability(
            node_type='runtime',
            execution_mode='python-module',
            description='Execute Python function snippet sent from frontend nodes.',
            outputs=['output', 'logs', 'error', 'metrics'],
            default_attributes={
                'timeout_seconds': TOKENFLOW_RUNTIME_TIMEOUT_SECONDS,
                'max_queue_length': TOKENFLOW_RUNTIME_MAX_QUEUE_LENGTH,
                'max_memory_mb': TOKENFLOW_RUNTIME_MAX_MEMORY_MB
            },
            supports_python_module=True
        ),
        NodeCapability(
            node_type='llm',
            execution_mode='python-module',
            description='Local GGUF inference via llama-cpp-python.',
            outputs=['text'],
            default_attributes={
                'backend': TOKENFLOW_RUNTIME_MODEL_BACKEND,
                'default_model': TOKENFLOW_RUNTIME_DEFAULT_MODEL
            },
            supports_python_module=True
        )
    ]


def get_runtime_health() -> RuntimeHealth:
    models = _list_models()
    dependencies = {
        'llama_cpp_available': _check_llama_cpp_available()
    }
    status = 'ok'
    if TOKENFLOW_RUNTIME_MODEL_BACKEND == 'llama-cpp-python' and not dependencies['llama_cpp_available']:
        status = 'degraded'
    limits = {
        'timeout_seconds': TOKENFLOW_RUNTIME_TIMEOUT_SECONDS,
        'max_concurrency': TOKENFLOW_RUNTIME_MAX_CONCURRENCY,
        'max_queue_length': TOKENFLOW_RUNTIME_MAX_QUEUE_LENGTH,
        'max_memory_mb': TOKENFLOW_RUNTIME_MAX_MEMORY_MB,
        'cancel_grace_ms': TOKENFLOW_RUNTIME_CANCEL_GRACE_MS,
        'max_source_chars': TOKENFLOW_RUNTIME_MAX_SOURCE_CHARS,
        'max_resource_bytes': TOKENFLOW_RUNTIME_MAX_RESOURCE_BYTES,
        'max_output_chars': TOKENFLOW_RUNTIME_MAX_OUTPUT_CHARS,
        'temp_dir': str(TOKENFLOW_RUNTIME_TEMP_DIR),
        'audit_log_path': str(TOKENFLOW_RUNTIME_AUDIT_LOG_PATH),
        'pending_tasks': _RUNTIME_PENDING,
        'allowed_models': sorted(TOKENFLOW_RUNTIME_ALLOWED_MODELS),
        'allowed_imports': sorted(TOKENFLOW_RUNTIME_ALLOWED_IMPORTS)
    }
    return RuntimeHealth(
        status=status,
        model_backend=TOKENFLOW_RUNTIME_MODEL_BACKEND,
        default_model=TOKENFLOW_RUNTIME_DEFAULT_MODEL,
        models=models,
        limits=limits,
        dependencies=dependencies
    )
