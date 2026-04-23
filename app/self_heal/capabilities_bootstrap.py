from app.self_heal.capability_planner import planner


planner.register_capability(
    name="self_knowledge_app",
    required_models=[
        "NumerologyProfile",
        "AstrologyProfile",
        "EnneagramProfile",
        "ChineseZodiacProfile",
    ],
    required_routes=[
        "/numerology/calculate",
        "/astrology/calculate",
        "/enneagram/calculate",
        "/chinese_zodiac/calculate",
    ],
    required_agents=[
        "numerology_agent",
        "astrology_agent",
        "enneagram_agent",
        "chinese_zodiac_agent",
    ],
    required_views=[
        "NumerologyDashboard",
        "AstrologyDashboard",
        "EnneagramDashboard",
        "ChineseZodiacDashboard",
    ],
)
