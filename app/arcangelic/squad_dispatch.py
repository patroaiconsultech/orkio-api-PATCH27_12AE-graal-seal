from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from .squad_registry import load_squad_agents, load_squad_runtime_defaults


_KEYWORD_MAP = {
    "backend_engineer": [
        "fastapi", "postgres", "alembic", "endpoint", "/api/chat", "/api/chat/stream",
        "rbac", "tenant", "persist", "migration", "banco", "database", "schema",
    ],
    "streaming_engineer": [
        "sse", "stream", "streaming", "chunk", "agent_done", "done", "listener",
        "duplicação", "duplicado", "duplica", "race", "hang", "pendurada",
    ],
    "realtime_voice_engineer": [
        "stt", "tts", "webrtc", "voice", "voz", "mic", "microfone", "transcript",
        "áudio", "audio", "playback",
    ],
    "frontend_engineer": [
        "react", "vite", "frontend", "ui", "appconsole", "render", "payload",
        "console", "component", "hook", "listener client",
    ],
    "runtime_openai_engineer": [
        "openai", "provider", "timeout", "token", "max_tokens", "temperature",
        "context window", "server_busy", "modelo", "model",
    ],
    "security_multi_tenant_engineer": [
        "security", "segurança", "cors", "secret", "secrets", "tenant",
        "multi-tenant", "auth", "authorization", "permission", "permissão",
        "cross-tenant",
    ],
    "technical_auditor": [
        "auditoria", "auditor", "regressão", "regression", "incidente",
        "root cause", "causa raiz", "severidade", "review",
    ],
    "qa_test_engineer": [
        "teste", "test", "qa", "smoke", "acceptance", "validação", "validar",
    ],
    "sre_reliability_engineer": [
        "latência", "latencia", "reliability", "sre", "observability",
        "métrica", "metrica", "healthcheck", "retry", "timeout operacional",
    ],
    "product_designer": [
        "ux", "design", "designer", "experiência", "experiencia", "interface",
        "stage mode", "team mode", "visual", "percepção", "percepcao",
    ],
    "conversation_designer": [
        "conversation", "conversa", "tom", "tone", "multi-agent", "multiagente",
        "fala", "resposta sobreposta", "ordem de fala",
    ],
    "technical_product_strategist": [
        "roadmap", "mvp", "prioridade", "priorização", "trade-off", "sequência",
        "sequencia", "backlog", "produto", "enterprise",
    ],
    "agent_systems_architect": [
        "dispatch", "router", "roteamento", "stage mode", "team mode",
        "múltiplos agentes", "multiplos agentes", "agentes respondendo",
        "agent architecture", "papéis", "papeis",
    ],
    "knowledge_memory_engineer": [
        "memory", "memória", "memoria", "rag", "context", "contexto",
        "knowledge", "base de conhecimento", "thread context", "org context",
    ],
}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _is_orion_technical_request(message: str) -> bool:
    raw = _normalize(message)
    if not raw:
        return False
    technical_markers = [
        "@orion", "orion", "cto", "backend", "frontend", "stream", "sse",
        "webrtc", "openai", "fastapi", "postgres", "runtime", "deploy",
        "produção", "producao", "produção", "bug", "erro", "patch", "arquitetura",
    ]
    return any(m in raw for m in technical_markers)


def should_apply_orion_squad(agent: Any, message: str) -> bool:
    agent_name = ((getattr(agent, "name", None) or "")).strip().lower()
    if agent_name == "orion" or agent_name.startswith("orion "):
        return True
    return _is_orion_technical_request(message)


def _score_specialists(message: str, agents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    raw = _normalize(message)
    scored: List[Dict[str, Any]] = []

    for a in agents:
        slug = (a.get("slug") or "").strip()
        if not slug or slug == "orion_cto":
            continue
        score = 0
        for kw in _KEYWORD_MAP.get(slug, []):
            if kw in raw:
                score += 3
        for tag in (a.get("domain_tags") or []):
            tag_norm = str(tag).replace("_", " ").lower()
            if tag_norm and tag_norm in raw:
                score += 2
        if score > 0:
            scored.append({**a, "_score": score})

    scored.sort(key=lambda x: (int(x.get("_score") or 0), int(x.get("priority") or 0)), reverse=True)
    return scored


def build_orion_squad_overlay(db: Session, *, org: str, message: str) -> Dict[str, Any]:
    """
    Retorna um overlay de sistema para o Orion operar como CTO coordenando especialistas internos.
    Não cria chamadas extras de LLM e não altera agentes visíveis do usuário.
    Fail-open: em erro, retorna estrutura vazia.
    """
    try:
        if not _is_orion_technical_request(message):
            return {}

        agents = load_squad_agents(db)
        defaults = load_squad_runtime_defaults(db)
        scored = _score_specialists(message, agents)

        primary = scored[0] if scored else None
        secondary = scored[1] if len(scored) > 1 else None

        lines = [
            "Internal Orion CTO squad overlay:",
            "- You are Orion acting as the visible CTO orchestrator.",
            "- Only Orion should answer the user directly.",
            "- Use at most one primary specialist and one silent secondary specialist.",
            "- Do not present the internal squad as separate visible responders.",
            "- Keep the answer technical, structured, and decisive.",
        ]
        if primary:
            lines.append(f"- Primary silent specialist: {primary.get('name')} ({primary.get('code')})")
            tags = ", ".join(primary.get("domain_tags") or [])
            if tags:
                lines.append(f"- Primary domain focus: {tags}")
        if secondary:
            lines.append(f"- Secondary silent specialist: {secondary.get('name')} ({secondary.get('code')})")

        if defaults:
            lines.append(
                f"- Runtime defaults: ONLY_ORION_RESPONDS={bool(defaults.get('ORION_SINGLE_VISIBLE_RESPONDER', True))}, "
                f"MAX_PRIMARY={int(defaults.get('MAX_PRIMARY_SPECIALISTS', 1) or 1)}, "
                f"MAX_SECONDARY={int(defaults.get('MAX_SECONDARY_SPECIALISTS', 1) or 1)}"
            )

        lines.extend([
            "Answer format:",
            "1) Problem",
            "2) Root cause",
            "3) Impact",
            "4) Safe next action",
        ])

        return {
            "enabled": True,
            "primary_specialist": primary.get("slug") if primary else None,
            "secondary_specialist": secondary.get("slug") if secondary else None,
            "overlay_text": "\n".join(lines),
        }
    except Exception:
        return {}
