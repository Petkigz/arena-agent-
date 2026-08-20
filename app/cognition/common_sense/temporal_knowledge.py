"""
Temporal Knowledge

Facts about time, sequences, and temporal relationships including:
- Before and after relationships
- Duration and frequency
- Daily cycles
- Seasonal patterns
- Aging and change over time
"""

TEMPORAL_KNOWLEDGE_FACTS = [
    # ── Before and After ──
    {"fact_id": "temp_001", "category": "temporal", "fact": "Breakfast comes before lunch", "confidence": 1.0},
    {"fact_id": "temp_002", "category": "temporal", "fact": "Lunch comes before dinner", "confidence": 1.0},
    {"fact_id": "temp_003", "category": "temporal", "fact": "Morning comes before afternoon", "confidence": 1.0},
    {"fact_id": "temp_004", "category": "temporal", "fact": "Afternoon comes before evening", "confidence": 1.0},
    {"fact_id": "temp_005", "category": "temporal", "fact": "Evening comes before night", "confidence": 1.0},
    {"fact_id": "temp_006", "category": "temporal", "fact": "Night comes before the next morning", "confidence": 1.0},
    {"fact_id": "temp_007", "category": "temporal", "fact": "Monday comes before Tuesday", "confidence": 1.0},
    {"fact_id": "temp_008", "category": "temporal", "fact": "Friday comes before Saturday", "confidence": 1.0},
    {"fact_id": "temp_009", "category": "temporal", "fact": "Saturday comes before Sunday", "confidence": 1.0},
    {"fact_id": "temp_010", "category": "temporal", "fact": "Spring comes before summer", "confidence": 1.0},
    {"fact_id": "temp_011", "category": "temporal", "fact": "Summer comes before autumn", "confidence": 1.0},
    {"fact_id": "temp_012", "category": "temporal", "fact": "Autumn comes before winter", "confidence": 1.0},
    {"fact_id": "temp_013", "category": "temporal", "fact": "Winter comes before spring", "confidence": 1.0},
    {"fact_id": "temp_014", "category": "temporal", "fact": "Childhood comes before adulthood", "confidence": 1.0},
    {"fact_id": "temp_015", "category": "temporal", "fact": "January is the first month of the year", "confidence": 1.0},
    {"fact_id": "temp_016", "category": "temporal", "fact": "December is the last month of the year", "confidence": 1.0},
    {"fact_id": "temp_017", "category": "temporal", "fact": "Sunrise comes before sunset each day", "confidence": 1.0},
    {"fact_id": "temp_018", "category": "temporal", "fact": "Planting comes before harvesting", "confidence": 1.0},
    {"fact_id": "temp_019", "category": "temporal", "fact": "Cooking comes before eating", "confidence": 0.9},
    {"fact_id": "temp_020", "category": "temporal", "fact": "Washing comes before drying", "confidence": 0.9},

    # ── Duration and Frequency ──
    {"fact_id": "temp_101", "category": "temporal", "fact": "A day has 24 hours", "confidence": 1.0},
    {"fact_id": "temp_102", "category": "temporal", "fact": "An hour has 60 minutes", "confidence": 1.0},
    {"fact_id": "temp_103", "category": "temporal", "fact": "A minute has 60 seconds", "confidence": 1.0},
    {"fact_id": "temp_104", "category": "temporal", "fact": "A week has 7 days", "confidence": 1.0},
    {"fact_id": "temp_105", "category": "temporal", "fact": "A year has 12 months", "confidence": 1.0},
    {"fact_id": "temp_106", "category": "temporal", "fact": "A year has about 365 days", "confidence": 1.0},
    {"fact_id": "temp_107", "category": "temporal", "fact": "A leap year has 366 days", "confidence": 1.0},
    {"fact_id": "temp_108", "category": "temporal", "fact": "February has 28 days in a common year", "confidence": 1.0},
    {"fact_id": "temp_109", "category": "temporal", "fact": "February has 29 days in a leap year", "confidence": 1.0},
    {"fact_id": "temp_110", "category": "temporal", "fact": "A decade is 10 years", "confidence": 1.0},
    {"fact_id": "temp_111", "category": "temporal", "fact": "A century is 100 years", "confidence": 1.0},
    {"fact_id": "temp_112", "category": "temporal", "fact": "Boiling water takes a few minutes", "confidence": 0.9},
    {"fact_id": "temp_113", "category": "temporal", "fact": "Growing a tree takes years", "confidence": 1.0},
    {"fact_id": "temp_114", "category": "temporal", "fact": "Baking a cake takes about an hour", "confidence": 0.8},
    {"fact_id": "temp_115", "category": "temporal", "fact": "A shower typically takes 5-15 minutes", "confidence": 0.9},
    {"fact_id": "temp_116", "category": "temporal", "fact": "A commute to work typically takes 15-60 minutes", "confidence": 0.8},
    {"fact_id": "temp_117", "category": "temporal", "fact": "A movie typically lasts 1.5-3 hours", "confidence": 0.9},
    {"fact_id": "temp_118", "category": "temporal", "fact": "A night's sleep typically lasts 6-9 hours", "confidence": 0.9},
    {"fact_id": "temp_119", "category": "temporal", "fact": "A work day is typically 8 hours", "confidence": 0.8},
    {"fact_id": "temp_120", "category": "temporal", "fact": "Weekends are Saturday and Sunday", "confidence": 1.0},

    # ── Daily Cycles ──
    {"fact_id": "temp_201", "category": "temporal", "fact": "The sun rises in the morning", "confidence": 1.0},
    {"fact_id": "temp_202", "category": "temporal", "fact": "The sun sets in the evening", "confidence": 1.0},
    {"fact_id": "temp_203", "category": "temporal", "fact": "It is brightest at midday", "confidence": 1.0},
    {"fact_id": "temp_204", "category": "temporal", "fact": "It is darkest at midnight", "confidence": 1.0},
    {"fact_id": "temp_205", "category": "temporal", "fact": "Temperature is usually coolest in the early morning", "confidence": 0.9},
    {"fact_id": "temp_206", "category": "temporal", "fact": "Temperature is usually warmest in the afternoon", "confidence": 0.9},
    {"fact_id": "temp_207", "category": "temporal", "fact": "People usually wake up in the morning", "confidence": 0.9},
    {"fact_id": "temp_208", "category": "temporal", "fact": "People usually go to sleep at night", "confidence": 0.9},
    {"fact_id": "temp_209", "category": "temporal", "fact": "Rush hour is typically in the morning and evening", "confidence": 0.9},
    {"fact_id": "temp_210", "category": "temporal", "fact": "Stars are visible at night but not during the day", "confidence": 1.0},

    # ── Aging and Change ──
    {"fact_id": "temp_301", "category": "temporal", "fact": "People grow taller as they age from childhood", "confidence": 1.0},
    {"fact_id": "temp_302", "category": "temporal", "fact": "Hair turns gray as people get older", "confidence": 0.9},
    {"fact_id": "temp_303", "category": "temporal", "fact": "Fruit ripens over time", "confidence": 1.0},
    {"fact_id": "temp_304", "category": "temporal", "fact": "Food spoils if left too long", "confidence": 1.0},
    {"fact_id": "temp_305", "category": "temporal", "fact": "Metal rusts over time when exposed to moisture", "confidence": 1.0},
    {"fact_id": "temp_306", "category": "temporal", "fact": "Paint fades over time in sunlight", "confidence": 1.0},
    {"fact_id": "temp_307", "category": "temporal", "fact": "Clothes wear out with repeated use", "confidence": 1.0},
    {"fact_id": "temp_308", "category": "temporal", "fact": "Trees grow larger over years", "confidence": 1.0},
    {"fact_id": "temp_309", "category": "temporal", "fact": "Skills improve with practice over time", "confidence": 1.0},
    {"fact_id": "temp_310", "category": "temporal", "fact": "Memories fade over time without reinforcement", "confidence": 0.9},
    {"fact_id": "temp_311", "category": "temporal", "fact": "Wounds heal over days or weeks", "confidence": 1.0},
    {"fact_id": "temp_312", "category": "temporal", "fact": "Seasons change every few months", "confidence": 1.0},
    {"fact_id": "temp_313", "category": "temporal", "fact": "The moon goes through phases over about a month", "confidence": 1.0},
    {"fact_id": "temp_314", "category": "temporal", "fact": "Tides change approximately every 6 hours", "confidence": 1.0},
    {"fact_id": "temp_315", "category": "temporal", "fact": "Technology becomes outdated over years", "confidence": 0.9},
]
