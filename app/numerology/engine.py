from __future__ import annotations
from typing import Any, Dict
from .service import name_number, life_path

_LIFE_PATH_LABELS = {
    1: "iniciador", 2: "mediador", 3: "comunicador", 4: "construtor",
    5: "explorador", 6: "cuidador", 7: "analista", 8: "realizador", 9: "humanitário",
    11: "intuitivo", 22: "arquiteto", 33: "mentor",
}

def generate_numerology_profile(payload: Dict[str, Any]) -> Dict[str, Any]:
    full_name = payload.get("full_name") or ""
    birth_date = payload.get("birth_date") or ""
    preferred_name = payload.get("preferred_name") or full_name.split(" ")[0] if full_name else "você"
    context = payload.get("context") or "vida prática"
    nn = name_number(full_name)
    lp = life_path(birth_date)
    life_label = _LIFE_PATH_LABELS.get(lp, "integrador")
    summary = (
        f"{preferred_name} carrega uma leitura simbólica de perfil {life_label}, "
        f"com ênfase em número de expressão {nn}. "
        f"Neste contexto de {context}, a interpretação útil é priorizar clareza, ritmo e coerência."
    )
    guidance = [
        "escolha uma prioridade principal antes de abrir novas frentes",
        "traduza intuição em um próximo passo verificável",
        "revise semanalmente o que gera energia versus drenagem",
    ]
    return {
        "profile_type": "numerology_cabalistic",
        "confidence_level": "symbolic_interpretive",
        "user_confirmed": False,
        "dimensions": {
            "expression_number": nn,
            "life_path": lp,
            "life_path_label": life_label,
        },
        "narrative_summary": summary,
        "practical_guidance": guidance,
        "planner_hints": {
            "best_mode": "structured_reflection",
            "focus_pattern": f"{life_label}_mode",
            "context": context,
        },
        "metadata": {
            "preferred_name": preferred_name,
            "consent_required_for_strong_memory": True,
        },
    }
